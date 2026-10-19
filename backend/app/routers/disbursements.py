from datetime import datetime, date
import io

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_branch_access, require_perm, has_perm
from ..models import Business, DisbursementBatch, DisbursementItem, Program
from ..utils import paginate, parse_page

router = APIRouter(tags=["disbursements"])


def batch_ser(b: DisbursementBatch, db: Session, include_items: bool = True) -> dict:
    data = {
        "id": b.id,
        "branch_id": b.branch_id,
        "program_id": b.program_id,
        "program_name": b.program.name if b.program else None,
        "title": b.title,
        "payment_date": str(b.payment_date) if b.payment_date else None,
        "currency": b.currency or "EUR",
        "disbursement_currency": getattr(b, "disbursement_currency", None) or "JOD",
        "exchange_rate": float(getattr(b, "exchange_rate", None) if getattr(b, "exchange_rate", None) is not None else 0.76),
        "base_amount": float(b.base_amount or 0.0),
        "total_amount": float(b.total_amount or 0.0),
        "total_amount_eur": float(b.total_amount or 0.0),
        "total_amount_jod": float(getattr(b, "total_amount_jod", None) if getattr(b, "total_amount_jod", None) is not None else round((b.total_amount or 0.0) * (getattr(b, "exchange_rate", None) or 0.76), 3)),
        "status": b.status or "draft",
        "notes": b.notes or "",
        "created_by": {
            "id": b.created_by.id,
            "name": f"{b.created_by.first_name} {b.created_by.last_name}".strip() or b.created_by.email,
            "email": b.created_by.email,
        } if b.created_by else None,
        "confirmed_by": {
            "id": b.confirmed_by.id,
            "name": f"{b.confirmed_by.first_name} {b.confirmed_by.last_name}".strip() or b.confirmed_by.email,
            "email": b.confirmed_by.email,
        } if b.confirmed_by else None,
        "confirmed_at": str(b.confirmed_at) if b.confirmed_at else None,
        "created_at": str(b.created_at) if b.created_at else None,
        "updated_at": str(b.updated_at) if b.updated_at else None,
        "items_count": len(b.items) if b.items else 0,
        # startups that actually received the payment (excluded ones don't count)
        "received_count": sum(1 for it in (b.items or []) if it.is_included),
    }
    # the payout the batch actually carries: the included items. Batch-level
    # totals can go stale when items are added, removed or excluded after the
    # batch was created, so the displayed figures always come from the items.
    _inc = [it for it in (b.items or []) if it.is_included]
    _eur = round(sum(float(it.amount or 0.0) for it in _inc), 2)
    _jod = round(sum(float(it.amount_jod or 0.0) for it in _inc), 3)
    _rate = float(getattr(b, "exchange_rate", None) if getattr(b, "exchange_rate", None) is not None else 0.76)
    data["total_amount_eur"] = _eur
    data["total_amount_jod"] = _jod if _jod else round(_eur * _rate, 3)
    # the rate the batch actually paid at: the item-weighted average, since
    # items can carry their own FX rates and the header rate may be stale
    data["effective_rate"] = round(_jod / _eur, 4) if (_eur and _jod) else _rate
    if include_items:
        batch_rate = float(getattr(b, "exchange_rate", None) if getattr(b, "exchange_rate", None) is not None else 0.76)
        data["items"] = [
            {
                "id": it.id,
                "business_id": it.business_id,
                "business_name": it.business.name if it.business else "",
                "business_logo": it.business.logo if it.business else None,
                "founders": [
                    {
                        "id": f.id,
                        "name": f"{f.first_name} {f.last_name}".strip(),
                        "email": f.email,
                    }
                    for f in (it.business.founders if it.business else [])
                ],
                "percentage": float(it.percentage if it.percentage is not None else 100.0),
                "amount": float(it.amount or 0.0),
                "amount_eur": float(it.amount or 0.0),
                "amount_jod": float(getattr(it, "amount_jod", None) if getattr(it, "amount_jod", None) is not None else round((it.amount or 0.0) * (getattr(it, "exchange_rate", None) or batch_rate), 3)),
                "disbursement_date": str(getattr(it, "disbursement_date", None) or b.payment_date or ""),
                "exchange_rate": float(getattr(it, "exchange_rate", None) if getattr(it, "exchange_rate", None) is not None else batch_rate),
                "is_included": bool(it.is_included),
                "notes": it.notes or "",
            }
            for it in b.items
        ]
    return data


# ------------------------------------------------------------------ Summary KPIs

@router.get("/disbursements/{branch_id}/summary/")
def disbursements_summary(
    branch_id: int,
    request: Request,
    ctx=Depends(require_perm("disbursements.view")),
):
    db: Session = ctx["db"]
    q = db.query(DisbursementBatch).filter(DisbursementBatch.branch_id == branch_id)

    # the same filters the batch list supports, so the headline tiles follow
    # whatever the toolbar has selected
    if program_id := request.query_params.get("program_id"):
        try:
            q = q.filter(DisbursementBatch.program_id == int(program_id))
        except ValueError:
            pass
    if status := request.query_params.get("status"):
        q = q.filter(DisbursementBatch.status == status)
    if currency := request.query_params.get("currency"):
        q = q.filter(DisbursementBatch.currency == currency.upper())
    if search := request.query_params.get("search"):
        q = q.filter(DisbursementBatch.title.ilike(f"%{search}%"))

    batches = q.all()
    
    total_batches = len(batches)
    draft_batches = sum(1 for b in batches if b.status == "draft")
    processed_batches = sum(1 for b in batches if b.status == "processed")
    
    # headline totals come from the included items as well: batch-level
    # totals can be stale (items added/removed/excluded after creation), and
    # the tiles must agree with the track breakdown and the batch rows
    totals_by_currency = {"USD": 0.0, "EUR": 0.0, "JOD": 0.0}
    pending_by_currency = {"USD": 0.0, "EUR": 0.0, "JOD": 0.0}
    _item_agg = db.query(
        DisbursementItem.batch_id,
        func.coalesce(func.sum(DisbursementItem.amount), 0.0),
        func.coalesce(func.sum(DisbursementItem.amount_jod), 0.0),
    ).filter(
        DisbursementItem.batch_id.in_([b.id for b in batches]),
        DisbursementItem.is_included == True,   # noqa: E712
    ).group_by(DisbursementItem.batch_id).all() if batches else []
    _item_sums = {bid: (float(eur), float(jod)) for bid, eur, jod in _item_agg}
    for b in batches:
        eur, jod = _item_sums.get(b.id, (0.0, 0.0))
        if b.status == "processed":
            totals_by_currency["EUR"] += eur
            totals_by_currency["JOD"] += jod
        else:
            pending_by_currency["EUR"] += eur
            pending_by_currency["JOD"] += jod

    # track breakdown over processed batches: base EUR and actually disbursed
    # JOD come from the included items (batch-level totals can be stale);
    # batches are classified with the same title rules the repayments module
    # uses, so both screens tell the same story
    from .repayments import _classify_disbursement
    by_track = {
        "grant_I": {"eur": 0.0, "jod": 0.0, "batches": 0},
        "loan_II": {"eur": 0.0, "jod": 0.0, "batches": 0},
        "grant_II": {"eur": 0.0, "jod": 0.0, "batches": 0},
        "other": {"eur": 0.0, "jod": 0.0, "batches": 0},
    }
    jod_actual = 0.0
    processed = [b for b in batches if b.status == "processed"]
    for b in processed:
        eur, jod = _item_sums.get(b.id, (0.0, 0.0))
        jod_actual += jod
        kind, track = _classify_disbursement(b.title)
        key = f"{kind}_{track}"
        if key not in by_track:
            key = "other"
        by_track[key]["eur"] += eur
        by_track[key]["jod"] += jod
        by_track[key]["batches"] += 1

    return {
        "total_batches": total_batches,
        "draft_batches": draft_batches,
        "processed_batches": processed_batches,
        "totals_by_currency": totals_by_currency,
        "pending_by_currency": pending_by_currency,
        "jod_actual": round(jod_actual, 3),
        "by_track": by_track,
    }


# ------------------------------------------------------------------ List batches

@router.get("/disbursements/{branch_id}/")
def list_disbursements(
    branch_id: int,
    request: Request,
    ctx=Depends(require_perm("disbursements.view")),
):
    db: Session = ctx["db"]
    page, size = parse_page(request)
    q = db.query(DisbursementBatch).filter(DisbursementBatch.branch_id == branch_id)

    if program_id := request.query_params.get("program_id"):
        try:
            q = q.filter(DisbursementBatch.program_id == int(program_id))
        except ValueError:
            pass

    if status := request.query_params.get("status"):
        q = q.filter(DisbursementBatch.status == status)

    if currency := request.query_params.get("currency"):
        q = q.filter(DisbursementBatch.currency == currency.upper())

    if search := request.query_params.get("search"):
        q = q.filter(DisbursementBatch.title.ilike(f"%{search}%"))

    q = q.order_by(DisbursementBatch.payment_date.desc(), DisbursementBatch.id.desc())
    return paginate(q, page, size, lambda b: batch_ser(b, db, include_items=False))


# ------------------------------------------------------------------ Create batch

class DisbursementItemIn(BaseModel):
    business_id: int
    percentage: float = 100.0
    is_included: bool = True
    notes: str = ""
    amount: float | None = None
    amount_jod: float | None = None
    disbursement_date: date | None = None
    exchange_rate: float | None = None


class DisbursementBatchCreateIn(BaseModel):
    program_id: int
    title: str | None = None
    payment_date: date
    currency: str = "EUR"
    disbursement_currency: str = "JOD"
    exchange_rate: float = 0.76
    base_amount: float = 0.0
    notes: str = ""
    items: list[DisbursementItemIn] | None = None


def _batch_narrative(db: Session, batch: DisbursementBatch) -> str:
    """Auto-generate the narrative shown under the batch title, matching the
    style of the imported historical batches. Only used when notes are empty —
    never overwrites text written by a user."""
    items = db.query(DisbursementItem).filter(
        DisbursementItem.batch_id == batch.id).all()
    if not items:
        return ""
    received = [i for i in items if i.is_included]
    pending = [i for i in items if not i.is_included]
    prg = db.get(Program, batch.program_id)
    prog_name = prg.name if prg else ""
    t = (batch.title or "").lower()
    kind = ("prototype grant" if "prototype" in t
            else "monthly stipend" if "monthly" in t or "stipend" in t
            else "loan tranche" if "tranche" in t or "track ii" in t
            else "disbursement")
    d = batch.payment_date
    date_str = f"{d.strftime('%b')} {d.day}, {d.year}" if d else ""
    line = f"{prog_name} {kind} (paid {date_str}). {len(received)} received payment"
    if pending:
        # exclusion reason comes from each item's notes; blank notes means the
        # startup did not meet the requirements (not merely pending paperwork)
        groups = {}
        for i in pending:
            reason = (i.notes or "").strip()
            if not reason:
                reason = "did not meet the requirements"
            biz = db.get(Business, i.business_id)
            groups.setdefault(reason, []).append(biz.name if biz else "unknown")
        segs = []
        for reason, names in groups.items():
            shown = ", ".join(names[:3])
            if len(names) > 3:
                shown += f" and {len(names) - 3} more"
            segs.append(f"{len(names)} {reason.lower()} ({shown})")
        line += "; " + "; ".join(segs)
    return line + "."


@router.post("/disbursements/{branch_id}/")
def create_disbursement_batch(
    branch_id: int,
    data: DisbursementBatchCreateIn,
    ctx=Depends(require_perm("disbursements.create")),
):
    db: Session = ctx["db"]
    user = ctx["user"]

    program = db.get(Program, data.program_id)
    if not program or program.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Programme / Cohort not found in this branch.")

    currency = data.currency.upper() if data.currency else "EUR"
    if currency not in ("USD", "EUR", "JOD"):
        raise HTTPException(status_code=400, detail="Currency must be USD, EUR, or JOD.")

    rate = float(data.exchange_rate if data.exchange_rate is not None else 0.76)
    disb_curr = (data.disbursement_currency or "JOD").upper()

    title = (data.title or "").strip()
    if not title:
        month_str = data.payment_date.strftime("%B %Y")
        title = f"{program.name} — {month_str} Disbursement"

    batch = DisbursementBatch(
        branch_id=branch_id,
        program_id=data.program_id,
        title=title,
        payment_date=data.payment_date,
        currency=currency,
        disbursement_currency=disb_curr,
        exchange_rate=rate,
        base_amount=float(data.base_amount or 0.0),
        notes=data.notes or "",
        status="draft",
        created_by_id=user.id,
    )
    db.add(batch)
    db.flush()

    total_amount = 0.0
    total_amount_jod = 0.0

    if data.items is not None and len(data.items) > 0:
        for it in data.items:
            biz = db.get(Business, it.business_id)
            if not biz or biz.branch_id != branch_id:
                continue
            pct = float(it.percentage if it.percentage is not None else 100.0)
            item_amount = it.amount if it.amount is not None else (batch.base_amount * (pct / 100.0))
            item_amount = round(float(item_amount), 2)
            it_rate = float(it.exchange_rate if it.exchange_rate is not None else rate)
            it_jod = float(it.amount_jod) if it.amount_jod is not None else round(item_amount * it_rate, 3)
            it_date = it.disbursement_date or batch.payment_date
            if it.is_included:
                total_amount += item_amount
                total_amount_jod += it_jod
            item = DisbursementItem(
                batch_id=batch.id,
                business_id=biz.id,
                percentage=pct,
                amount=item_amount,
                amount_jod=it_jod,
                disbursement_date=it_date,
                exchange_rate=it_rate,
                is_included=it.is_included,
                notes=it.notes or "",
            )
            db.add(item)
    else:
        # Default: auto-populate all businesses in this cohort / program
        businesses = db.query(Business).filter(
            Business.branch_id == branch_id,
            Business.program_id == data.program_id,
        ).order_by(Business.name).all()

        for biz in businesses:
            pct = 100.0
            item_amount = round(float(batch.base_amount * (pct / 100.0)), 2)
            it_jod = round(item_amount * rate, 3)
            total_amount += item_amount
            total_amount_jod += it_jod
            item = DisbursementItem(
                batch_id=batch.id,
                business_id=biz.id,
                percentage=pct,
                amount=item_amount,
                amount_jod=it_jod,
                disbursement_date=batch.payment_date,
                exchange_rate=rate,
                is_included=True,
                notes="",
            )
            db.add(item)

    batch.total_amount = round(total_amount, 2)
    batch.total_amount_jod = round(total_amount_jod, 3)
    if not (batch.notes or "").strip():
        batch.notes = _batch_narrative(db, batch)
    db.commit()
    db.refresh(batch)

    return batch_ser(batch, db, include_items=True)


# ------------------------------------------------------------------ Export all disbursements (Excel / CSV)

@router.get("/disbursements/{branch_id}/export/")
def export_all_disbursements(
    branch_id: int,
    request: Request,
    ctx=Depends(require_perm("disbursements.view")),
):
    import csv
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    db: Session = ctx["db"]
    batches = db.query(DisbursementBatch).filter(
        DisbursementBatch.branch_id == branch_id
    ).order_by(DisbursementBatch.payment_date.desc(), DisbursementBatch.id.desc()).all()

    fmt = request.query_params.get("format", "excel").lower()

    headers = [
        "Batch ID",
        "Batch Title",
        "Cohort / Programme",
        "Startup / Business",
        "Founder Name",
        "Exact Disbursement Date",
        "Payment %",
        "Base Currency",
        "Amount (EUR)",
        "Exchange Rate (EUR/JOD)",
        "Disbursement Currency",
        "Amount (JOD)",
        "Status",
        "Notes",
    ]

    rows = []
    tot_eur = 0.0
    tot_jod = 0.0

    for b in batches:
        b_rate = float(getattr(b, "exchange_rate", None) if getattr(b, "exchange_rate", None) is not None else 0.76)
        curr = b.currency or "EUR"
        disb_curr = getattr(b, "disbursement_currency", None) or "JOD"

        for item in b.items:
            if not item.is_included:
                continue
            founders_str = ", ".join(
                f"{f.first_name} {f.last_name}".strip() for f in (item.business.founders if item.business else [])
            )
            it_date = str(getattr(item, "disbursement_date", None) or b.payment_date or "")
            it_rate = float(getattr(item, "exchange_rate", None) if getattr(item, "exchange_rate", None) is not None else b_rate)
            it_amt_eur = float(item.amount or 0.0)
            it_amt_jod = float(getattr(item, "amount_jod", None) if getattr(item, "amount_jod", None) is not None else round(it_amt_eur * it_rate, 3))
            tot_eur += it_amt_eur
            tot_jod += it_amt_jod

            rows.append([
                b.id,
                b.title,
                b.program.name if b.program else "",
                item.business.name if item.business else "—",
                founders_str,
                it_date,
                f"{item.percentage:.1f}%",
                curr,
                it_amt_eur,
                it_rate,
                disb_curr,
                it_amt_jod,
                b.status.capitalize(),
                item.notes or "",
            ])

    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["# finnspark — All Disbursements Export"])
        writer.writerow([f"# Total EUR: {tot_eur:,.2f} | Total JOD: {tot_jod:,.3f}"])
        writer.writerow(headers)
        for r in rows:
            writer.writerow(r)
        output = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
        return StreamingResponse(
            output,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=all_disbursements_report.csv"},
        )

    wb = Workbook()
    ws = wb.active
    ws.title = "All Disbursements"

    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    title_font = Font(name="Arial", size=14, bold=True)
    meta_font = Font(name="Arial", size=10, italic=True)

    ws.append(["finnspark — Comprehensive Disbursements Report"])
    ws.cell(row=1, column=1).font = title_font
    ws.append([f"Total Base Amount: €{tot_eur:,.2f} EUR | Total Disbursed: {tot_jod:,.3f} JOD | Transactions: {len(rows)}"])
    ws.cell(row=2, column=1).font = meta_font
    ws.append([])

    ws.append(headers)
    header_row_idx = 4
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=header_row_idx, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font

    for r in rows:
        ws.append(r)

    # Total row
    ws.append(["TOTAL", "", "", "", "", "", "", "", tot_eur, "", "", tot_jod, "", ""])
    last_row = ws.max_row
    total_font = Font(name="Arial", size=11, bold=True)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=last_row, column=col_idx)
        cell.font = total_font

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = col[0].column_letter
        ws.column_dimensions[col_letter].width = max(max_len + 3, 13)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=all_disbursements_report.xlsx"},
    )


# ------------------------------------------------------------------ Get single batch

@router.get("/disbursements/{branch_id}/{batch_id}/")
def get_disbursement_batch(
    branch_id: int,
    batch_id: int,
    ctx=Depends(require_perm("disbursements.view")),
):
    db: Session = ctx["db"]
    batch = db.get(DisbursementBatch, batch_id)
    if not batch or batch.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Disbursement batch not found.")

    return batch_ser(batch, db, include_items=True)


# ------------------------------------------------------------------ Update batch (draft only)

class DisbursementItemUpdateIn(BaseModel):
    id: int | None = None
    business_id: int | None = None
    percentage: float = 100.0
    is_included: bool = True
    notes: str = ""
    amount: float | None = None
    amount_jod: float | None = None
    disbursement_date: date | None = None
    exchange_rate: float | None = None


class DisbursementBatchUpdateIn(BaseModel):
    title: str | None = None
    payment_date: date | None = None
    currency: str | None = None
    disbursement_currency: str | None = None
    exchange_rate: float | None = None
    base_amount: float | None = None
    notes: str | None = None
    items: list[DisbursementItemUpdateIn] | None = None


@router.put("/disbursements/{branch_id}/{batch_id}/")
def update_disbursement_batch(
    branch_id: int,
    batch_id: int,
    data: DisbursementBatchUpdateIn,
    ctx=Depends(require_perm("disbursements.edit")),
):
    db: Session = ctx["db"]
    batch = db.get(DisbursementBatch, batch_id)
    if not batch or batch.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Disbursement batch not found.")

    if batch.status == "processed":
        raise HTTPException(
            status_code=400,
            detail="Cannot modify a processed disbursement batch. An administrator must reopen it first.",
        )

    if data.title is not None:
        batch.title = data.title.strip() or batch.title
    old_date = batch.payment_date
    if data.payment_date is not None:
        batch.payment_date = data.payment_date
    if data.currency is not None:
        curr = data.currency.upper()
        if curr not in ("USD", "EUR", "JOD"):
            raise HTTPException(status_code=400, detail="Currency must be USD, EUR, or JOD.")
        batch.currency = curr
    if data.disbursement_currency is not None:
        batch.disbursement_currency = data.disbursement_currency.upper()
    old_rate = float(batch.exchange_rate if batch.exchange_rate is not None else 0.76)
    if data.exchange_rate is not None:
        batch.exchange_rate = float(data.exchange_rate)
    if data.base_amount is not None:
        batch.base_amount = float(data.base_amount)
    if data.notes is not None:
        batch.notes = data.notes

    batch_rate = float(batch.exchange_rate if batch.exchange_rate is not None else 0.76)
    rate_changed = data.exchange_rate is not None and batch_rate != old_rate
    date_changed = data.payment_date is not None and batch.payment_date != old_date

    if data.items is not None:
        existing_items = {it.id: it for it in batch.items}
        total_amount = 0.0
        total_amount_jod = 0.0

        for item_data in data.items:
            if item_data.id and item_data.id in existing_items:
                item = existing_items[item_data.id]
                item.percentage = float(item_data.percentage)
                item.is_included = bool(item_data.is_included)
                item.notes = item_data.notes or ""
                calc_amt = item_data.amount if item_data.amount is not None else (batch.base_amount * (item.percentage / 100.0))
                item.amount = round(float(calc_amt), 2)
                if rate_changed:
                    item.exchange_rate = batch_rate
                elif item_data.exchange_rate is not None:
                    item.exchange_rate = float(item_data.exchange_rate)
                it_rate = float(item.exchange_rate if item.exchange_rate is not None else batch_rate)
                if item_data.amount_jod is not None and not rate_changed:
                    item.amount_jod = float(item_data.amount_jod)
                else:
                    item.amount_jod = round(item.amount * it_rate, 3)
                if date_changed:
                    item.disbursement_date = batch.payment_date
                elif item_data.disbursement_date is not None:
                    item.disbursement_date = item_data.disbursement_date
                elif not item.disbursement_date:
                    item.disbursement_date = batch.payment_date

                if item.is_included:
                    total_amount += item.amount
                    total_amount_jod += item.amount_jod
            elif item_data.business_id:
                biz = db.get(Business, item_data.business_id)
                if biz and biz.branch_id == branch_id:
                    pct = float(item_data.percentage)
                    calc_amt = item_data.amount if item_data.amount is not None else (batch.base_amount * (pct / 100.0))
                    calc_amt = round(float(calc_amt), 2)
                    it_rate = batch_rate if rate_changed else float(item_data.exchange_rate if item_data.exchange_rate is not None else batch_rate)
                    it_jod = round(calc_amt * it_rate, 3)
                    if item_data.amount_jod is not None and not rate_changed:
                        it_jod = float(item_data.amount_jod)
                    it_date = batch.payment_date if date_changed else (item_data.disbursement_date or batch.payment_date)
                    if item_data.is_included:
                        total_amount += calc_amt
                        total_amount_jod += it_jod
                    new_item = DisbursementItem(
                        batch_id=batch.id,
                        business_id=biz.id,
                        percentage=pct,
                        amount=calc_amt,
                        amount_jod=it_jod,
                        disbursement_date=it_date,
                        exchange_rate=it_rate,
                        is_included=item_data.is_included,
                        notes=item_data.notes or "",
                    )
                    db.add(new_item)
        batch.total_amount = round(total_amount, 2)
        batch.total_amount_jod = round(total_amount_jod, 3)
    else:
        # Recalculate based on updated base_amount and exchange_rate
        total_amount = 0.0
        total_amount_jod = 0.0
        for item in batch.items:
            item.amount = round(float(batch.base_amount * (item.percentage / 100.0)), 2)
            if rate_changed or item.exchange_rate is None:
                item.exchange_rate = batch_rate
            it_rate = float(item.exchange_rate or batch_rate)
            item.amount_jod = round(item.amount * it_rate, 3)
            if date_changed or not item.disbursement_date:
                item.disbursement_date = batch.payment_date
            if item.is_included:
                total_amount += item.amount
                total_amount_jod += item.amount_jod
        batch.total_amount = round(total_amount, 2)
        batch.total_amount_jod = round(total_amount_jod, 3)

    batch.updated_at = datetime.utcnow()
    if not (batch.notes or "").strip():
        batch.notes = _batch_narrative(db, batch)
    db.commit()
    db.refresh(batch)

    return batch_ser(batch, db, include_items=True)


# ------------------------------------------------------------------ Confirm / Process batch

@router.post("/disbursements/{branch_id}/{batch_id}/confirm/")
def confirm_disbursement_batch(
    branch_id: int,
    batch_id: int,
    ctx=Depends(require_perm("disbursements.confirm")),
):
    db: Session = ctx["db"]
    user = ctx["user"]
    batch = db.get(DisbursementBatch, batch_id)
    if not batch or batch.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Disbursement batch not found.")

    if batch.status == "processed":
        raise HTTPException(status_code=400, detail="Batch is already processed and locked.")

    batch.status = "processed"
    batch.confirmed_by_id = user.id
    batch.confirmed_at = datetime.utcnow()
    batch.updated_at = datetime.utcnow()
    if not (batch.notes or "").strip():
        batch.notes = _batch_narrative(db, batch)

    db.commit()
    db.refresh(batch)

    return {
        "detail": "Batch confirmed and processed successfully.",
        "batch": batch_ser(batch, db, include_items=True),
    }


# ------------------------------------------------------------------ Reopen batch (Admin only)

@router.post("/disbursements/{branch_id}/{batch_id}/reopen/")
def reopen_disbursement_batch(
    branch_id: int,
    batch_id: int,
    ctx=Depends(require_branch_access()),
):
    db: Session = ctx["db"]
    roles = ctx["roles"]

    # Admin check: Must have branch_admin / organization_admin or disbursements.reopen permission
    is_admin = any(r in ("branch_admin", "organization_admin", "*") for r in roles) or has_perm(roles, "disbursements.reopen")
    if not is_admin:
        raise HTTPException(
            status_code=403,
            detail="Only administrators have permission to reopen a processed disbursement batch.",
        )

    batch = db.get(DisbursementBatch, batch_id)
    if not batch or batch.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Disbursement batch not found.")

    if batch.status == "draft":
        raise HTTPException(status_code=400, detail="Batch is already in draft status.")

    batch.status = "draft"
    batch.confirmed_by_id = None
    batch.confirmed_at = None
    batch.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(batch)

    return {
        "detail": "Batch reopened successfully.",
        "batch": batch_ser(batch, db, include_items=True),
    }


# ------------------------------------------------------------------ Delete batch (draft only)

@router.delete("/disbursements/{branch_id}/{batch_id}/")
def delete_disbursement_batch(
    branch_id: int,
    batch_id: int,
    ctx=Depends(require_perm("disbursements.edit")),
):
    db: Session = ctx["db"]
    batch = db.get(DisbursementBatch, batch_id)
    if not batch or batch.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Disbursement batch not found.")

    if batch.status == "processed":
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a processed disbursement batch. Reopen it first or archive.",
        )

    db.delete(batch)
    db.commit()
    return {"detail": "Disbursement batch deleted successfully."}


# ------------------------------------------------------------------ Export batch to Excel / CSV

@router.get("/disbursements/{branch_id}/{batch_id}/export/")
def export_disbursement_batch(
    branch_id: int,
    batch_id: int,
    request: Request,
    ctx=Depends(require_perm("disbursements.view")),
):
    import csv
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    db: Session = ctx["db"]
    batch = db.get(DisbursementBatch, batch_id)
    if not batch or batch.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Disbursement batch not found.")

    curr = batch.currency or "EUR"
    disb_curr = getattr(batch, "disbursement_currency", None) or "JOD"
    rate = float(getattr(batch, "exchange_rate", None) if getattr(batch, "exchange_rate", None) is not None else 0.76)
    tot_eur = float(batch.total_amount or 0.0)
    tot_jod = float(getattr(batch, "total_amount_jod", None) if getattr(batch, "total_amount_jod", None) is not None else round(tot_eur * rate, 3))

    fmt = request.query_params.get("format", "excel").lower()

    headers = [
        "Startup / Business",
        "Founders",
        "Exact Disbursement Date",
        "Payment %",
        f"Base Amount ({curr})",
        f"Exchange Rate ({curr} to {disb_curr})",
        f"Disbursement Amount ({disb_curr})",
        "Included in Batch",
        "Remarks / Notes",
    ]

    rows = []
    for item in batch.items:
        founders_str = ", ".join(
            f"{f.first_name} {f.last_name}".strip() for f in (item.business.founders if item.business else [])
        )
        it_date = str(getattr(item, "disbursement_date", None) or batch.payment_date or "")
        it_rate = float(getattr(item, "exchange_rate", None) if getattr(item, "exchange_rate", None) is not None else rate)
        it_jod = float(getattr(item, "amount_jod", None) if getattr(item, "amount_jod", None) is not None else round((item.amount or 0.0) * it_rate, 3))
        rows.append([
            item.business.name if item.business else "—",
            founders_str,
            it_date,
            f"{item.percentage:.1f}%",
            float(item.amount or 0.0),
            it_rate,
            it_jod,
            "Yes" if item.is_included else "No",
            item.notes or "",
        ])

    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([f"# finnspark — {batch.title}"])
        writer.writerow([f"# Payment Date: {batch.payment_date} | Rate: 1 {curr} = {rate} {disb_curr} | Total: {tot_eur:,.2f} {curr} ({tot_jod:,.3f} {disb_curr})"])
        writer.writerow(headers)
        for r in rows:
            writer.writerow(r)
        writer.writerow(["TOTAL", "", "", "", tot_eur, rate, tot_jod, f"{sum(1 for i in batch.items if i.is_included)} / {len(batch.items)} startups", ""])
        output = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
        filename = f"disbursement_{batch.id}_{batch.payment_date}.csv"
        return StreamingResponse(
            output,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    # Excel export
    wb = Workbook()
    ws = wb.active
    ws.title = "Disbursement Batch"

    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    title_font = Font(name="Arial", size=14, bold=True)
    meta_font = Font(name="Arial", size=10, italic=True)

    ws.append([f"finnspark — {batch.title}"])
    ws.cell(row=1, column=1).font = title_font
    ws.append([f"Programme / Cohort: {batch.program.name if batch.program else '—'}"])
    ws.cell(row=2, column=1).font = meta_font
    ws.append([
        f"Payment Date: {batch.payment_date} | Base: {curr} | Disbursement: {disb_curr} | Rate: 1 {curr} = {rate} {disb_curr} | Total: {tot_eur:,.2f} {curr} ({tot_jod:,.3f} {disb_curr})"
    ])
    ws.cell(row=3, column=1).font = meta_font
    ws.append([])

    ws.append(headers)
    header_row_idx = 5
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=header_row_idx, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center" if col_idx in (3, 4, 5, 6, 7, 8) else "left", vertical="center")

    for r in rows:
        ws.append(r)

    # Summary Row
    summary_row = [
        "TOTAL COHORT DISBURSEMENT",
        "",
        "",
        "",
        tot_eur,
        rate,
        tot_jod,
        f"{sum(1 for i in batch.items if i.is_included)} / {len(batch.items)} startups",
        "",
    ]
    ws.append(summary_row)
    last_row = ws.max_row
    total_font = Font(name="Arial", size=11, bold=True)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=last_row, column=col_idx)
        cell.font = total_font

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = col[0].column_letter
        ws.column_dimensions[col_letter].width = max(max_len + 3, 14)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"disbursement_{batch.id}_{batch.payment_date}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )



