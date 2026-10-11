import io
import csv
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_

from ..database import get_db
from ..deps import require_branch_access, require_perm
from ..models import (
    Branch, Business, BusinessFounder, FinanceTimelineEntry,
    InvestmentCase, LoanRepayment, PaymentScheduleEntry, Program, User,
)

router = APIRouter(tags=["loan_repayments"])


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
    ctx=Depends(require_perm("repayments.view")),
):
    db: Session = ctx["db"]

    cases = db.query(InvestmentCase).filter(
        InvestmentCase.branch_id == branch_id,
        InvestmentCase.investment_amount > 0,
    ).all()
    total_approved_eur = sum(float(c.investment_amount or 0.0) for c in cases)
    rate_def = 0.76
    total_approved_jod = round(total_approved_eur * rate_def, 3)

    repayments = db.query(LoanRepayment).filter(
        LoanRepayment.branch_id == branch_id,
        LoanRepayment.status == "completed",
    ).all()

    total_repaid_eur = sum(float(r.amount or 0.0) for r in repayments)
    total_repaid_jod = sum(float(r.amount_jod or round((r.amount or 0.0) * (r.exchange_rate or rate_def), 3)) for r in repayments)
    total_principal_eur = sum(float(r.principal_amount if r.principal_amount is not None else (r.amount or 0.0)) for r in repayments)
    total_interest_eur = sum(float(r.interest_amount or 0.0) for r in repayments)

    outstanding_eur = max(0.0, round(total_approved_eur - total_principal_eur, 2))
    outstanding_jod = max(0.0, round(outstanding_eur * rate_def, 3))
    recovery_rate = round(100.0 * total_principal_eur / total_approved_eur, 1) if total_approved_eur > 0 else 0.0

    distinct_borrowers = len(set(c.business_id for c in cases if c.business_id))

    return {
        "total_approved_eur": total_approved_eur,
        "total_approved_jod": total_approved_jod,
        "total_repaid_eur": round(total_repaid_eur, 2),
        "total_repaid_jod": round(total_repaid_jod, 3),
        "total_principal_eur": round(total_principal_eur, 2),
        "total_interest_eur": round(total_interest_eur, 2),
        "outstanding_eur": outstanding_eur,
        "outstanding_jod": outstanding_jod,
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
    ctx=Depends(require_perm("repayments.view")),
):
    db: Session = ctx["db"]
    cases = db.query(InvestmentCase).filter(
        InvestmentCase.branch_id == branch_id,
        InvestmentCase.investment_amount > 0,
    ).order_by(InvestmentCase.company_name).all()

    all_repayments = db.query(LoanRepayment).filter(
        LoanRepayment.branch_id == branch_id,
        LoanRepayment.status == "completed",
    ).order_by(LoanRepayment.payment_date.desc()).all()

    repay_by_biz = {}
    for r in all_repayments:
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
        outstanding_eur = max(0.0, round(approved_eur - total_repaid_eur, 2))
        outstanding_jod = round(outstanding_eur * rate, 3)

        pct_repaid = round(100.0 * total_repaid_eur / approved_eur, 1) if approved_eur > 0 else 0.0
        last_date = str(b_repayments[0].payment_date) if b_repayments else None

        rows.append({
            "case_id": c.id,
            "business_id": c.business_id,
            "company_name": (biz.name if biz else None) or c.company_name or "—",
            "program_id": biz.program_id if biz else None,
            "program_name": biz.program.name if (biz and biz.program) else "—",
            "ceo_name": c.ceo_name or "",
            "loan_approved_eur": approved_eur,
            "loan_approved_jod": approved_jod,
            "co_financing_grant_eur": float(c.co_financing_amount or 0.0),
            "currency": c.currency or "EUR",
            "disbursement_currency": "JOD",
            "exchange_rate": rate,
            "total_repaid_eur": round(total_repaid_eur, 2),
            "total_repaid_jod": round(total_repaid_jod, 3),
            "outstanding_balance_eur": outstanding_eur,
            "outstanding_balance_jod": outstanding_jod,
            "pct_repaid": min(100.0, pct_repaid),
            "repayments_count": len(b_repayments),
            "last_payment_date": last_date,
            "status": "fully_repaid" if (outstanding_eur <= 0.01 and total_repaid_eur > 0) else "active",
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

    total_repaid_eur = sum(float(r.amount or 0.0) for r in repayments if r.status == "completed")
    total_repaid_jod = sum(float(r.amount_jod or round((r.amount or 0.0) * rate, 3)) for r in repayments if r.status == "completed")

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
