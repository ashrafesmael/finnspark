import io
import csv
import re
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_

from ..database import get_db
from ..deps import has_perm, require_branch_access, require_perm
from ..models import (
    Branch, Business, BusinessFounder, FinanceTimelineEntry,
    InvestmentCase, LoanRepayment, PaymentScheduleEntry, Program, User,
    DisbursementBatch, DisbursementItem, RepaymentBatch,
)

router = APIRouter(tags=["loan_repayments"])



def _display_names(biz: Business, case=None) -> dict:
    """English trading name (for businesses registered under a non-latin name)
    and the entrepreneur behind the startup (founder, else the case's CEO)."""
    founder = next(iter(biz.founders or []), None)
    entrepreneur = (f"{founder.first_name} {founder.last_name}".strip()
                    if founder else (case.ceo_name if case else "")) or ""
    return {
        "business_name_en": (biz.name_en or "").strip() or None,
        "entrepreneur": entrepreneur,
    }

def repayment_ser(r: LoanRepayment, db: Session) -> dict:
    biz = r.business
    prg = biz.program if biz else None
    user = r.recorded_by

    rate = float(r.exchange_rate if r.exchange_rate is not None else 0.76)
    amt_eur = float(r.amount or 0.0)
    amt_jod = float(r.amount_jod if r.amount_jod is not None else round(amt_eur * rate, 3))
    princ_amt = float(r.principal_amount if r.principal_amount is not None else amt_eur)
    int_amt = float(r.interest_amount if r.interest_amount is not None else 0.0)

    return {
        "id": r.id,
        "branch_id": r.branch_id,
        "business_id": r.business_id,
        "business_name": biz.name if biz else "—",
        **(_display_names(biz, r.case) if biz else {"business_name_en": None, "entrepreneur": ""}),
        "program_id": prg.id if prg else None,
        "program_name": prg.name if prg else None,
        "case_id": r.case_id,
        "schedule_entry_id": r.schedule_entry_id,
        "payment_date": str(r.payment_date) if r.payment_date else None,
        "amount": amt_eur,
        "amount_eur": amt_eur,
        "amount_jod": amt_jod,
        "currency": r.currency or "EUR",
        "disbursement_currency": r.disbursement_currency or "JOD",
        "exchange_rate": rate,
        "principal_amount": princ_amt,
        "interest_amount": int_amt,
        "payment_method": r.payment_method or "Bank Transfer",
        "reference_number": r.reference_number or "",
        "batch_id": r.batch_id,
        "loan_number": r.loan_number or "",
        "cohort": r.cohort or "",
        "payer_name": r.payer_name or "",
        "channel": r.channel or "",
        "instalment_label": r.instalment_label or "",
        "verified_against": r.verified_against or "",
        "verified": bool(r.verified),
        "entry_type": r.entry_type or "installment",
        "status": r.status or "completed",
        "notes": r.notes or "",
        "receipt_url": r.receipt_url,
        "recorded_by": {
            "id": user.id,
            "name": f"{user.first_name} {user.last_name}".strip() or user.email,
        } if user else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


# ------------------------------------------------------------------ Summary KPIs

@router.get("/repayments/{branch_id}/summary/")
def repayments_summary(
    branch_id: int,
    program_id: Optional[int] = None,
    business_id: Optional[int] = None,
    ctx=Depends(require_perm("repayments.view")),
):
    db: Session = ctx["db"]

    q = db.query(InvestmentCase).filter(
        InvestmentCase.branch_id == branch_id,
        InvestmentCase.investment_amount > 0,
    )
    if program_id:
        q = q.join(Business, Business.id == InvestmentCase.business_id).filter(
            Business.program_id == program_id)
    if business_id:
        q = q.filter(InvestmentCase.business_id == business_id)
    cases = q.all()
    total_approved_eur = sum(float(c.investment_amount or 0.0) for c in cases)
    rate_def = 0.76
    total_approved_jod = round(total_approved_eur * rate_def, 3)

    processed_ids = _counted_batch_ids(db, branch_id)
    case_ids = {c.id for c in cases}
    # scope repayments to the filtered cases; but when a programme/startup
    # filter matched no cases at all, nothing was borrowed in that scope and
    # the collected totals must be zero -- not the whole book's repayments
    scoped = bool(program_id or business_id)
    repayments = [r for r in db.query(LoanRepayment).filter(
        LoanRepayment.branch_id == branch_id).all()
        if _counts_toward_balance(r, processed_ids)
        and (r.case_id in case_ids if (case_ids or scoped) else True)]

    total_repaid_eur = sum(float(r.amount or 0.0) for r in repayments)
    total_repaid_jod = sum(float(r.amount_jod or round((r.amount or 0.0) * (r.exchange_rate or rate_def), 3)) for r in repayments)
    total_collected_eur = round(total_repaid_eur, 2)

    # collected / outstanding in BOTH currencies: the schedule lives in the
    # loan's own currency (JOD for most loans, EUR for BabPlus), so each case
    # contributes its native figures and converts to the other at the loan's
    # own disbursement rate -- never a flat portfolio rate.
    disbursed_eur = sum(float(c.disbursement_amount or 0.0) for c in cases)
    disbursed_jod = 0.0
    principal_collected_eur = charges_collected_eur = 0.0
    principal_collected_jod = charges_collected_jod = 0.0
    principal_out_eur = charges_out_eur = 0.0
    principal_out_jod = charges_out_jod = 0.0
    pos_all = _portfolio_positions(db, branch_id)
    for c in cases:
        p_all = pos_all.get(c.id, {})
        entries = p_all.get("entries", [])
        case_reps = [r for r in repayments if r.case_id == c.id]
        pos = _case_repay_position(c, case_reps, entries)
        sccy = pos["sched_ccy"]
        rate = pos["rate"]
        to_eur = (lambda v: v) if sccy == "EUR" else (lambda v: v / rate if rate else 0.0)
        to_jod = (lambda v: v * rate) if sccy == "EUR" else (lambda v: v)
        if sccy == "EUR":
            disbursed_jod += float(c.disbursement_amount or 0.0) * rate
        else:
            disbursed_jod += float(c.disbursement_amount_jod or 0.0)
        if case_reps:
            principal_collected_eur += to_eur(pos["settled_principal_i"])
            charges_collected_eur += to_eur(pos["settled_charges_i"])
            principal_collected_jod += to_jod(pos["settled_principal_i"])
            charges_collected_jod += to_jod(pos["settled_charges_i"])
        principal_out_eur += to_eur(pos["principal_out_i"])
        charges_out_eur += to_eur(pos["charges_out_i"])
        principal_out_jod += to_jod(pos["principal_out_i"])
        charges_out_jod += to_jod(pos["charges_out_i"])

    principal_collected_eur = round(principal_collected_eur, 2)
    charges_collected_eur = round(charges_collected_eur, 2)
    principal_collected_jod = round(principal_collected_jod, 3)
    charges_collected_jod = round(charges_collected_jod, 3)
    principal_out_eur = round(principal_out_eur, 2)
    incl_out_eur = round(principal_out_eur + charges_out_eur, 2)
    principal_out_jod = round(principal_out_jod, 2)
    incl_out_jod = round(principal_out_jod + charges_out_jod, 2)
    recovery_rate = round(100.0 * principal_collected_eur / disbursed_eur, 1) if disbursed_eur > 0 else 0.0

    distinct_borrowers = len(set(c.business_id for c in cases if c.business_id))

    return {
        "total_approved_eur": total_approved_eur,
        "total_approved_jod": total_approved_jod,
        "total_disbursed_eur": round(disbursed_eur, 2),
        "total_repaid_eur": total_collected_eur,
        "total_repaid_jod": round(total_repaid_jod, 3),
        "principal_collected_eur": principal_collected_eur,
        "charges_collected_eur": charges_collected_eur,
        "outstanding_principal_eur": principal_out_eur,
        "outstanding_incl_charges_eur": incl_out_eur,
        "outstanding_charges_eur": round(charges_out_eur, 2),
        "total_disbursed_jod": round(disbursed_jod, 3),
        "outstanding_principal_jod": principal_out_jod,
        "outstanding_incl_charges_jod": incl_out_jod,
        "principal_collected_jod": principal_collected_jod,
        "charges_collected_jod": charges_collected_jod,
        # compat: outstanding_eur remains the principal-only view
        "outstanding_eur": principal_out_eur,
        "outstanding_jod": principal_out_jod,
        "recovery_rate_pct": recovery_rate,
        "total_repayments_count": len(repayments),
        "active_borrowers_count": distinct_borrowers,
        "currency": "EUR",
        "disbursement_currency": "JOD",
    }


# ------------------------------------------------------------------ Loans Overview Directory

@router.get("/repayments/{branch_id}/loans-overview/")
def loans_overview(
    branch_id: int,
    program_id: Optional[int] = None,
    business_id: Optional[int] = None,
    ctx=Depends(require_perm("repayments.view")),
):
    db: Session = ctx["db"]
    q = db.query(InvestmentCase).filter(
        InvestmentCase.branch_id == branch_id,
        InvestmentCase.investment_amount > 0,
    )
    if program_id:
        q = q.join(Business, Business.id == InvestmentCase.business_id).filter(
            Business.program_id == program_id)
    if business_id:
        q = q.filter(InvestmentCase.business_id == business_id)
    cases = q.order_by(InvestmentCase.company_name).all()

    processed_ids = _counted_batch_ids(db, branch_id)
    all_repayments = db.query(LoanRepayment).filter(
        LoanRepayment.branch_id == branch_id,
    ).order_by(LoanRepayment.payment_date.desc()).all()

    repay_by_biz = {}
    for r in all_repayments:
        if _counts_toward_balance(r, processed_ids):
            repay_by_biz.setdefault(r.business_id, []).append(r)

    rows = []
    for c in cases:
        biz = db.get(Business, c.business_id) if c.business_id else None
        b_repayments = repay_by_biz.get(c.business_id, [])
        total_repaid_eur = sum(float(r.amount or 0.0) for r in b_repayments)
        rate = float(c.forex_rate if (c.forex_rate and c.forex_rate != 1.0) else 0.76)
        total_repaid_jod = sum(float(r.amount_jod or round((r.amount or 0.0) * rate, 3)) for r in b_repayments)
        approved_eur = float(c.investment_amount or 0.0)
        approved_jod = round(approved_eur * rate, 3)
        disb_eur = float(c.disbursement_amount or 0.0)
        disb_jod = float(c.disbursement_amount_jod or 0.0)

        # repayable position from the schedule: instalments carry interest and
        # fees, so outstanding is tracked principal-only AND incl. charges
        entries = db.query(PaymentScheduleEntry).filter(
            PaymentScheduleEntry.case_id == c.id).all()
        pos = _case_repay_position(c, b_repayments, entries)
        outstanding_principal_eur = pos["principal_out_eur"]
        outstanding_incl_eur = pos["incl_out_eur"]
        principal_out_i = pos["principal_out_i"]

        _entries0 = db.query(PaymentScheduleEntry).filter(
            PaymentScheduleEntry.case_id == c.id).first()
        _sched_ccy = (_entries0.currency or "").upper() if _entries0 else ""
        _disb_sched_ccy = (float(c.disbursement_amount or 0.0) if _sched_ccy == "EUR"
                           else disb_jod)
        pct_repaid = round(100.0 * pos["settled_principal_i"] / _disb_sched_ccy, 1) \
            if _disb_sched_ccy > 0 else 0.0
        last_date = str(b_repayments[0].payment_date) if b_repayments else None

        rows.append({
            "case_id": c.id,
            "business_id": c.business_id,
            "company_name": (biz.name if biz else None) or c.company_name or "—",
            **(_display_names(biz, c) if biz else {"company_name_en": None, "entrepreneur": ""}),
            "program_id": biz.program_id if biz else None,
            "program_name": biz.program.name if (biz and biz.program) else "—",
            "ceo_name": c.ceo_name or "",
            "loan_approved_eur": approved_eur,
            "loan_approved_jod": approved_jod,
            "co_financing_grant_eur": float(c.co_financing_amount or 0.0),
            "currency": c.currency or "EUR",
            "disbursement_currency": "JOD",
            "exchange_rate": rate,
            "disbursed_eur": disb_eur,
            "disbursed_jod": disb_jod,
            "total_repaid_eur": round(total_repaid_eur, 2),
            "total_repaid_jod": round(total_repaid_jod, 3),
            "expected_total_eur": pos["expected_eur"],
            "outstanding_principal_eur": outstanding_principal_eur,
            "outstanding_principal_jod": round(pos["principal_out_i"], 2),
            "outstanding_incl_charges_eur": outstanding_incl_eur,
            "outstanding_incl_charges_jod": round(pos["incl_out_i"], 2),
            "pct_repaid": min(100.0, pct_repaid),
            "repayments_count": len(b_repayments),
            "last_payment_date": last_date,
            "status": "fully_repaid" if (principal_out_i <= 0.01 and total_repaid_eur > 0) else "active",
        })

    return {"results": rows, "count": len(rows)}


# ------------------------------------------------------------------ Repayment List (Paginated)

@router.get("/repayments/{branch_id}/")
def list_repayments(
    branch_id: int,
    business_id: Optional[int] = None,
    program_id: Optional[int] = None,
    status: Optional[str] = None,
    payment_method: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=200),
    ctx=Depends(require_perm("repayments.view")),
):
    db: Session = ctx["db"]
    q = db.query(LoanRepayment).join(Business, Business.id == LoanRepayment.business_id).filter(
        LoanRepayment.branch_id == branch_id
    )

    if business_id:
        q = q.filter(LoanRepayment.business_id == business_id)
    if program_id:
        q = q.filter(Business.program_id == program_id)
    if status:
        q = q.filter(LoanRepayment.status == status)
    if payment_method:
        q = q.filter(LoanRepayment.payment_method == payment_method)
    if date_from:
        q = q.filter(LoanRepayment.payment_date >= date_from)
    if date_to:
        q = q.filter(LoanRepayment.payment_date <= date_to)
    if search:
        s = f"%{search.strip()}%"
        q = q.filter(
            or_(
                Business.name.ilike(s),
                LoanRepayment.reference_number.ilike(s),
                LoanRepayment.notes.ilike(s),
            )
        )

    total_count = q.count()
    items = q.order_by(LoanRepayment.payment_date.desc(), LoanRepayment.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "results": [repayment_ser(it, db) for it in items],
        "count": total_count,
        "page": page,
        "page_size": page_size,
    }


# ------------------------------------------------------------------ Create Repayment

class RepaymentCreateIn(BaseModel):
    business_id: int
    case_id: Optional[int] = None
    schedule_entry_id: Optional[int] = None
    payment_date: date
    amount: float
    currency: str = "EUR"
    disbursement_currency: str = "JOD"
    exchange_rate: float = 0.76
    principal_amount: Optional[float] = None
    interest_amount: float = 0.0
    payment_method: str = "Bank Transfer"
    reference_number: str = ""
    status: str = "completed"
    notes: str = ""
    receipt_url: Optional[str] = None


@router.post("/repayments/{branch_id}/")
def create_repayment(
    branch_id: int,
    data: RepaymentCreateIn,
    ctx=Depends(require_perm("repayments.create")),
):
    db: Session = ctx["db"]
    user = ctx["user"]

    biz = db.get(Business, data.business_id)
    if not biz or biz.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Startup / Business not found in this branch.")

    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="Repayment amount must be greater than zero.")

    rate = float(data.exchange_rate if data.exchange_rate is not None else 0.76)
    amt_eur = float(data.amount)
    amt_jod = round(amt_eur * rate, 3)

    int_amt = float(data.interest_amount or 0.0)
    princ_amt = float(data.principal_amount) if data.principal_amount is not None else max(0.0, amt_eur - int_amt)

    case_id = data.case_id
    if not case_id:
        case = db.query(InvestmentCase).filter(
            InvestmentCase.branch_id == branch_id,
            InvestmentCase.business_id == biz.id,
        ).first()
        if case:
            case_id = case.id

    repay = LoanRepayment(
        branch_id=branch_id,
        business_id=biz.id,
        case_id=case_id,
        schedule_entry_id=data.schedule_entry_id,
        payment_date=data.payment_date,
        amount=amt_eur,
        currency=(data.currency or "EUR").upper(),
        disbursement_currency=(data.disbursement_currency or "JOD").upper(),
        exchange_rate=rate,
        amount_jod=amt_jod,
        principal_amount=princ_amt,
        interest_amount=int_amt,
        payment_method=(data.payment_method or "Bank Transfer").strip(),
        reference_number=(data.reference_number or "").strip(),
        status=(data.status or "completed").strip().lower(),
        notes=(data.notes or "").strip(),
        receipt_url=data.receipt_url,
        recorded_by_id=user.id if user else None,
        created_at=datetime.utcnow(),
    )
    db.add(repay)
    db.flush()

    if case_id and repay.status == "completed":
        ref_text = f" (Ref: {repay.reference_number})" if repay.reference_number else ""
        db.add(FinanceTimelineEntry(
            case_id=case_id,
            entry_date=repay.payment_date,
            label=f"Loan Repayment: {biz.name}{ref_text}",
            amount=repay.amount,
            direction="in",
        ))

    if data.schedule_entry_id:
        sch = db.get(PaymentScheduleEntry, data.schedule_entry_id)
        if sch and sch.case_id == case_id:
            sch.paid = True
            sch.paid_date = repay.payment_date

    db.commit()
    db.refresh(repay)
    return repayment_ser(repay, db)


# ------------------------------------------------------------------ Export (Excel / CSV)

@router.get("/repayments/{branch_id}/export/")
def export_repayments(
    request: Request,
    branch_id: int,
    ctx=Depends(require_perm("repayments.view")),
):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    db: Session = ctx["db"]
    branch = db.get(Branch, branch_id)
    repayments = db.query(LoanRepayment).join(
        Business, Business.id == LoanRepayment.business_id
    ).filter(
        LoanRepayment.branch_id == branch_id
    ).order_by(LoanRepayment.payment_date.desc(), LoanRepayment.id.desc()).all()

    fmt = request.query_params.get("format", "excel").lower()

    headers = [
        "Payment Date",
        "Startup / Business",
        "Cohort / Programme",
        "Base Amount (EUR)",
        "Exchange Rate (EUR/JOD)",
        "Repayment Amount (JOD)",
        "Principal (EUR)",
        "Interest (EUR)",
        "Payment Method",
        "Reference / Receipt #",
        "Status",
        "Recorded By",
        "Notes",
    ]

    rows = []
    for r in repayments:
        biz = r.business
        prg = biz.program if biz else None
        user = r.recorded_by
        u_name = f"{user.first_name} {user.last_name}".strip() if user else ""
        rate = float(r.exchange_rate or 0.76)
        amt_eur = float(r.amount or 0.0)
        amt_jod = float(r.amount_jod or round(amt_eur * rate, 3))
        princ = float(r.principal_amount if r.principal_amount is not None else amt_eur)
        interest = float(r.interest_amount or 0.0)

        rows.append([
            str(r.payment_date or ""),
            biz.name if biz else "—",
            prg.name if prg else "—",
            amt_eur,
            rate,
            amt_jod,
            princ,
            interest,
            r.payment_method or "Bank Transfer",
            r.reference_number or "",
            (r.status or "completed").capitalize(),
            u_name,
            r.notes or "",
        ])

    tot_eur = sum(r[3] for r in rows)
    tot_jod = sum(r[5] for r in rows)
    tot_princ = sum(r[6] for r in rows)
    tot_int = sum(r[7] for r in rows)

    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        bname = branch.name if branch else f"Branch {branch_id}"
        writer.writerow([f"# finnspark — Loan Repayments & Recoveries Report ({bname})"])
        writer.writerow([f"# Exported on: {date.today()} | Total Collected: €{tot_eur:,.2f} ({tot_jod:,.3f} JOD) across {len(rows)} payments"])
        writer.writerow(headers)
        for r in rows:
            writer.writerow(r)
        writer.writerow(["TOTAL", f"{len(rows)} transactions", "", tot_eur, 0.76, tot_jod, tot_princ, tot_int, "", "", "", "", ""])

        output = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
        filename = f"loan_repayments_{branch_id}_{date.today()}.csv"
        return StreamingResponse(
            output,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    wb = Workbook()
    ws = wb.active
    ws.title = "Loan Repayments"

    bname = branch.name if branch else f"Branch {branch_id}"
    ws.merge_cells("A1:M1")
    ws["A1"] = f"finnspark — Loan Repayments & Recoveries Audit Report ({bname})"
    ws["A1"].font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    ws["A1"].fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    ws["A1"].alignment = Alignment(horizontal="left", vertical="center", indent=1)

    ws.merge_cells("A2:M2")
    ws["A2"] = f"Exported: {date.today().strftime('%d %B %Y')} | Total Collected: €{tot_eur:,.2f} ({tot_jod:,.3f} JOD) across {len(rows)} transactions"
    ws["A2"].font = Font(name="Calibri", size=10, italic=True, color="475569")
    ws["A2"].fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
    ws["A2"].alignment = Alignment(horizontal="left", vertical="center", indent=1)

    ws.row_dimensions[4].height = 24
    header_fill = PatternFill(start_color="0F766E", end_color="0F766E", fill_type="solid")
    header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col_idx, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center" if col_idx in (1, 5, 9, 10, 11) else "left", vertical="center")

    for row_idx, r in enumerate(rows, 5):
        ws.row_dimensions[row_idx].height = 20
        for col_idx, val in enumerate(r, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            if col_idx in (4, 7, 8):
                cell.number_format = "#,##0.00"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif col_idx == 5:
                cell.number_format = "0.0000"
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx == 6:
                cell.number_format = "#,##0.000"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif col_idx in (1, 9, 10, 11):
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    tot_row = len(rows) + 5
    ws.row_dimensions[tot_row].height = 22
    summary_fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
    summary_font = Font(name="Calibri", size=10, bold=True)
    for c in range(1, 14):
        ws.cell(row=tot_row, column=c).fill = summary_fill
        ws.cell(row=tot_row, column=c).font = summary_font

    ws.cell(row=tot_row, column=1, value="TOTAL")
    ws.cell(row=tot_row, column=2, value=f"{len(rows)} transactions")
    c4 = ws.cell(row=tot_row, column=4, value=tot_eur)
    c4.number_format = "#,##0.00"
    c4.alignment = Alignment(horizontal="right", vertical="center")
    c6 = ws.cell(row=tot_row, column=6, value=tot_jod)
    c6.number_format = "#,##0.000"
    c6.alignment = Alignment(horizontal="right", vertical="center")
    c7 = ws.cell(row=tot_row, column=7, value=tot_princ)
    c7.number_format = "#,##0.00"
    c7.alignment = Alignment(horizontal="right", vertical="center")
    c8 = ws.cell(row=tot_row, column=8, value=tot_int)
    c8.number_format = "#,##0.00"
    c8.alignment = Alignment(horizontal="right", vertical="center")

    col_widths = [14, 28, 22, 16, 15, 18, 16, 14, 16, 20, 14, 20, 26]
    for i, w in enumerate(col_widths, 1):
        from openpyxl.utils import get_column_letter
        ws.column_dimensions[get_column_letter(i)].width = w

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"loan_repayments_{branch_id}_{date.today()}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ------------------------------------------------------------------ Import Template (Excel)

@router.get("/repayments/{branch_id}/import-template/")
def download_repayment_template(
    branch_id: int,
    ctx=Depends(require_perm("repayments.view")),
):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    db: Session = ctx["db"]
    branch = db.get(Branch, branch_id)
    bname = branch.name if branch else f"Branch {branch_id}"

    wb = Workbook()

    # Sheet 1: Template
    ws = wb.active
    ws.title = "Repayment Import"

    # Title Banner
    ws.merge_cells("A1:H1")
    ws["A1"] = f"finnspark — Startup Loan Repayments Bulk Import Template ({bname})"
    ws["A1"].font = Font(name="Calibri", size=13, bold=True, color="FFFFFF")
    ws["A1"].fill = PatternFill(start_color="0D9488", end_color="0D9488", fill_type="solid")
    ws["A1"].alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[1].height = 28

    ws.merge_cells("A2:H2")
    ws["A2"] = "Fill in the repayments below. Required columns are marked with *. Accepted formats: Date (YYYY-MM-DD or DD/MM/YYYY), Amount (numbers in EUR)."
    ws["A2"].font = Font(name="Calibri", size=9, italic=True, color="475569")
    ws["A2"].fill = PatternFill(start_color="F0FDFA", end_color="F0FDFA", fill_type="solid")
    ws["A2"].alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[2].height = 20

    template_headers = [
        "Startup / Business Name *",
        "Payment Date *",
        "Amount (EUR) *",
        "FX Rate (EUR/JOD)",
        "Payment Method",
        "Reference / Receipt #",
        "Principal Portion (EUR)",
        "Notes",
    ]

    ws.row_dimensions[4].height = 24
    header_fill = PatternFill(start_color="134E4A", end_color="134E4A", fill_type="solid")
    header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    thin_border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )

    for col_idx, h in enumerate(template_headers, 1):
        cell = ws.cell(row=4, column=col_idx, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center" if col_idx in (2, 4, 5, 6) else "left", vertical="center")
        cell.border = thin_border

    # Pre-fill active borrowers in this branch
    cases = db.query(InvestmentCase).filter(
        InvestmentCase.branch_id == branch_id,
        InvestmentCase.investment_amount > 0,
    ).order_by(InvestmentCase.company_name).all()

    row_num = 5
    today_str = str(date.today())
    for c in cases:
        biz = db.get(Business, c.business_id) if c.business_id else None
        cname = (biz.name if biz else None) or c.company_name or ""
        rate = float(c.forex_rate if (c.forex_rate and c.forex_rate != 1.0) else 0.76)

        ws.row_dimensions[row_num].height = 20
        ws.cell(row=row_num, column=1, value=cname)
        ws.cell(row=row_num, column=2, value=today_str)
        ws.cell(row=row_num, column=3, value=None) # User enters amount
        c4 = ws.cell(row=row_num, column=4, value=rate)
        c4.number_format = "0.0000"
        ws.cell(row=row_num, column=5, value="Bank Transfer")
        ws.cell(row=row_num, column=6, value="")
        ws.cell(row=row_num, column=7, value=None)
        ws.cell(row=row_num, column=8, value="")

        for c_idx in range(1, 9):
            ws.cell(row=row_num, column=c_idx).border = thin_border

        row_num += 1

    widths = [32, 16, 18, 18, 18, 22, 22, 30]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # Sheet 2: Guide & Instructions
    ws_guide = wb.create_sheet(title="Guide & Reference")
    ws_guide.column_dimensions["A"].width = 24
    ws_guide.column_dimensions["B"].width = 60

    ws_guide.cell(row=1, column=1, value="Column").font = Font(bold=True)
    ws_guide.cell(row=1, column=2, value="Instructions & Allowed Values").font = Font(bold=True)

    guide_rows = [
        ("Startup / Business Name *", "Exact startup name or partial name matching a startup in this branch."),
        ("Payment Date *", "Date when the payment was received (e.g. 2026-06-15 or 15/06/2026)."),
        ("Amount (EUR) *", "The repayment amount in EUR (number greater than zero, e.g. 2500.00)."),
        ("FX Rate (EUR/JOD)", "Optional exchange rate from EUR to JOD. Defaults to 0.7600 if left blank."),
        ("Payment Method", "Allowed: Bank Transfer, Cheque, Cash, Deposit Slip, Mobile Wallet, Other (defaults to Bank Transfer)."),
        ("Reference / Receipt #", "Transaction reference number, bank receipt ID, or cheque number."),
        ("Principal Portion (EUR)", "Optional principal amount. If left blank, the entire amount is treated as principal."),
        ("Notes", "Optional comments or notes regarding this payment tranche."),
    ]
    for g_idx, (col_name, desc_text) in enumerate(guide_rows, 2):
        ws_guide.cell(row=g_idx, column=1, value=col_name).font = Font(bold=True)
        ws_guide.cell(row=g_idx, column=2, value=desc_text)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"loan_repayments_import_template_{branch_id}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ------------------------------------------------------------------ Helper Parsers

def _parse_excel_date(v):
    if not v:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y", "%d.%m.%Y", "%Y.%m.%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    if len(s) >= 10:
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        except ValueError:
            pass
    return None


def _parse_num(v, default=0.0):
    if v is None or v == "":
        return default
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace("€", "").replace("$", "").replace("JOD", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return default


# ------------------------------------------------------------------ Import Repayments

@router.post("/repayments/{branch_id}/import/")
async def import_repayments(
    branch_id: int,
    file: UploadFile = File(...),
    ctx=Depends(require_perm("repayments.create")),
):
    import openpyxl
    db: Session = ctx["db"]
    user = ctx["user"]

    contents = await file.read()
    fname = (file.filename or "").lower()

    raw_rows = []
    if fname.endswith(".csv"):
        try:
            text = contents.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = contents.decode("latin-1")
        reader = csv.reader(io.StringIO(text))
        for r in reader:
            if any(c.strip() for c in r):
                raw_rows.append(r)
    else:
        try:
            wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True)
            ws = wb.active
            for row in ws.iter_rows(values_only=True):
                if row and any(c is not None and str(c).strip() for c in row):
                    raw_rows.append(list(row))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to read Excel spreadsheet: {str(e)}")

    if not raw_rows:
        raise HTTPException(status_code=400, detail="The uploaded spreadsheet is empty.")

    # Locate header row (look for 'startup', 'business', 'company', 'amount', 'date')
    header_idx = -1
    col_map = {}
    for idx, row in enumerate(raw_rows[:10]):
        row_str = [str(c).lower().strip() if c is not None else "" for c in row]
        if any("startup" in c or "business" in c or "company" in c for c in row_str) and \
           any("amount" in c or "eur" in c for c in row_str):
            header_idx = idx
            for col_i, h in enumerate(row_str):
                if any(k in h for k in ("startup", "business", "company")):
                    col_map["business"] = col_i
                elif any(k in h for k in ("payment date", "date")):
                    col_map["date"] = col_i
                elif any(k in h for k in ("amount (eur)", "amount", "repayment amount", "base amount")):
                    col_map["amount"] = col_i
                elif any(k in h for k in ("rate", "fx", "forex")):
                    col_map["fx"] = col_i
                elif any(k in h for k in ("method", "payment method")):
                    col_map["method"] = col_i
                elif any(k in h for k in ("reference", "receipt", "ref", "trx")):
                    col_map["ref"] = col_i
                elif any(k in h for k in ("principal",)):
                    col_map["principal"] = col_i
                elif any(k in h for k in ("notes", "note", "description", "memo")):
                    col_map["notes"] = col_i
            break

    if header_idx == -1 or "business" not in col_map or "amount" not in col_map:
        # Fallback default columns
        col_map = {"business": 0, "date": 1, "amount": 2, "fx": 3, "method": 4, "ref": 5, "principal": 6, "notes": 7}
        header_idx = 0 if any(str(c).replace(".", "").isdigit() for c in raw_rows[0][2:4]) else 1

    # Load all branch businesses for matching
    businesses = db.query(Business).filter(Business.branch_id == branch_id).all()
    biz_by_name = {b.name.strip().lower(): b for b in businesses}

    cases = db.query(InvestmentCase).filter(InvestmentCase.branch_id == branch_id).all()
    case_by_biz_id = {c.business_id: c for c in cases if c.business_id}

    imported_count = 0
    updated_count = 0
    skipped_count = 0
    total_eur = 0.0
    total_jod = 0.0
    errors = []

    for r_idx, row in enumerate(raw_rows[header_idx + 1:], start=header_idx + 2):
        if not row or not any(c is not None and str(c).strip() for c in row):
            continue

        b_val = row[col_map["business"]] if col_map.get("business", -1) < len(row) else None
        if not b_val or not str(b_val).strip():
            skipped_count += 1
            continue

        biz_name_clean = str(b_val).strip()
        # Find matching business
        biz = biz_by_name.get(biz_name_clean.lower())
        if not biz:
            # Try fuzzy/substring match
            for b_name, b_obj in biz_by_name.items():
                if b_name in biz_name_clean.lower() or biz_name_clean.lower() in b_name:
                    biz = b_obj
                    break

        if not biz:
            errors.append(f"Row {r_idx}: Startup '{biz_name_clean}' not found in branch.")
            continue

        # Amount
        amt_raw = row[col_map["amount"]] if col_map.get("amount", -1) < len(row) else None
        amt_eur = _parse_num(amt_raw, 0.0)
        if amt_eur <= 0:
            errors.append(f"Row {r_idx}: Invalid repayment amount for '{biz.name}'. Must be greater than 0.")
            continue

        # Date
        date_raw = row[col_map.get("date", 1)] if col_map.get("date", -1) < len(row) else None
        pay_date = _parse_excel_date(date_raw) or date.today()

        # FX Rate
        fx_raw = row[col_map.get("fx", 3)] if col_map.get("fx", -1) < len(row) else None
        rate = _parse_num(fx_raw, 0.76)
        if rate <= 0:
            rate = 0.76

        # Method
        method_raw = row[col_map.get("method", 4)] if col_map.get("method", -1) < len(row) else None
        method = str(method_raw).strip() if method_raw else "Bank Transfer"

        # Reference
        ref_raw = row[col_map.get("ref", 5)] if col_map.get("ref", -1) < len(row) else None
        ref = str(ref_raw).strip() if ref_raw is not None else ""

        # Principal & Interest
        princ_raw = row[col_map.get("principal", 6)] if col_map.get("principal", -1) < len(row) else None
        princ = _parse_num(princ_raw, amt_eur) if princ_raw else amt_eur

        # Notes
        notes_raw = row[col_map.get("notes", 7)] if col_map.get("notes", -1) < len(row) else None
        notes = str(notes_raw).strip() if notes_raw is not None else ""

        amt_jod = round(amt_eur * rate, 3)
        case = case_by_biz_id.get(biz.id)
        case_id = case.id if case else None

        # Check for existing repayment to update (by business_id, payment_date, and reference_number if provided)
        existing = None
        if ref:
            existing = db.query(LoanRepayment).filter(
                LoanRepayment.branch_id == branch_id,
                LoanRepayment.business_id == biz.id,
                LoanRepayment.reference_number == ref,
            ).first()

        if existing:
            existing.payment_date = pay_date
            existing.amount = amt_eur
            existing.exchange_rate = rate
            existing.amount_jod = amt_jod
            existing.principal_amount = princ
            existing.payment_method = method
            existing.notes = notes
            existing.status = "completed"
            updated_count += 1
        else:
            repay = LoanRepayment(
                branch_id=branch_id,
                business_id=biz.id,
                case_id=case_id,
                payment_date=pay_date,
                amount=amt_eur,
                currency="EUR",
                disbursement_currency="JOD",
                exchange_rate=rate,
                amount_jod=amt_jod,
                principal_amount=princ,
                interest_amount=0.0,
                payment_method=method,
                reference_number=ref,
                status="completed",
                notes=notes,
                recorded_by_id=user.id if user else None,
                created_at=datetime.utcnow(),
            )
            db.add(repay)
            imported_count += 1

        total_eur += amt_eur
        total_jod += amt_jod

        # Timeline entry sync
        if case_id:
            ref_txt = f" (Ref: {ref})" if ref else ""
            tl = db.query(FinanceTimelineEntry).filter(
                FinanceTimelineEntry.case_id == case_id,
                FinanceTimelineEntry.direction == "in",
                FinanceTimelineEntry.entry_date == pay_date,
            ).first()
            if not tl:
                db.add(FinanceTimelineEntry(
                    case_id=case_id,
                    entry_date=pay_date,
                    label=f"Loan Repayment: {biz.name}{ref_txt}",
                    amount=amt_eur,
                    direction="in",
                ))
            else:
                tl.amount = amt_eur

    db.commit()

    return {
        "success": True,
        "imported_count": imported_count,
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "total_amount_eur": round(total_eur, 2),
        "total_amount_jod": round(total_jod, 3),
        "errors": errors,
        "message": f"Successfully processed {imported_count + updated_count} repayments (€{total_eur:,.2f} / {total_jod:,.3f} JOD).",
    }


# ------------------------------------------------------------------ Startup Statement

@router.get("/repayments/{branch_id}/startup/{business_id}/statement/")
def startup_statement(
    branch_id: int,
    business_id: int,
    ctx=Depends(require_perm("repayments.view")),
):
    db: Session = ctx["db"]
    biz = db.get(Business, business_id)
    if not biz or biz.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Startup not found in this branch.")

    case = db.query(InvestmentCase).filter(
        InvestmentCase.branch_id == branch_id,
        InvestmentCase.business_id == biz.id,
    ).first()

    repayments = db.query(LoanRepayment).filter(
        LoanRepayment.branch_id == branch_id,
        LoanRepayment.business_id == biz.id,
    ).order_by(LoanRepayment.payment_date.asc(), LoanRepayment.id.asc()).all()

    rate = float(case.forex_rate if (case and case.forex_rate and case.forex_rate != 1.0) else 0.76) if case else 0.76
    loan_approved_eur = float(case.investment_amount or 0.0) if case else 0.0
    loan_approved_jod = round(loan_approved_eur * rate, 3)

    processed_ids = _counted_batch_ids(db, branch_id)
    total_repaid_eur = sum(float(r.amount or 0.0) for r in repayments
                           if _counts_toward_balance(r, processed_ids))
    total_repaid_jod = sum(float(r.amount_jod or round((r.amount or 0.0) * rate, 3)) for r in repayments
                           if _counts_toward_balance(r, processed_ids))

    outstanding_eur = max(0.0, round(loan_approved_eur - total_repaid_eur, 2))
    outstanding_jod = round(outstanding_eur * rate, 3)

    schedules = []
    if case:
        for p in case.payments:
            schedules.append({
                "id": p.id,
                "due_date": str(p.due_date) if p.due_date else "",
                "amount": float(p.amount or 0.0),
                "paid": bool(p.paid),
                "paid_date": str(p.paid_date) if p.paid_date else "",
            })

    founders = [f"{f.first_name} {f.last_name}".strip() for f in (biz.founders or [])]

    return {
        "business_id": biz.id,
        "business_name": biz.name,
        **_display_names(biz, case),
        "program_id": biz.program_id,
        "program_name": biz.program.name if biz.program else "—",
        "founders": founders,
        "case_id": case.id if case else None,
        "ceo_name": case.ceo_name if case else "",
        "loan_approved_eur": loan_approved_eur,
        "loan_approved_jod": loan_approved_jod,
        "co_financing_grant_eur": float(case.co_financing_amount or 0.0) if case else 0.0,
        "exchange_rate": rate,
        "currency": "EUR",
        "disbursement_currency": "JOD",
        "total_repaid_eur": round(total_repaid_eur, 2),
        "total_repaid_jod": round(total_repaid_jod, 3),
        "outstanding_balance_eur": outstanding_eur,
        "outstanding_balance_jod": outstanding_jod,
        "repayments": [repayment_ser(r, db) for r in repayments],
        "schedules": schedules,
    }



# ================================================================== Repayment Batches
# Monthly batch uploads, mirroring the disbursement flow: rows arrive as a
# draft batch, are reviewed, then the batch is confirmed and locked. Batches
# must be registered before the /{repayment_id}/ routes below or FastAPI would
# match "batches" as a repayment id.

BATCH_HEADERS = ["Cohort", "Startup", "Loan #", "Paid by", "Date of repayment",
                 "Cash / Bank", "Channel", "Amount (JOD)", "Amount (EUR)",
                 "Instalment / notes", "Verified against"]


def _parse_any_date(v):
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_amount(v):
    if v is None:
        return 0.0
    s = str(v).strip().replace(",", "").replace("\u00a0", "").replace(" ", "")
    if not s or s in ("-", "\u2014"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _strip_loan_suffix(name: str) -> str:
    """'OrganicG - 1st loan' -> 'OrganicG'; the loan number column already
    distinguishes the loans, the suffix is just how the register labels them."""
    return re.sub(r"\s*[-\u2013/]\s*\d*\s*(st|nd|rd|th)?\s*loan\s*$", "",
                  (name or "").strip(), flags=re.I).strip()


def _norm_biz_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _match_business(raw_name: str, businesses):
    """Match a register startup name to a Business record. Handles name
    variants seen in practice: 'BabPlus' vs 'Bab Plus', 'Barq Boxes' vs
    'BarqBoxes', 'GGEZ / Kafana Tech' vs 'GGEZ1', 'Denally' vs
    'Denally (Dr. NALY)'."""
    target = _norm_biz_name(_strip_loan_suffix(raw_name))
    raw = _strip_loan_suffix(raw_name).strip().lower()
    if not target and not raw:
        return None
    # exact normalised match first; names in non-latin scripts (e.g. Arabic)
    # normalise to nothing, so fall back to the raw name
    for b in businesses:
        nb = _norm_biz_name(b.name)
        if target and nb and nb == target:
            return b
        if not target and b.name.strip().lower() == raw:
            return b
    # alternates written as 'A / B' are tried as separate names
    parts = [_norm_biz_name(p) for p in re.split(r"\s*/\s*", raw_name)]
    best = None
    for p in parts:
        if not p:
            continue
        for b in businesses:
            nb = _norm_biz_name(b.name)
            nraw = b.name.strip().lower()
            if target and nb and (nb == p or nb.startswith(p) or p.startswith(nb)):
                if best is None or len(nb) > len(_norm_biz_name(best.name)):
                    best = b
            elif not target and nraw == raw:
                best = b
    return best


def _digits_from(text: str) -> str:
    """Loan numbers are stored as their digits: the register appends notes to
    the cell ('1000005 (restructured as 1000016)', '1000001 (dup. no.)') and
    schedules and per-loan sums key on the number alone."""
    m = re.search(r"\d+", text or "")
    return m.group(0) if m else ""


def _classify_entry(label: str) -> str:
    t = (label or "").lower()
    if "refinanc" in t or "balance rolled" in t or "consolidat" in t:
        return "refinanced"
    # an instalment that merely mentions a fee stays an instalment
    if "instalment" in t or "installment" in t:
        return "installment"
    if "fee" in t:
        return "fee"
    return "installment"


def _is_unverified(source: str) -> bool:
    """Register convention: yellow rows are evidenced only by a slip or
    Loandisk, with nothing on a bank record."""
    s = (source or "").lower()
    if any(k in s for k in ("bank", "report", "statement")):
        return False
    return any(k in s for k in ("slip", "loandisk", "receipt"))




def _repayment_split_cases(db: Session, branch_id: int, repayments):
    """(principal_eur, charges_eur) actually collected, where charges = the
    interest / fee share of each instalment. The schedule is the source of
    truth for the split: a repayment settles unpaid instalments oldest-first,
    each instalment contributing its principal/interest/fee composition."""
    cases = {c.id: c for c in db.query(InvestmentCase).filter(
        InvestmentCase.branch_id == branch_id).all()}
    case_ids = {r.case_id for r in repayments if r.case_id}
    sched = {}
    if case_ids:
        for e in db.query(PaymentScheduleEntry).filter(
                PaymentScheduleEntry.case_id.in_(case_ids)).order_by(
                PaymentScheduleEntry.due_date.asc(), PaymentScheduleEntry.id.asc()).all():
            sched.setdefault(e.case_id, []).append(e)
    principal = charges = 0.0
    for r in repayments:
        case = cases.get(r.case_id)
        if case is None:
            # no case link: the whole payment is treated as principal
            principal += float(r.amount or 0.0)
            continue
        rate = (float(case.forex_rate or 0.76) or 0.76)
        entries = sched.get(case.id, [])
        # a repayment settles unpaid instalments in the loan currency, oldest
        # first; each instalment pays its own composition
        remaining = float(r.amount_jod or 0.0) or round(float(r.amount or 0.0) * rate, 3)
        for e in entries:
            if remaining <= 0.005:
                break
            if e.paid:
                continue
            total_i = float(e.amount or 0.0)
            take = min(remaining, total_i)
            share = (take / total_i) if total_i > 0 else 0.0
            principal += float(e.principal_amount or 0.0) * share / rate
            charges += (float(e.interest_amount or 0.0) + float(e.fee_amount or 0.0)) * share / rate
            remaining -= take
        if remaining > 0.005 and not entries:
            # schedule missing: fall back to treating everything as principal
            principal += (float(r.amount_jod or 0.0) or float(r.amount or 0.0) * rate) / rate
    return round(principal, 2), round(charges, 2)


def _portfolio_positions(db: Session, branch_id: int):
    """Per-case repayable positions from the schedule (loan currency), plus
    EUR via the case rate. Expected instalments include interest/fees, so
    'including charges' outstanding is normally higher than the loan disbursed."""
    cases = db.query(InvestmentCase).filter(
        InvestmentCase.branch_id == branch_id,
        InvestmentCase.investment_amount > 0).all()
    case_ids = [c.id for c in cases]
    sched = {}
    if case_ids:
        for e in db.query(PaymentScheduleEntry).filter(
                PaymentScheduleEntry.case_id.in_(case_ids)).order_by(
                PaymentScheduleEntry.due_date.asc()).all():
            sched.setdefault(e.case_id, []).append(e)
    out = {}
    today = date.today()
    for c in cases:
        entries = sched.get(c.id, [])
        rate = (float(c.forex_rate or 0.76) or 0.76)
        total_i = sum(float(e.amount or 0.0) for e in entries)
        due_i = sum(float(e.amount or 0.0) for e in entries
                    if e.due_date and e.due_date <= today)
        principal_i = sum(float(e.principal_amount or 0.0) for e in entries)
        charges_i = total_i - principal_i
        out[c.id] = {
            "case": c, "rate": rate,
            "entries": entries,
            "total_expected_i": total_i,
            "scheduled_due_i": due_i,
            "principal_expected_i": principal_i,
            "charges_expected_i": charges_i,
        }
    return out




def _case_repay_position(case: InvestmentCase, repayments, entries):
    """Repayable position for one case, in the loan's own currency.

    The recorded repayments (cash, including the non-cash refinance row)
    settle the schedule oldest-first; that walk gives what was collected and
    how it splits across principal / interest / fees. What remains
    outstanding is every schedule instalment the cash did not reach that the
    loan book has not flagged settled (a restructured loan's superseded
    instalments are flagged and carry no balance -- the balance lives on the
    restructured loan's own schedule).
    """
    rate = float(case.forex_rate or 0.76) or 0.76
    expected_i = sum(float(e.amount or 0.0) for e in entries)
    principal_i = sum(float(e.principal_amount or 0.0) for e in entries)
    if entries and principal_i == 0.0:
        # schedule without composition (legacy rows): instalments are principal
        for e in entries:
            e.principal_amount = float(e.amount or 0.0)
        principal_i = expected_i
    charges_i = expected_i - principal_i
    sched_ccy = (entries[0].currency or "").upper() if entries else \
        str(case.currency or "").upper()
    cash_i = 0.0
    for r in repayments:
        if sched_ccy == "EUR":
            cash_i += float(r.amount or 0.0)
        else:
            cash_i += float(r.amount_jod or 0.0) if (r.amount_jod or 0.0) > 0 else float(r.amount or 0.0)

    if not entries:
        # no repayment schedule: fall back to the approved facility, treating
        # all collected cash as principal
        disb_i = (float(case.disbursement_amount or 0.0) if sched_ccy == "EUR"
                  else float(case.disbursement_amount_jod or 0.0))
        if disb_i <= 0 and repayments:
            disb_i = (float(case.investment_amount or 0.0) if sched_ccy == "EUR"
                      else round(float(case.investment_amount or 0.0) * rate, 2))
        collected_p = min(cash_i, disb_i)
        collected_c = 0.0
        outstanding_p = max(0.0, disb_i - collected_p)
        outstanding_c = 0.0
    else:
        # the loan book's settled flags only govern instalments the recorded
        # payments never reach (restructures and the like); where cash does
        # reach an instalment, the cash itself settles it -- its timing is
        # what dates the settlement, so an instalment the cash has not
        # reached *yet* is still owed, flag or no flag
        remaining = cash_i
        reached = []
        for e in entries:
            t_i = float(e.amount or 0.0)
            take = min(max(remaining, 0.0), t_i)
            reached.append(take > 0.005)
            remaining -= take
        remaining = cash_i
        collected_p = collected_c = 0.0
        outstanding_p = outstanding_c = 0.0
        for e, is_reached in zip(entries, reached):
            t_i = float(e.amount or 0.0)
            take = min(remaining, t_i)
            share = take / t_i if t_i else 0.0
            collected_p += float(e.principal_amount or 0.0) * share
            collected_c += (float(e.interest_amount or 0.0) + float(e.fee_amount or 0.0)) * share
            remaining -= take
            unsettled = t_i - take
            if unsettled > 0.005 and (not e.paid or is_reached):
                outstanding_p += float(e.principal_amount or 0.0) * (unsettled / t_i)
                outstanding_c += (float(e.interest_amount or 0.0) + float(e.fee_amount or 0.0)) * (unsettled / t_i)
        if remaining > 0.005:
            # overpayment beyond the schedule: principal collected
            collected_p += remaining

    to_eur = (lambda v: v) if sched_ccy == "EUR" else (lambda v: v / rate if rate else 0.0)
    to_jod = (lambda v: v * rate) if sched_ccy == "EUR" else (lambda v: v)
    return {
        "rate": rate, "sched_ccy": sched_ccy,
        "expected_i": expected_i, "principal_i": principal_i, "charges_i": charges_i,
        "cash_i": cash_i,
        "settled_principal_i": collected_p, "settled_charges_i": collected_c,
        "principal_out_i": outstanding_p, "charges_out_i": outstanding_c,
        "incl_out_i": outstanding_p + outstanding_c,
        "principal_out_eur": round(to_eur(outstanding_p), 2),
        "charges_out_eur": round(to_eur(outstanding_c), 2),
        "incl_out_eur": round(to_eur(outstanding_p + outstanding_c), 2),
        "expected_eur": round(to_eur(expected_i), 2),
    }


def _counted_batch_ids(db: Session, branch_id: int) -> set:
    """Batch ids whose rows count toward balances. Mirrors disbursements:
    draft batches are visible but hold no money until they are confirmed."""
    return {b.id for b in db.query(RepaymentBatch.id).filter(
        RepaymentBatch.branch_id == branch_id,
        RepaymentBatch.status == "processed").all()}


def _counts_toward_balance(r: LoanRepayment, processed_ids: set) -> bool:
    """Legacy rows (uploaded before batches existed) always count; batched
    rows count only once their batch is processed."""
    return r.status == "completed" and (r.batch_id is None or r.batch_id in processed_ids)

def _classify_disbursement(title: str):
    """(kind, track) from the disbursement batch title.

    Track I holds only grants (monthly stipend, prototype voucher). Track II
    holds the loan plus the co-financing grant: for the cohort 1&2 series the
    loan went out as Tranche 1 (S3) and the grant followed in two halves
    (Tranche 2 S4 / Tranche 3 S5) -- those halves are grant instalments, not
    loan money, so they must never inflate the repayable balance. Cohort 3
    disburses its loan as a 'Loan Tranche' batch, and top-up funding's grant
    went out as an 'additional grant' batch. Anything unrecognised is treated
    as a loan so the repayable balance is never understated."""
    t = (title or "").lower()
    if "tranche 2" in t or "tranche 3" in t or "grant tranche" in t:
        # co-financing grant instalments (Track II): the grant followed the
        # loan in two halves ("Grant tranche 1/2") and for the cohort 1&2
        # series was recorded as Tranche 2 (S4) / Tranche 3 (S5)
        return "grant", "II"
    if "additional grant" in t:
        # Track II top-up funding: grant disbursed in one go
        return "grant", "II"
    if "track ii" in t or "tranche" in t or "loan" in t:
        return "loan", "II"
    if "track i" in t or "prototype" in t or "stipend" in t or "allowance" in t \
            or "voucher" in t or "grant" in t or "monthly disbursement" in t:
        return "grant", "I"
    return "loan", "II"


def repayment_batch_ser(b: RepaymentBatch, db: Session, include_items: bool = False) -> dict:
    items = b.repayments
    n_jod = sum(1 for r in items if (r.amount_jod or 0) > 0)
    return {
        "id": b.id,
        "branch_id": b.branch_id,
        "title": b.title,
        "batch_month": str(b.batch_month) if b.batch_month else None,
        "source": b.source or "",
        "currency": b.currency or "EUR",
        "disbursement_currency": b.disbursement_currency or "JOD",
        "exchange_rate": float(b.exchange_rate or 0.76),
        "total_eur": round(float(b.total_eur or 0.0), 2),
        "total_jod": round(float(b.total_jod or 0.0), 3),
        "rows_count": len(items),
        "jod_rows": n_jod,
        "status": b.status or "draft",
        "notes": b.notes or "",
        "created_by": (f"{b.created_by.first_name} {b.created_by.last_name}".strip()
                       or b.created_by.email) if b.created_by else None,
        "confirmed_by": (f"{b.confirmed_by.first_name} {b.confirmed_by.last_name}".strip()
                         or b.confirmed_by.email) if b.confirmed_by else None,
        "confirmed_at": b.confirmed_at.isoformat() if b.confirmed_at else None,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "repayments": [repayment_ser(r, db) for r in items] if include_items else None,
    }


@router.post("/repayments/{branch_id}/batches/upload/")
async def upload_repayment_batch(
    branch_id: int,
    file: UploadFile = File(...),
    title: str = Form(""),
    source: str = Form(""),
    ctx=Depends(require_perm("repayments.create")),
):
    """Upload a monthly repayment batch (Excel/CSV). Rows whose startup cannot
    be matched to a business in the branch are skipped and reported back for
    mapping rather than being guessed."""
    import openpyxl
    db: Session = ctx["db"]
    user = ctx["user"]

    contents = await file.read()
    fname = (file.filename or "").lower()

    raw_rows = []
    if fname.endswith(".csv"):
        try:
            text = contents.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = contents.decode("latin-1")
        for r in csv.reader(io.StringIO(text)):
            if any(c.strip() for c in r):
                raw_rows.append(r)
    else:
        try:
            wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True)
            for row in wb.active.iter_rows(values_only=True):
                if row and any(c is not None and str(c).strip() for c in row):
                    raw_rows.append(list(row))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to read spreadsheet: {e}")

    if not raw_rows:
        raise HTTPException(status_code=400, detail="The uploaded spreadsheet is empty.")

    # locate the header row and map its columns
    header_idx, col_map = -1, {}
    for idx, row in enumerate(raw_rows[:10]):
        cells = [str(c).lower().strip() if c is not None else "" for c in row]
        if any("startup" in c or "business" in c or "company" in c for c in cells) and \
           any("amount" in c or "date" in c for c in cells):
            header_idx = idx
            for ci, h in enumerate(cells):
                if "cohort" in h:
                    col_map["cohort"] = ci
                elif "startup" in h or "business" in h or "company" in h:
                    col_map["startup"] = ci
                elif "loan" in h:
                    col_map["loan"] = ci
                elif "paid by" in h or "payer" in h:
                    col_map["payer"] = ci
                elif "date" in h:
                    col_map["date"] = ci
                elif "cash" in h and "bank" in h:
                    col_map["cash_bank"] = ci
                elif "channel" in h:
                    col_map["channel"] = ci
                elif "jod" in h:
                    col_map["jod"] = ci
                elif "eur" in h:
                    col_map["eur"] = ci
                elif "instalment" in h or "installment" in h:
                    col_map["instalment"] = ci
                elif "verified" in h or "source" in h:
                    col_map["verified"] = ci
            break

    if header_idx == -1 or "startup" not in col_map:
        raise HTTPException(
            status_code=400,
            detail="Could not find a header row. Expected columns: " + ", ".join(BATCH_HEADERS))

    def cell(row, key):
        ci = col_map.get(key)
        if ci is None or ci >= len(row):
            return None
        v = row[ci]
        return "" if v is None else v

    businesses = db.query(Business).filter(Business.branch_id == branch_id).all()
    case_by_biz = {c.business_id: c for c in db.query(InvestmentCase).filter(
        InvestmentCase.branch_id == branch_id, InvestmentCase.business_id.isnot(None)).all()}

    parsed, unmatched, skipped = [], [], 0
    for r_idx, row in enumerate(raw_rows[header_idx + 1:], start=header_idx + 2):
        if not row or not any(c is not None and str(c).strip() for c in row):
            continue
        raw_name = str(cell(row, "startup") or "").strip()
        if not raw_name:
            skipped += 1
            continue
        low = raw_name.lower()
        if "total" in low or "grand" in low:      # summary lines inside the sheet
            continue
        pdate = _parse_any_date(cell(row, "date"))
        if pdate is None:
            skipped += 1
            continue
        biz = _match_business(raw_name, businesses)
        if biz is None:
            unmatched.append({"row": r_idx, "startup": raw_name})
            continue

        jod = _parse_amount(cell(row, "jod"))
        eur = _parse_amount(cell(row, "eur"))
        case = case_by_biz.get(biz.id)
        rate = float(case.forex_rate) if (case and case.forex_rate and case.forex_rate != 1.0) else 0.76
        if eur <= 0 and jod > 0:
            eur = round(jod / rate, 2)
        elif jod <= 0 and eur > 0:
            jod = round(eur * rate, 3)
        if eur <= 0 and jod <= 0:
            skipped += 1
            continue

        instalment = str(cell(row, "instalment") or "").strip()
        verified_src = str(cell(row, "verified") or "").strip()
        cash_bank = str(cell(row, "cash_bank") or "").strip()
        parsed.append({
            "business": biz, "case": case, "date": pdate, "rate": rate,
            "jod": jod, "eur": eur,
            "cohort": str(cell(row, "cohort") or "").strip(),
            "loan_number": (_digits_from(str(cell(row, "loan") or "")) or
                            str(cell(row, "loan") or "").strip()),
            "payer_name": str(cell(row, "payer") or "").strip(),
            "payment_method": "Cash" if cash_bank.lower().startswith("cash") else "Bank Transfer",
            "channel": str(cell(row, "channel") or "").strip(),
            "instalment_label": instalment,
            "verified_against": verified_src,
            "verified": not _is_unverified(verified_src),
            "entry_type": _classify_entry(instalment),
        })

    if not parsed:
        raise HTTPException(
            status_code=400,
            detail="No usable repayment rows found"
                   + (f"; {len(unmatched)} row(s) had an unrecognised startup" if unmatched else "") + ".")

    if not (title or "").strip():
        months = sorted({p["date"].strftime("%Y-%m") for p in parsed})
        span = months[0] if len(months) == 1 else f"{months[0]} to {months[-1]}"
        title = f"Repayments — {span}"

    batch = RepaymentBatch(
        branch_id=branch_id,
        title=title.strip(),
        batch_month=date(parsed[0]["date"].year, parsed[0]["date"].month, 1),
        source=(source or "").strip(),
        currency="EUR",
        disbursement_currency="JOD",
        exchange_rate=0.76,
        total_eur=round(sum(p["eur"] for p in parsed), 2),
        total_jod=round(sum(p["jod"] for p in parsed), 3),
        status="draft",
        created_by_id=user.id,
    )
    db.add(batch)
    db.flush()

    for p in parsed:
        db.add(LoanRepayment(
            branch_id=branch_id,
            business_id=p["business"].id,
            case_id=p["case"].id if p["case"] else None,
            batch_id=batch.id,
            payment_date=p["date"],
            amount=p["eur"],
            amount_jod=p["jod"],
            exchange_rate=p["rate"],
            loan_number=p["loan_number"],
            cohort=p["cohort"],
            payer_name=p["payer_name"],
            channel=p["channel"],
            instalment_label=p["instalment_label"],
            verified_against=p["verified_against"],
            verified=p["verified"],
            entry_type=p["entry_type"],
            payment_method=p["payment_method"],
            status="completed",
            recorded_by_id=user.id,
        ))
    db.commit()
    db.refresh(batch)

    return {
        "detail": f"Batch created with {len(parsed)} repayment rows.",
        "batch": repayment_batch_ser(batch, db, include_items=True),
        "matched_startups": len({p["business"].id for p in parsed}),
        "unmatched": unmatched,
        "skipped_rows": skipped,
    }


@router.get("/repayments/{branch_id}/batches/")
def list_repayment_batches(branch_id: int, ctx=Depends(require_perm("repayments.view"))):
    db: Session = ctx["db"]
    batches = db.query(RepaymentBatch).filter(
        RepaymentBatch.branch_id == branch_id).order_by(
        RepaymentBatch.batch_month.desc(), RepaymentBatch.id.desc()).all()
    return {
        "results": [repayment_batch_ser(b, db) for b in batches],
        "count": len(batches),
    }


@router.get("/repayments/{branch_id}/batches/import-template/")
def repayment_batches_template(branch_id: int, ctx=Depends(require_perm("repayments.view"))):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Repayments"
    ws.append(BATCH_HEADERS)
    ws.append(["C#2", "Example Startup", "1000001", "John Doe (bank record)", "20-Jul-2025",
               "Bank transfer", "Inward transfer", 487.75, "", "July 2025",
               "Wafaa's monthly report (bank extract), Jul 2025"])
    ws.append(["C#2", "Example Startup", "1000001", "John Doe", "04-Oct-2026", "Bank transfer",
               "EUR transfer", "", 597.02, "Months 14 & 15 paid together", "Slip; Loandisk"])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=repayment_batch_template.xlsx"})


@router.get("/repayments/{branch_id}/batches/{batch_id}/")
def get_repayment_batch(branch_id: int, batch_id: int, ctx=Depends(require_perm("repayments.view"))):
    db: Session = ctx["db"]
    b = db.get(RepaymentBatch, batch_id)
    if not b or b.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Repayment batch not found.")
    return repayment_batch_ser(b, db, include_items=True)


@router.post("/repayments/{branch_id}/batches/{batch_id}/confirm/")
def confirm_repayment_batch(branch_id: int, batch_id: int, ctx=Depends(require_perm("repayments.confirm"))):
    db: Session = ctx["db"]
    user = ctx["user"]
    b = db.get(RepaymentBatch, batch_id)
    if not b or b.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Repayment batch not found.")
    if b.status == "processed":
        raise HTTPException(status_code=400, detail="Batch is already processed and locked.")
    b.status = "processed"
    b.confirmed_by_id = user.id
    b.confirmed_at = datetime.utcnow()
    b.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(b)
    return {"detail": "Repayment batch confirmed and locked.",
            "batch": repayment_batch_ser(b, db, include_items=True)}


@router.post("/repayments/{branch_id}/batches/{batch_id}/reopen/")
def reopen_repayment_batch(branch_id: int, batch_id: int, ctx=Depends(require_branch_access())):
    db: Session = ctx["db"]
    roles = ctx["roles"]
    if not (any(r in ("branch_admin", "organization_admin", "*") for r in roles)
            or has_perm(roles, "repayments.reopen")):
        raise HTTPException(status_code=403,
                            detail="Only administrators can reopen a processed repayment batch.")
    b = db.get(RepaymentBatch, batch_id)
    if not b or b.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Repayment batch not found.")
    if b.status == "draft":
        raise HTTPException(status_code=400, detail="Batch is already in draft status.")
    b.status = "draft"
    b.confirmed_by_id = None
    b.confirmed_at = None
    b.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(b)
    return {"detail": "Repayment batch reopened.", "batch": repayment_batch_ser(b, db, include_items=True)}


@router.delete("/repayments/{branch_id}/batches/{batch_id}/")
def delete_repayment_batch(branch_id: int, batch_id: int, ctx=Depends(require_perm("repayments.create"))):
    db: Session = ctx["db"]
    b = db.get(RepaymentBatch, batch_id)
    if not b or b.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Repayment batch not found.")
    if b.status == "processed":
        raise HTTPException(status_code=400,
                            detail="Processed batches are locked. Reopen the batch first.")
    db.delete(b)   # rows cascade
    db.commit()
    return {"detail": "Repayment batch deleted."}


@router.get("/repayments/{branch_id}/batches/{batch_id}/export/")
def export_repayment_batch(branch_id: int, batch_id: int, ctx=Depends(require_perm("repayments.view"))):
    import openpyxl
    db: Session = ctx["db"]
    b = db.get(RepaymentBatch, batch_id)
    if not b or b.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Repayment batch not found.")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Repayments"
    ws.append(BATCH_HEADERS)
    for r in b.repayments:
        ws.append([r.cohort, r.business.name if r.business else "", r.loan_number,
                   r.payer_name, str(r.payment_date), r.payment_method, r.channel,
                   float(r.amount_jod or 0), float(r.amount or 0),
                   r.instalment_label, r.verified_against])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", b.title)[:60]
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={safe}.xlsx"})


# ------------------------------------------------------------------ Startup ledger
# Everything that moved for one startup: disbursements received (Track I grant
# / Track II loan) and repayments made, in one chronological ledger with the
# repayable balance at each month end. Track I grants never enter the balance;
# Track II repayments offset only the loan disbursed.

@router.get("/repayments/{branch_id}/startup/{business_id}/ledger/")
def startup_ledger(branch_id: int, business_id: int, ctx=Depends(require_perm("repayments.view"))):
    db: Session = ctx["db"]
    biz = db.get(Business, business_id)
    if not biz or biz.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Startup not found in this branch.")
    case = db.query(InvestmentCase).filter(
        InvestmentCase.branch_id == branch_id,
        InvestmentCase.business_id == biz.id).first()

    rate = float(case.forex_rate) if (case and case.forex_rate and case.forex_rate != 1.0) else 0.76
    loan_approved_eur = float(case.investment_amount or 0.0) if case else 0.0
    co_financing_eur = float(case.co_financing_amount or 0.0) if case else 0.0

    events = []

    items = db.query(DisbursementItem).join(
        DisbursementBatch, DisbursementItem.batch_id == DisbursementBatch.id).filter(
        DisbursementItem.business_id == biz.id,
        DisbursementBatch.branch_id == branch_id,
        DisbursementItem.is_included == True,   # noqa: E712
    ).all()
    for it in items:
        b = it.batch
        kind, track = _classify_disbursement(b.title)
        d = it.disbursement_date or b.payment_date
        eur = float(it.amount or 0.0)
        jod = float(it.amount_jod if it.amount_jod is not None else round(eur * float(b.exchange_rate or rate), 3))
        events.append({
            "date": str(d) if d else "", "_d": d,
            "direction": "in", "kind": kind, "track": track,
            "label": f"{b.title}" + (f" ({b.program.name})" if b.program else ""),
            "amount_eur": eur, "amount_jod": jod,
            "source": "disbursement",
            "notes": it.notes or "",
        })

    repayments = db.query(LoanRepayment).filter(
        LoanRepayment.branch_id == branch_id,
        LoanRepayment.business_id == biz.id,
    ).order_by(LoanRepayment.payment_date.asc(), LoanRepayment.id.asc()).all()
    processed_ids = _counted_batch_ids(db, branch_id)
    for r in repayments:
        eur = float(r.amount or 0.0)
        jod = float(r.amount_jod if r.amount_jod is not None else round(eur * float(r.exchange_rate or rate), 3))
        label_bits = [b for b in (r.instalment_label, f"Loan {r.loan_number}" if r.loan_number else "") if b]
        _loan = (r.loan_number or "").strip()
        events.append({
            "date": str(r.payment_date), "_d": r.payment_date,
            "direction": "out",
            "kind": r.entry_type or "installment", "track": "II",
            "label": " \u00b7 ".join(label_bits) or "Repayment",
            "amount_eur": eur, "amount_jod": jod,
            "source": "repayment",
            "verified": bool(r.verified),
            "channel": r.channel or r.payment_method or "",
            "status": r.status or "completed",
            "entry_type": r.entry_type or "installment",
            "notes": r.notes or "",
            "_counts": _counts_toward_balance(r, processed_ids),
            "_loan": _loan,
        })

    events.sort(key=lambda e: (e["_d"] or date.min, e["source"]))

    counts_toward_balance = lambda e: (e["source"] == "disbursement" and e["kind"] == "loan") \
        or (e["source"] == "repayment" and e["status"] == "completed"
            and e.get("entry_type") in ("installment", "refinanced"))

    disb_loan_eur = disb_loan_jod = 0.0
    disb_grant_eur = disb_grant_jod = 0.0
    disb_grant1_eur = disb_grant2_eur = 0.0
    repaid_eur = repaid_jod = 0.0
    monthly, running_eur, running_jod = {}, 0.0, 0.0

    # month-end repayable positions via the shared helper: the schedule's
    # instalment composition splits each payment into principal and interest/
    # fees, giving both outstanding views (principal-only and incl. charges)
    sched_entries = db.query(PaymentScheduleEntry).filter(
        PaymentScheduleEntry.case_id == case.id).order_by(
        PaymentScheduleEntry.due_date.asc(), PaymentScheduleEntry.id.asc()).all() if case else []

    class _Rep:
        def __init__(self, ev):
            self.amount = ev["amount_eur"]
            self.amount_jod = ev["amount_jod"]

    repay_events = [e for e in events if e["source"] == "repayment"
                    and e.get("_counts") and e.get("entry_type") in ("installment", "refinanced")]

    disbursed_loan_i = float(case.disbursement_amount_jod or 0.0) if case else 0.0
    sched_ccy = (sched_entries[0].currency or "").upper() if sched_entries else ""
    for e in events:
        m = (e["_d"].strftime("%Y-%m") if e["_d"] else "unknown")
        slot = monthly.setdefault(m, {"month": m, "loan_in_eur": 0.0, "loan_in_jod": 0.0,
                                      "grant_in_eur": 0.0, "grant_in_jod": 0.0,
                                      "repaid_eur": 0.0, "repaid_jod": 0.0})
        if e["source"] == "disbursement":
            if e["kind"] == "loan":
                disb_loan_eur += e["amount_eur"]; disb_loan_jod += e["amount_jod"]
                slot["loan_in_eur"] += e["amount_eur"]; slot["loan_in_jod"] += e["amount_jod"]
            else:
                disb_grant_eur += e["amount_eur"]; disb_grant_jod += e["amount_jod"]
                slot["grant_in_eur"] += e["amount_eur"]; slot["grant_in_jod"] += e["amount_jod"]
                if e.get("track") == "I":
                    disb_grant1_eur += e["amount_eur"]
                else:
                    disb_grant2_eur += e["amount_eur"]
        elif e["source"] == "repayment" and e.get("_counts") and e.get("entry_type") in ("installment", "refinanced"):
            repaid_eur += e["amount_eur"]; repaid_jod += e["amount_jod"]
            slot["repaid_eur"] += e["amount_eur"]; slot["repaid_jod"] += e["amount_jod"]
        if (e["source"] == "disbursement" and e["kind"] == "loan") or \
                (e["source"] == "repayment" and e.get("_counts")
                 and e.get("entry_type") in ("installment", "refinanced")):
            # repayable balance (a): principal only
            running_eur += e["amount_eur"] if e["source"] == "disbursement" else -e["amount_eur"]
            running_jod += e["amount_jod"] if e["source"] == "disbursement" else -e["amount_jod"]
        slot["closing_outstanding_eur"] = round(max(0.0, running_eur), 2)
        slot["closing_outstanding_jod"] = round(max(0.0, running_jod), 3)

    # month-end balances via the same schedule walk the headline figures use:
    # recorded payments settle the schedule oldest-first, and what the cash has
    # not reached (and the loan book has not flagged settled) is still owed --
    # split into principal and interest/fees on the remaining instalments.
    # Nothing is owed before the loan itself was disbursed.
    # month-end closing balances are struck on the last calendar day of each
    # month, so the current month lines up with the as-of-today figures
    month_ends = {}
    for e in events:
        if e["_d"]:
            k = e["_d"].strftime("%Y-%m")
            y, mo = int(k[:4]), int(k[5:7])
            month_ends[k] = (date(y, mo + 1, 1) - timedelta(days=1)) if mo < 12 else date(y, 12, 31)
    today = date.today()
    # a loan's schedule only counts as owed from that loan's own disbursement:
    # loans (ordered by first instalment) are matched to loan disbursements in
    # date order; a restructured loan taken on without new cash activates when
    # the previous loan's schedule ends
    loan_first_due, loan_last_due = {}, {}
    for e in sched_entries:
        ln = e.loan_number or ""
        if e.due_date:
            if ln not in loan_first_due or e.due_date < loan_first_due[ln]:
                loan_first_due[ln] = e.due_date
            if ln not in loan_last_due or e.due_date > loan_last_due[ln]:
                loan_last_due[ln] = e.due_date
    loan_disb_dates = sorted(e["_d"] for e in events
                             if e["source"] == "disbursement" and e["kind"] == "loan"
                             and e["_d"])
    loan_gate = {}
    prev_last_due = None
    for i, ln in enumerate(sorted(loan_first_due, key=lambda k: loan_first_due[k])):
        if i < len(loan_disb_dates):
            loan_gate[ln] = loan_disb_dates[i]
        else:
            loan_gate[ln] = prev_last_due or loan_first_due[ln]
        prev_last_due = loan_last_due.get(ln, prev_last_due)
    default_gate = loan_disb_dates[0] if loan_disb_dates else None
    # which instalments the case's recorded cash eventually reaches
    cash_reached = []
    _rem = sum((e["amount_eur"] if sched_ccy == "EUR" else e["amount_jod"])
               for e in repay_events)
    for e in sched_entries:
        _t = float(e.amount or 0.0)
        _take = min(max(_rem, 0.0), _t)
        cash_reached.append(_take > 0.005)
        _rem -= _take
    to_eur = (lambda v: v) if sched_ccy == "EUR" else (lambda v: v / rate if rate else 0.0)
    to_jod = (lambda v: v * rate) if sched_ccy == "EUR" else (lambda v: v)
    for m_key, slot in monthly.items():
        cutoff = month_ends.get(m_key)
        if cutoff is None:
            continue
        if not sched_entries:
            # no repayment schedule: the cash-flow running balance is all we
            # have, and with no instalments there are no separate charges
            slot["closing_incl_charges_eur"] = slot["closing_outstanding_eur"]
            slot["closing_incl_charges_jod"] = slot["closing_outstanding_jod"]
            continue
        if default_gate is None or cutoff < default_gate:
            slot["closing_outstanding_eur"] = slot["closing_outstanding_jod"] = 0.0
            slot["closing_incl_charges_eur"] = slot["closing_incl_charges_jod"] = 0.0
            continue
        remaining = sum((e["amount_eur"] if sched_ccy == "EUR" else e["amount_jod"])
                        for e in repay_events if (e["_d"] or date.max) <= cutoff)
        out_p = out_c = 0.0
        for e, is_reached in zip(sched_entries, cash_reached):
            gate = loan_gate.get(e.loan_number or "", default_gate)
            if cutoff < gate:
                continue   # this loan did not exist yet: it is not owed and
                           # earlier cash belongs to the loans before it
            t_i = float(e.amount or 0.0)
            take = min(remaining, t_i)
            unsettled = t_i - take
            # a settled flag retires an instalment only where the recorded
            # cash never reaches it (restructure bookkeeping) -- and even then
            # only from its due date onward, or from today on so the current
            # month closes at the headline figures. Instalments the cash does
            # reach settle when the cash arrives, flag or no flag.
            if unsettled > 0.005 and t_i:
                retired = (e.paid and not is_reached
                           and (e.due_date is None or e.due_date <= cutoff
                                or cutoff >= today))
                if not retired:
                    share = unsettled / t_i
                    out_p += float(e.principal_amount or 0.0) * share
                    out_c += (float(e.interest_amount or 0.0) + float(e.fee_amount or 0.0)) * share
            remaining -= take
        slot["closing_outstanding_eur"] = round(to_eur(out_p), 2)
        slot["closing_outstanding_jod"] = round(out_p, 3)
        slot["closing_incl_charges_eur"] = round(to_eur(out_p + out_c), 2)
        slot["closing_incl_charges_jod"] = round(out_p + out_c, 2)

    pos_now = _case_repay_position(case, [_Rep(e) for e in repay_events], sched_entries)
    outstanding_incl_jod = round(pos_now["incl_out_i"], 2)
    outstanding_incl_eur = pos_now["incl_out_eur"]

    lines = []
    for e in events:
        e.pop("_d", None)
        lines.append(e)

    # per-loan schedule position: what Loandisk says should have been paid by
    # today against what actually was, in the loan's own currency
    today = date.today()
    loan_summaries = []
    if case:
        loan_numbers = sorted({x.loan_number for x in db.query(PaymentScheduleEntry.loan_number)
                               .filter(PaymentScheduleEntry.case_id == case.id).all()
                               if x.loan_number})
        for ln in loan_numbers:
            sched = db.query(PaymentScheduleEntry).filter(
                PaymentScheduleEntry.case_id == case.id,
                PaymentScheduleEntry.loan_number == ln,
            ).order_by(PaymentScheduleEntry.due_date.asc()).all()
            if not sched:
                continue
            ccy = (sched[0].currency or "").upper()
            scheduled_total = sum(float(x.amount or 0.0) for x in sched)
            scheduled_due = sum(float(x.amount or 0.0) for x in sched
                                if x.due_date and x.due_date <= today)
            paid_to_date = sum(
                float(e["amount_eur" if ccy == "EUR" else "amount_jod"])
                for e in events if e.get("_loan") == ln and e["source"] == "repayment"
                and e["status"] == "completed")
            unpaid = [x for x in sched if not x.paid and x.due_date]
            next_due = unpaid[0] if unpaid else None
            paid_count = sum(1 for x in sched if x.paid)
            all_settled = paid_count >= len(sched)
            # arrears = what should have been paid by today minus what was
            # (the loan book's own definition). A loan whose instalments are
            # all flagged settled (restructured/superseded) carries no
            # arrears -- its balance lives on the restructured loan.
            arrears = max(0.0, scheduled_due - paid_to_date)
            # settled = nothing left on this schedule: every instalment is
            # either flagged settled by the loan book or reached by the
            # recorded payments (cash plus the non-cash refinance row)
            remaining_cash = paid_to_date
            loan_outstanding = 0.0
            for x in sched:
                t = float(x.amount or 0.0)
                take = min(remaining_cash, t)
                if t - take > 0.005 and not x.paid:
                    loan_outstanding += t - take
                remaining_cash -= take
            loan_summaries.append({
                "loan_number": ln,
                "currency": ccy,
                "instalments_scheduled": len(sched),
                "instalments_paid": paid_count,
                "total_scheduled": round(scheduled_total, 2),
                "scheduled_due_to_date": round(scheduled_due, 2),
                "paid_to_date": round(paid_to_date, 2),
                "arrears": 0.0 if all_settled else round(arrears, 2),
                "next_due_date": str(next_due.due_date) if next_due else None,
                "next_amount": float(next_due.amount or 0.0) if next_due else None,
                "fully_settled": loan_outstanding <= 0.005,
            })

    return {
        "business_id": biz.id,
        "business_name": biz.name,
        **_display_names(biz, case),
        "program_id": biz.program_id,
        "program_name": biz.program.name if biz.program else None,
        "case_id": case.id if case else None,
        "exchange_rate": rate,
        "loans": loan_summaries,
        "loan_approved_eur": loan_approved_eur,
        "loan_approved_jod": round(loan_approved_eur * rate, 3),
        "co_financing_grant_eur": co_financing_eur,
        "disbursed_loan_eur": round(disb_loan_eur, 2),
        "disbursed_loan_jod": round(disb_loan_jod, 3),
        "disbursed_grant_eur": round(disb_grant_eur, 2),
        "disbursed_grant_I_eur": round(disb_grant1_eur, 2),
        "disbursed_grant_II_eur": round(disb_grant2_eur, 2),
        "disbursed_grant_jod": round(disb_grant_jod, 3),
        "total_repaid_eur": round(repaid_eur, 2),
        "total_repaid_jod": round(repaid_jod, 3),
        "principal_collected_eur": pos_now["principal_out_eur"] and round(
            (float(case.disbursement_amount or 0.0) if sched_ccy == "EUR"
             else float(case.disbursement_amount_jod or 0.0) / rate
             ) - pos_now["principal_out_eur"], 2) or 0.0,
        "charges_collected_eur": round(pos_now["settled_charges_i"] /
                                       (rate if sched_ccy != "EUR" else 1.0), 2),
        # with a schedule the walk splits principal from charges; without one
        # the cash-flow view (disbursed minus everything repaid) is the best
        # available principal figure
        "outstanding_eur": (pos_now["principal_out_eur"] if sched_entries
                            else max(0.0, round(disb_loan_eur - repaid_eur, 2))),
        "outstanding_jod": (round(pos_now["principal_out_i"], 2) if sched_entries
                            else max(0.0, round(disb_loan_jod - repaid_jod, 3))),
        "outstanding_incl_charges_eur": outstanding_incl_eur,
        "outstanding_incl_charges_jod": round(outstanding_incl_jod, 2),
        "outstanding_vs_approved_eur": max(0.0, round(loan_approved_eur - repaid_eur, 2)),
        "lines": lines,
        "monthly": sorted(monthly.values(), key=lambda m: m["month"]),
    }


# ------------------------------------------------------------------ Single Repayment & Item Operations

@router.get("/repayments/{branch_id}/{repayment_id}/")
def get_repayment(
    branch_id: int,
    repayment_id: int,
    ctx=Depends(require_perm("repayments.view")),
):
    db: Session = ctx["db"]
    r = db.get(LoanRepayment, repayment_id)
    if not r or r.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Repayment record not found.")
    return repayment_ser(r, db)


class RepaymentUpdateIn(BaseModel):
    payment_date: Optional[date] = None
    amount: Optional[float] = None
    exchange_rate: Optional[float] = None
    principal_amount: Optional[float] = None
    interest_amount: Optional[float] = None
    payment_method: Optional[str] = None
    reference_number: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    receipt_url: Optional[str] = None


@router.put("/repayments/{branch_id}/{repayment_id}/")
def update_repayment(
    branch_id: int,
    repayment_id: int,
    data: RepaymentUpdateIn,
    ctx=Depends(require_perm("repayments.edit")),
):
    db: Session = ctx["db"]
    r = db.get(LoanRepayment, repayment_id)
    if not r or r.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Repayment record not found.")

    if data.payment_date is not None:
        r.payment_date = data.payment_date
    if data.amount is not None:
        if data.amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be greater than zero.")
        r.amount = float(data.amount)
    if data.exchange_rate is not None:
        r.exchange_rate = float(data.exchange_rate)

    r.amount_jod = round(r.amount * (r.exchange_rate or 0.76), 3)

    if data.interest_amount is not None:
        r.interest_amount = float(data.interest_amount)
    if data.principal_amount is not None:
        r.principal_amount = float(data.principal_amount)
    else:
        r.principal_amount = max(0.0, r.amount - (r.interest_amount or 0.0))

    if data.payment_method is not None:
        r.payment_method = data.payment_method.strip()
    if data.reference_number is not None:
        r.reference_number = data.reference_number.strip()
    if data.status is not None:
        r.status = data.status.strip().lower()
    if data.notes is not None:
        r.notes = data.notes.strip()
    if data.receipt_url is not None:
        r.receipt_url = data.receipt_url

    if r.case_id:
        ref_needle = f" (Ref: {r.reference_number})" if r.reference_number else ""
        tl = db.query(FinanceTimelineEntry).filter(
            FinanceTimelineEntry.case_id == r.case_id,
            FinanceTimelineEntry.direction == "in",
            FinanceTimelineEntry.entry_date == r.payment_date,
        ).first()
        if tl:
            tl.amount = r.amount
            tl.label = f"Loan Repayment: {r.business.name if r.business else 'Startup'}{ref_needle}"

    db.commit()
    db.refresh(r)
    return repayment_ser(r, db)


@router.delete("/repayments/{branch_id}/{repayment_id}/")
def delete_repayment(
    branch_id: int,
    repayment_id: int,
    ctx=Depends(require_perm("repayments.delete")),
):
    db: Session = ctx["db"]
    r = db.get(LoanRepayment, repayment_id)
    if not r or r.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Repayment record not found.")

    if r.case_id:
        tl = db.query(FinanceTimelineEntry).filter(
            FinanceTimelineEntry.case_id == r.case_id,
            FinanceTimelineEntry.direction == "in",
            FinanceTimelineEntry.entry_date == r.payment_date,
            FinanceTimelineEntry.amount == r.amount,
        ).first()
        if tl:
            db.delete(tl)

    db.delete(r)
    db.commit()
    return {"detail": "Repayment record deleted successfully."}
