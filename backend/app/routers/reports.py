import io

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_perm
from ..models import (
    Business, BusinessFounder, BusinessIndustry, BusinessType, FinanceTimelineEntry,
    InvestmentCase, InvestmentStatus, PaymentScheduleEntry,
)
from ..utils import paginate, parse_page

router = APIRouter(tags=["reports"])

SECTIONS = [
    "overview", "financial-timeline", "investment-metrics", "collateral-overview", "ceo-profile",
    "business-details", "co-financing-summary", "financial-indicators", "sustainability",
    "equity-overview", "requested-technical-assistance",
]


def _approved_cases(db: Session, branch_id: int) -> list[InvestmentCase]:
    approved = db.query(InvestmentStatus).filter_by(code_name="approved").first()
    q = db.query(InvestmentCase).filter(InvestmentCase.branch_id == branch_id)
    if approved:
        q = q.filter(InvestmentCase.status_id == approved.id)
    return list(q.order_by(InvestmentCase.created_at.desc()))


def _case_rows(db: Session, branch_id: int) -> list[dict]:
    out = []
    for c in _approved_cases(db, branch_id):
        biz = db.get(Business, c.business_id) if c.business_id else None
        founder = biz.founders[0] if biz and biz.founders else None
        industry = db.get(BusinessIndustry, c.industry_id)
        btype = db.get(BusinessType, c.type_id)
        row = {"case": c, "business": biz, "founder": founder}
        row["industry"] = industry.name if industry else ""
        row["type"] = btype.name if btype else ""
        out.append(row)
    return out


def section_rows(section: str, db: Session, branch_id: int) -> tuple[list[str], list[dict]]:
    rows = _case_rows(db, branch_id)

    def build(headers, mapper):
        return headers, [mapper(r) for r in rows]

    if section == "overview":
        return build(
            ["Company", "Industry", "Type", "Round", "Amount invested", "Co-financing"],
            lambda r: {
                "Company": r["case"].company_name, "Industry": r["industry"], "Type": r["type"],
                "Round": r["case"].round.name if r["case"].round else "",
                "Amount invested": r["case"].investment_amount or 0,
                "Co-financing": r["case"].co_financing_amount or 0})
    if section == "financial-timeline":
        entries = []
        for c in _approved_cases(db, branch_id):
            for e in c.timeline_entries:
                entries.append({"Case": c.company_name, "Date": str(e.entry_date), "Label": e.label,
                                "Direction": e.direction, "Amount (USD)": round(
                                    e.amount * (c.forex_rate or 1.0), 2)})
        headers = ["Case", "Date", "Label", "Direction", "Amount (USD)"]
        return headers, entries
    if section == "investment-metrics":
        return build(
            ["Company", "Equity offered %", "Amount requested", "Amount invested", "ROI proxy %"],
            lambda r: {
                "Company": r["case"].company_name,
                "Equity offered %": r["case"].equity_offered_pct or 0,
                "Amount requested": r["case"].amount_requested or 0,
                "Amount invested": r["case"].investment_amount or 0,
                "ROI proxy %": round(
                    100.0 * (r["case"].equity_offered_pct or 0) / 100.0 *
                    ((r["case"].investment_amount or 0) / (r["case"].amount_requested or 1)), 1)})
    if section == "collateral-overview":
        return build(["Company", "Collateral description"],
                     lambda r: {"Company": r["case"].company_name,
                                "Collateral description": r["case"].collateral_description or ""})
    if section == "ceo-profile":
        return build(
            ["Company", "CEO name", "Founder email", "Position"],
            lambda r: {"Company": r["case"].company_name, "CEO name": r["case"].ceo_name,
                       "Founder email": (r["founder"].email if r["founder"] else ""),
                       "Position": (r["founder"].position if r["founder"] else "")})
    if section == "business-details":
        return build(
            ["Company", "Business name", "Programme", "Graduation", "Course progress %"],
            lambda r: {
                "Company": r["case"].company_name,
                "Business name": r["business"].name if r["business"] else "",
                "Programme": (r["business"].program.name if r["business"] and r["business"].program else ""),
                "Graduation": r["business"].graduation_status if r["business"] else "",
                "Course progress %": (r["business"].course_progress or 0) if r["business"] else 0})
    if section == "co-financing-summary":
        return build(
            ["Company", "Investment amount", "Co-financing amount", "Total", "Co-financing share %"],
            lambda r: {
                "Company": r["case"].company_name,
                "Investment amount": r["case"].investment_amount or 0,
                "Co-financing amount": r["case"].co_financing_amount or 0,
                "Total": (r["case"].investment_amount or 0) + (r["case"].co_financing_amount or 0),
                "Co-financing share %": round(
                    100.0 * (r["case"].co_financing_amount or 0) /
                    max(1e-9, (r["case"].investment_amount or 0) + (r["case"].co_financing_amount or 0)), 1)})
    if section == "financial-indicators":
        return build(
            ["Company", "Currency", "Forex rate", "Invested (local)", "Requested (local)"],
            lambda r: {
                "Company": r["case"].company_name, "Currency": r["case"].currency,
                "Forex rate": r["case"].forex_rate or 1.0,
                "Invested (local)": round((r["case"].investment_amount or 0) / (r["case"].forex_rate or 1.0), 2),
                "Requested (local)": round((r["case"].amount_requested or 0) / (r["case"].forex_rate or 1.0), 2)})
    if section == "sustainability":
        return build(["Company", "Sustainability notes"],
                     lambda r: {"Company": r["case"].company_name,
                                "Sustainability notes": r["case"].sustainability_notes or ""})
    if section == "equity-overview":
        return build(["Company", "Equity offered %", "Round"],
                     lambda r: {"Company": r["case"].company_name,
                                "Equity offered %": r["case"].equity_offered_pct or 0,
                                "Round": r["case"].round.name if r["case"].round else ""})
    if section == "requested-technical-assistance":
        return build(["Company", "Technical assistance request"],
                     lambda r: {"Company": r["case"].company_name,
                                "Technical assistance request": r["case"].technical_assistance_request or ""})
    raise HTTPException(status_code=404, detail="Unknown report section.")


@router.get("/branch/{branch_id}/reports/detailed-info/{section}/")
def detailed_info(branch_id: int, section: str, request: Request,
                  ctx=Depends(require_perm("reports.view"))):
    if section not in SECTIONS:
        raise HTTPException(status_code=404, detail="Unknown report section.")
    db: Session = ctx["db"]
    headers, rows = section_rows(section, db, branch_id)
    page, size = parse_page(request)
    start = (page - 1) * size
    chunk = rows[start:start + size]
    return {
        "count": len(rows),
        "page": page, "page_size": size,
        "headers": headers,
        "results": [{h: r.get(h) for h in headers} for r in chunk],
    }


@router.get("/branch/{branch_id}/reports/detailed-info/{section}/export/")
def export_section(branch_id: int, section: str, ctx=Depends(require_perm("reports.export"))):
    from openpyxl import Workbook
    if section not in SECTIONS:
        raise HTTPException(status_code=404, detail="Unknown report section.")
    db: Session = ctx["db"]
    headers, rows = section_rows(section, db, branch_id)
    wb = Workbook()
    ws = wb.active
    ws.title = section[:31]
    ws.append(headers)
    for r in rows:
        ws.append([r.get(h) for h in headers])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(buf, media_type=(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        headers={"Content-Disposition": f"attachment; filename={section}.xlsx"})


@router.get("/branch/{branch_id}/reports/portfolio-snapshot/")
def portfolio_snapshot(request: Request, ctx=Depends(require_perm("reports.view"))):
    db: Session = ctx["db"]
    rows = _case_rows(db, ctx["branch_id"])
    total_invested = sum(r["case"].investment_amount or 0 for r in rows)
    total_cofin = sum(r["case"].co_financing_amount or 0 for r in rows)
    by_industry: dict[str, float] = {}
    for r in rows:
        key = r["industry"] or "Other"
        by_industry[key] = by_industry.get(key, 0) + (r["case"].investment_amount or 0)
    return {
        "companies": len(rows),
        "total_invested": round(total_invested, 2),
        "total_co_financing": round(total_cofin, 2),
        "avg_ticket": round(total_invested / len(rows), 2) if rows else 0,
        "by_industry": sorted([{"name": k, "invested": round(v, 2)} for k, v in by_industry.items()],
                              key=lambda x: -x["invested"]),
    }


@router.get("/branch/{branch_id}/reports/payments-schedule/")
def payments_schedule(request: Request, ctx=Depends(require_perm("reports.view"))):
    db: Session = ctx["db"]
    case_ids = [c.id for c in _approved_cases(db, ctx["branch_id"])]
    rows = db.query(PaymentScheduleEntry).filter(PaymentScheduleEntry.case_id.in_(case_ids or [0]))
    rows = rows.order_by(PaymentScheduleEntry.due_date).all()
    out = []
    for p in rows:
        case = db.get(InvestmentCase, p.case_id)
        overdue = (not p.paid) and p.due_date is not None
        out.append({
            "id": p.id, "company": case.company_name if case else "", "due_date": str(p.due_date),
            "amount": p.amount, "paid": bool(p.paid), "status":
                ("paid" if p.paid else ("overdue" if overdue else "upcoming"))})
    return {"count": len(out), "results": out}


@router.get("/branch/{branch_id}/reports/aging-analysis/")
def aging_analysis(ctx=Depends(require_perm("reports.view"))):
    from datetime import date
    db: Session = ctx["db"]
    today = date.today()
    buckets = {"current": 0.0, "1-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
    case_ids = [c.id for c in _approved_cases(db, ctx["branch_id"])]
    rows = db.query(PaymentScheduleEntry).filter(
        PaymentScheduleEntry.case_id.in_(case_ids or [0]), PaymentScheduleEntry.paid.is_(False)).all()
    for p in rows:
        if not p.due_date:
            continue
        days = (today - p.due_date).days
        amount = p.amount or 0
        if days <= 0:
            buckets["current"] += amount
        elif days <= 30:
            buckets["1-30"] += amount
        elif days <= 60:
            buckets["31-60"] += amount
        elif days <= 90:
            buckets["61-90"] += amount
        else:
            buckets["90+"] += amount
    return [{"bucket": k, "outstanding": round(v, 2)} for k, v in buckets.items()]


@router.get("/branch/{branch_id}/reports/forex/")
def forex_report(ctx=Depends(require_perm("reports.view"))):
    db: Session = ctx["db"]
    rows = []
    for c in _approved_cases(db, ctx["branch_id"]):
        rate = c.forex_rate or 1.0
        rows.append({
            "company": c.company_name, "currency": c.currency, "rate": rate,
            "invested_usd": round((c.investment_amount or 0) * rate, 2) if c.currency != "USD"
            else round(c.investment_amount or 0, 2),
            "requested_local": round((c.amount_requested or 0), 2)})
    return {"count": len(rows), "results": rows}
