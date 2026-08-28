from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_branch_access, require_perm
from ..models import (
    Applicant, ApplicantStatus, Country, District, Evaluation, Province, ScoringForm,
    ScoringQuestion, SelectionStage,
)
from ..utils import paginate, parse_page, serialize_ref


def applicant_ser(a: Applicant, user_id: int | None = None) -> dict:
    return {
        "id": a.id,
        "branch": a.branch_id,
        "business_name": a.business_name,
        "first_name": a.first_name,
        "last_name": a.last_name,
        "email": a.email,
        "program_id": a.program_id,
        "program_name": a.program.name if a.program else None,
        "selection_stage": serialize_ref(a.stage) if a.stage else None,
        "selection_stage_id": a.selection_stage_id,
        "status": serialize_ref(a.status) if a.status else None,
        "country": serialize_ref(a.country) if a.country else None,
        "average_score": a.average_score,
        "registered": bool(a.registered),
        "evaluated_by_me": user_id is not None and (a.id, user_id) in _evals_cache,
        "application_date": str(a.application_date or ""),
    }


_evals_cache: dict[tuple[int, int], object] = {}


def warm_selection(db: Session, branch_id: int, user_id: int | None):
    _evals_cache.clear()
    if not user_id:
        return
    rows = db.query(Evaluation.applicant_id).filter(
        Evaluation.evaluator_id == user_id,
        Evaluation.applicant_id.in_(db.query(Applicant.id).filter(Applicant.branch_id == branch_id)),
    ).all()
    for (aid,) in rows:
        _evals_cache[(aid, user_id)] = True


router = APIRouter(tags=["selection"])


@router.get("/v2/applicants/{branch_id}/")
def applicants_list(branch_id: int, request: Request, ctx=Depends(require_perm("selections.view"))):
    db: Session = ctx["db"]
    user = ctx["user"]
    warm_selection(db, branch_id, user.id)
    page, size = parse_page(request)

    q = db.query(Applicant).filter(Applicant.branch_id == branch_id)
    params = request.query_params
    if s := params.get("search"):
        like = f"%{s}%"
        q = q.filter((Applicant.business_name.ilike(like)) |
                     (Applicant.first_name.ilike(like)) | (Applicant.last_name.ilike(like)) |
                     (Applicant.email.ilike(like)))
    if v := params.get("stage"):
        q = q.filter(Applicant.selection_stage_id == int(v))
    if v := params.get("status"):
        q = q.join(ApplicantStatus, ApplicantStatus.id == Applicant.status_id).filter(
            ApplicantStatus.code_name == v)
    if v := params.get("program"):
        q = q.filter(Applicant.program_id == int(v))
    if v := params.get("country"):
        q = q.filter(Applicant.country_id == int(v))
    if v := params.get("province"):
        q = q.filter(Applicant.province_id == int(v))
    if v := params.get("district"):
        q = q.filter(Applicant.district_id == int(v))
    if v := params.get("registered"):
        q = q.filter(Applicant.registered == (v.lower() == "true"))
    min_s = params.get("min_score")
    if min_s:
        try:
            q = q.filter(Applicant.average_score >= float(min_s))
        except ValueError:
            pass
    q = q.order_by(Applicant.application_date.desc())
    return paginate(q, page, size, lambda a: applicant_ser(a, user.id))


@router.get("/applicants/{branch_id}/{applicant_id}/")
def applicant_detail(branch_id: int, applicant_id: int, ctx=Depends(require_perm("selections.view"))):
    db: Session = ctx["db"]
    a = db.get(Applicant, applicant_id)
    if not a or a.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    data = applicant_ser(a, ctx["user"].id)
    data["answers"] = a.answers or {}
    data["answer_labels"] = a.answer_labels or {}
    data["invited_at"] = a.invited_at.isoformat() + "Z" if a.invited_at else None
    data["age"] = a.age
    data["gender_id"] = a.gender_id
    prov = db.get(Province, a.province_id) if a.province_id else None
    dist = db.get(District, a.district_id) if a.district_id else None
    data["province"] = {"id": prov.id, "name": prov.name} if prov else None
    data["district"] = {"id": dist.id, "name": dist.name} if dist else None
    evals = db.query(Evaluation).filter(Evaluation.applicant_id == a.id).all()
    data["evaluations"] = [{
        "id": e.id, "evaluator_id": e.evaluator_id, "total_score": e.total_score,
        "answers": e.answers, "created_at": str(e.created_at),
    } for e in evals]
    # available scoring forms for this stage
    forms = db.query(ScoringForm).filter(
        ScoringForm.branch_id == branch_id,
        ScoringForm.is_for_graduation.is_(False),
        (ScoringForm.selection_stage_id == a.selection_stage_id) | (ScoringForm.selection_stage_id.is_(None)),
    ).all()
    from ..routers.forms import scoring_form_ser
    data["scoring_forms"] = [scoring_form_ser(f, nested=False) for f in forms]
    grad_forms = db.query(ScoringForm).filter(
        ScoringForm.branch_id == branch_id, ScoringForm.is_for_graduation.is_(True)).all()
    data["graduation_forms"] = [scoring_form_ser(f, nested=False) for f in grad_forms]
    return data


class ApplicantPatch(BaseModel):
    selection_stage_id: int | None = None
    status: str | None = None       # code_name
    program_id: int | None = None
    business_name: str | None = None
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None


@router.patch("/applicants/{branch_id}/{applicant_id}/")
def patch_applicant(branch_id: int, applicant_id: int, data: ApplicantPatch,
                    ctx=Depends(require_perm("selections.edit"))):
    db: Session = ctx["db"]
    a = db.get(Applicant, applicant_id)
    if not a or a.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    if data.selection_stage_id is not None:
        st = db.get(SelectionStage, data.selection_stage_id)
        if not st or st.branch_id != branch_id:
            raise HTTPException(status_code=400, detail="Invalid stage.")
        a.selection_stage_id = st.id
    if data.status:
        st = db.query(ApplicantStatus).filter(ApplicantStatus.code_name == data.status).first()
        if not st:
            raise HTTPException(status_code=400, detail="Invalid status.")
        a.status_id = st.id
    for f in ("program_id", "business_name", "email", "first_name", "last_name"):
        v = getattr(data, f)
        if v is not None:
            setattr(a, f, v)
    db.commit()
    return applicant_ser(a, ctx["user"].id)


class ScoreIn(BaseModel):
    scoring_form_id: int
    answers: list[dict]   # [{question_id, score}]
    is_graduation: bool = False


@router.post("/applicants/{branch_id}/{applicant_id}/score/")
def score_applicant(branch_id: int, applicant_id: int, data: ScoreIn,
                    ctx=Depends(require_perm("applicants.score"))):
    db: Session = ctx["db"]
    a = db.get(Applicant, applicant_id)
    if not a or a.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    form = db.get(ScoringForm, data.scoring_form_id)
    if not form or form.branch_id != branch_id:
        raise HTTPException(status_code=400, detail="Invalid scoring form.")

    questions = {q.id: q for q in db.query(ScoringQuestion).filter(
        ScoringQuestion.scoring_form_id == form.id)}
    total_weight = sum(q.weightage for q in questions.values())
    earned = 0.0
    for ans in data.answers:
        q = questions.get(ans.get("question_id"))
        if not q:
            continue
        try:
            score = max(0.0, min(10.0, float(ans.get("score", 0))))
        except (TypeError, ValueError):
            score = 0.0
        earned += score * q.weightage
    # weighted percentage: scores are 0-10, weightages sum to `total_weight`
    pct = round((earned / total_weight) * 10.0, 2) if total_weight else 0.0

    ev = Evaluation(
        scoring_form_id=form.id, applicant_id=a.id, evaluator_id=ctx["user"].id,
        answers=data.answers, total_score=pct,
    )
    db.add(ev)
    db.flush()

    others = db.query(Evaluation.total_score).filter(
        Evaluation.applicant_id == a.id, Evaluation.id != ev.id).all()
    all_scores = [pct] + [o[0] for o in others]
    a.average_score = round(sum(all_scores) / len(all_scores), 2)
    db.commit()
    return {"evaluation_id": ev.id, "total_score": pct, "average_score": a.average_score}


@router.post("/applicants/{branch_id}/{applicant_id}/invite/")
def invite_applicant(branch_id: int, applicant_id: int, ctx=Depends(require_perm("selections.edit"))):
    """Generate a one-time registration link for the founder (valid 14 days)."""
    db: Session = ctx["db"]
    from datetime import datetime
    from ..models import Notification, User as U
    from ..security import create_invite_token
    from ..config import config
    from ..mailer import send_email, invite_email_html
    a = db.get(Applicant, applicant_id)
    if not a or a.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    if not a.email:
        raise HTTPException(status_code=400, detail="Applicant has no email address on file.")
    token = create_invite_token(a.id, a.email)
    a.invited_at = datetime.utcnow()
    staff = db.query(U).filter(U.email == ctx["user"].email).first()
    db.add(Notification(
        user_id=staff.id, type="invite",
        payload={"message": f"Invitation link generated for {a.email}", "applicant_id": a.id}))
    db.commit()
    base = config.PUBLIC_BASE_URL or ""
    invite_url = f"{base}/register?token={token}"
    sent = send_email(a.email, "Your finnspark founder account invitation",
                      invite_email_html(a.first_name or a.business_name or "", invite_url))
    return {
        "detail": (f"Invitation email sent to {a.email}" if sent
                   else f"Invitation link generated for {a.email} — SMTP not configured, share the link manually"),
        "invite_url": invite_url,
        "email": a.email,
        "email_sent": sent,
        "invited_at": a.invited_at.isoformat() + "Z" if a.invited_at else None,
    }


# ------------------------------------------------------------------ manage stages

class StageIn(BaseModel):
    name: str
    description: str = ""
    order: int = 0


@router.post("/stages/{branch_id}/")
def create_stage(branch_id: int, data: StageIn, ctx=Depends(require_perm("selections.edit"))):
    db: Session = ctx["db"]
    stage = SelectionStage(branch_id=branch_id, name=data.name,
                           description=data.description, order=data.order)
    db.add(stage)
    db.commit()
    db.refresh(stage)
    return serialize_ref(stage)


@router.patch("/stages/{branch_id}/{stage_id}/")
def update_stage(branch_id: int, stage_id: int, data: StageIn,
                 ctx=Depends(require_perm("selections.edit"))):
    db: Session = ctx["db"]
    stage = db.get(SelectionStage, stage_id)
    if not stage or stage.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    stage.name, stage.description, stage.order = data.name, data.description, data.order
    db.commit()
    return serialize_ref(stage)


@router.delete("/stages/{branch_id}/{stage_id}/")
def delete_stage(branch_id: int, stage_id: int, ctx=Depends(require_perm("selections.edit"))):
    db: Session = ctx["db"]
    stage = db.get(SelectionStage, stage_id)
    if not stage or stage.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    used = db.query(Applicant).filter(Applicant.selection_stage_id == stage_id).count()
    if used:
        raise HTTPException(status_code=400, detail="Stage has applicants; move them first.")
    db.delete(stage)
    db.commit()
    return {"detail": "Deleted"}
