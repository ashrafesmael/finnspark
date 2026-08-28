from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_branch_access, require_perm
from ..models import (
    Business, BusinessIndustry, BusinessType, CommitteeDecision, CommitteeLevel, InvestmentCase,
    InvestmentStage, InvestmentStatus, InvestmentTier, InvestmentRound, Program,
)
from ..utils import paginate, parse_page


def case_ser(c: InvestmentCase) -> dict:
    return {
        "id": c.id,
        "branch": c.branch_id,
        "business_id": c.business_id,
        "company_name": c.company_name,
        "program_name": (c.business.program.name if c.business and c.business.program else None),
        "type": {"id": c.type_id} if c.type_id else None,
        "industry_id": c.industry_id,
        "tier": {"id": c.tier.id, "name": c.tier.name, "code_name": c.tier.code_name} if c.tier else None,
        "round": {"id": c.round.id, "name": c.round.name, "code_name": c.round.code_name} if c.round else None,
        "stage": {"id": c.stage.id, "name": c.stage.name, "code_name": getattr(c.stage, "code_name", None)} if c.stage else None,
        "status": {"id": c.status.id, "name": c.status.name, "code_name": c.status.code_name} if c.status else None,
        "owner_id": c.owner_id,
        "currency": c.currency,
        "amount_requested": c.amount_requested,
        "investment_amount": c.investment_amount,
        "co_financing_amount": c.co_financing_amount,
        "collateral_description": c.collateral_description,
        "equity_offered_pct": c.equity_offered_pct,
        "ceo_name": c.ceo_name,
        "created_at": str(c.created_at or ""),
    }


router = APIRouter(tags=["investment"])


def _case_query(db: Session, branch_id: int):
    return db.query(InvestmentCase).filter(InvestmentCase.branch_id == branch_id)


def _apply_filters(q, params):
    if v := params.get("tier"):
        q = q.filter(InvestmentCase.tier_id == int(v))
    if v := params.get("stage"):
        q = q.filter(InvestmentCase.stage_id == int(v))
    if v := params.get("type"):
        q = q.filter(InvestmentCase.type_id == int(v))
    if v := params.get("industry"):
        q = q.filter(InvestmentCase.industry_id == int(v))
    if v := params.get("round"):
        q = q.filter(InvestmentCase.round_id == int(v))
    if v := params.get("status"):
        q = q.join(InvestmentStatus, InvestmentStatus.id == InvestmentCase.status_id).filter(
            InvestmentStatus.code_name == v)
    return q


# ------------------------------------------------------------------ dealflow

@router.get("/investment/{branch_id}/dealflow/investment-cases/")
def dealflow_list(branch_id: int, request: Request, ctx=Depends(require_perm("dealflow.view"))):
    db: Session = ctx["db"]
    page, size = parse_page(request)
    q = _apply_filters(_case_query(db, branch_id), request.query_params)
    q = q.order_by(InvestmentCase.created_at.desc())
    return paginate(q, page, size, case_ser)


class CaseIn(BaseModel):
    business_id: int | None = None
    company_name: str | None = None
    type_id: int | None = None
    industry_id: int | None = None
    tier_id: int | None = None
    round_id: int | None = None
    stage_id: int | None = None
    amount_requested: float = 0.0
    currency: str = "USD"
    ceo_name: str = ""


@router.post("/investment/{branch_id}/dealflow/investment-cases/")
def create_case(branch_id: int, data: CaseIn, ctx=Depends(require_perm("dealflow.edit"))):
    db: Session = ctx["db"]
    company = data.company_name
    biz = db.get(Business, data.business_id) if data.business_id else None
    if biz:
        if biz.branch_id != branch_id:
            raise HTTPException(status_code=400, detail="Business not in this branch.")
        company = company or biz.name
    stage = data.stage_id or (
        db.query(InvestmentStage).filter_by(branch_id=branch_id).order_by(
            InvestmentStage.order).first().id
        if db.query(InvestmentStage).filter_by(branch_id=branch_id).count() else None)
    status = db.query(InvestmentStatus).filter(InvestmentStatus.code_name == "in_approval").first()
    case = InvestmentCase(
        branch_id=branch_id, business_id=biz.id if biz else None, company_name=company or "",
        type_id=data.type_id, industry_id=data.industry_id, tier_id=data.tier_id,
        round_id=data.round_id, stage_id=stage,
        status_id=status.id if status else None,
        owner_id=ctx["user"].id, amount_requested=data.amount_requested,
        currency=data.currency, ceo_name=data.ceo_name,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case_ser(case)


@router.get("/investment/{branch_id}/dealflow/investment-cases/{case_id}/")
def case_detail(branch_id: int, case_id: int, ctx=Depends(require_perm("dealflow.view"))):
    db: Session = ctx["db"]
    c = db.get(InvestmentCase, case_id)
    if not c or c.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    data = case_ser(c)
    data["sustainability_notes"] = c.sustainability_notes
    data["innovation_notes"] = c.innovation_notes
    data["technical_assistance_request"] = c.technical_assistance_request
    data["forex_rate"] = c.forex_rate
    data["timeline_entries"] = [{
        "id": e.id, "entry_date": str(e.entry_date), "label": e.label,
        "amount": e.amount, "direction": e.direction} for e in c.timeline_entries]
    data["payments"] = [{
        "id": p.id, "due_date": str(p.due_date), "amount": p.amount,
        "paid": bool(p.paid), "paid_date": str(p.paid_date or "")} for p in c.payments]
    decisions = db.query(CommitteeDecision, CommitteeLevel).join(
        CommitteeLevel, CommitteeLevel.id == CommitteeDecision.committee_level_id).filter(
        CommitteeDecision.case_id == c.id).all()
    data["decisions"] = [{
        "id": d.id, "committee_level": {"id": lvl.id, "name": lvl.name},
        "decision": d.decision, "notes": d.notes, "decided_at": str(d.decided_at)} for d, lvl in decisions]
    return data


@router.patch("/investment/{branch_id}/dealflow/investment-cases/{case_id}/")
def patch_case(branch_id: int, case_id: int, data: dict, ctx=Depends(require_perm("dealflow.edit"))):
    db: Session = ctx["db"]
    c = db.get(InvestmentCase, case_id)
    if not c or c.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    fields = {
        "company_name", "amount_requested", "currency", "ceo_name",
        "collateral_description", "equity_offered_pct", "sustainability_notes",
        "innovation_notes", "technical_assistance_request", "forex_rate",
        "investment_amount", "co_financing_amount",
    }
    for f in fields & set(data.keys()):
        setattr(c, f, data[f])
    for ref_field, model in (("tier_id", InvestmentTier), ("round_id", InvestmentRound),
                             ("stage_id", InvestmentStage), ("status_id", InvestmentStatus)):
        if ref_field in data and data[ref_field]:
            if model is InvestmentStage:
                ok = db.query(model).filter_by(id=int(data[ref_field]), branch_id=branch_id).count()
            else:
                ok = db.get(model, int(data[ref_field]))
            if ok:
                setattr(c, ref_field, int(data[ref_field]))
    db.commit()
    return case_ser(c)


@router.delete("/investment/{branch_id}/dealflow/investment-cases/{case_id}/")
def delete_case(branch_id: int, case_id: int, ctx=Depends(require_perm("dealflow.edit"))):
    db: Session = ctx["db"]
    c = db.get(InvestmentCase, case_id)
    if not c or c.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    db.delete(c)
    db.commit()
    return {"detail": "Deleted"}


# ------------------------------------------------------------------ approval

@router.get("/investment/{branch_id}/approval/investment-cases/")
def approval_list(branch_id: int, request: Request, ctx=Depends(require_perm("approval.view"))):
    db: Session = ctx["db"]
    page, size = parse_page(request)
    q = _apply_filters(_case_query(db, branch_id), request.query_params)
    committee = request.query_params.get("committee")
    if committee:
        q = q.join(CommitteeDecision, CommitteeDecision.case_id == InvestmentCase.id, isouter=True) \
            .filter((CommitteeDecision.committee_level_id == int(committee)) |
                    (CommitteeDecision.id.is_(None)))
    else:
        st = db.query(InvestmentStatus).filter(InvestmentStatus.code_name.in_(
            ["in_approval", "revision"])).all()
        q = q.filter(InvestmentCase.status_id.in_([s.id for s in st]))
    q = q.distinct().order_by(InvestmentCase.created_at.desc())
    return paginate(q, page, size, case_ser)


class DecisionIn(BaseModel):
    committee_level_id: int
    decision: str          # approved | rejected | revision
    notes: str = ""


@router.post("/investment/{branch_id}/approval/{case_id}/decide/")
def decide_case(branch_id: int, case_id: int, data: DecisionIn,
                ctx=Depends(require_perm("approval.decide"))):
    db: Session = ctx["db"]
    c = db.get(InvestmentCase, case_id)
    if not c or c.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    level = db.get(CommitteeLevel, data.committee_level_id)
    if not level or level.branch_id != branch_id:
        raise HTTPException(status_code=400, detail="Invalid committee level.")
    if data.decision not in ("approved", "rejected", "revision"):
        raise HTTPException(status_code=400, detail="Invalid decision.")
    db.add(CommitteeDecision(
        committee_level_id=level.id, case_id=c.id, decision=data.decision,
        notes=data.notes, decided_by_id=ctx["user"].id))

    # advance the workflow: approved → next committee level or final state
    levels = db.query(CommitteeLevel).filter_by(branch_id=branch_id).order_by(CommitteeLevel.order).all()
    decided_levels = {d.committee_level_id for d in db.query(CommitteeDecision).filter(
        CommitteeDecision.case_id == c.id)}
    status_map = {s.code_name: s.id for s in db.query(InvestmentStatus).all()}
    if data.decision == "rejected":
        c.status_id = status_map.get("rejected")
    elif data.decision == "revision":
        c.status_id = status_map.get("revision")
    elif data.decision == "approved":
        pending = [l for l in levels if l.id not in decided_levels]
        if pending:
            c.status_id = status_map.get("in_approval")
        else:
            c.status_id = status_map.get("approved")
    db.commit()
    return case_ser(c)


# ------------------------------------------------------------------ portfolio

@router.get("/investment/{branch_id}/portfolio_management/investment-cases/")
def portfolio_list(branch_id: int, request: Request, ctx=Depends(require_perm("portfolio.view"))):
    db: Session = ctx["db"]
    page, size = parse_page(request)
    approved = db.query(InvestmentStatus).filter(InvestmentStatus.code_name == "approved").first()
    q = _case_query(db, branch_id).filter(InvestmentCase.status_id == approved.id)
    q = _apply_filters(q, request.query_params).order_by(InvestmentCase.created_at.desc())
    return paginate(q, page, size, case_ser)


class TimelineIn(BaseModel):
    entry_date: str
    label: str = ""
    amount: float = 0.0
    direction: str = "in"


@router.post("/investment/{branch_id}/{case_id}/timeline/")
def add_timeline_entry(branch_id: int, case_id: int, data: TimelineIn,
                       ctx=Depends(require_perm("portfolio.edit"))):
    from ..models import FinanceTimelineEntry
    from datetime import date
    db: Session = ctx["db"]
    c = db.get(InvestmentCase, case_id)
    if not c or c.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    try:
        d = date.fromisoformat(data.entry_date[:10])
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date.")
    e = FinanceTimelineEntry(case_id=c.id, entry_date=d, label=data.label,
                             amount=data.amount, direction=data.direction)
    db.add(e)
    db.commit()
    db.refresh(e)
    return {"id": e.id}


class PaymentIn(BaseModel):
    due_date: str
    amount: float = 0.0
    paid: bool = False


@router.post("/investment/{branch_id}/{case_id}/payments/")
def add_payment(branch_id: int, case_id: int, data: PaymentIn,
                ctx=Depends(require_perm("portfolio.edit"))):
    from ..models import PaymentScheduleEntry
    from datetime import date
    db: Session = ctx["db"]
    c = db.get(InvestmentCase, case_id)
    if not c or c.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    try:
        d = date.fromisoformat(data.due_date[:10])
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date.")
    p = PaymentScheduleEntry(case_id=c.id, due_date=d, amount=data.amount, paid=data.paid,
                             paid_date=date.today() if data.paid else None)
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"id": p.id}
