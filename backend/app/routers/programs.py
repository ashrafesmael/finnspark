from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_branch_access, require_perm
from ..models import (
    Applicant, Business, BusinessFounder, BusinessIndustry, BusinessType, Course,
    InvestmentCase, InvestmentStage, InvestmentStatus, MentorConclusionQuestion,
    MentorReviewQuestion, Mentorship, Program, ProgramType, ProgramStatus, QuestionAnswer,
)
from ..utils import paginate, parse_page


def business_ser(b: Business, db: Session) -> dict:
    return {
        "id": b.id,
        "name": b.name,
        "program_id": b.program_id,
        "program_name": b.program.name if b.program else None,
        "logo": b.logo,
        "type": {"id": b.type_id} if b.type_id else None,
        "type_name": db.get(BusinessType, b.type_id).name if b.type_id else None,
        "industry_id": b.industry_id,
        "industry_name": (db.get(BusinessIndustry, b.industry_id).name if b.industry_id else None),
        "graduation_status": b.graduation_status,
        "course_progress": b.course_progress,
        "course_score": b.course_score,
        "average_evaluator_score": b.average_evaluator_score,
        "invested": bool(b.invested),
        "founders": [{
            "id": f.id, "first_name": f.first_name, "last_name": f.last_name,
            "email": f.email, "age": f.age, "position": f.position,
        } for f in b.founders],
        "mentors": [{
            "id": m.mentor_id, "name": f"{m.mentor.first_name} {m.mentor.last_name}".strip(),
        } for m in b.mentor_links],
    }


router = APIRouter(tags=["programs"])


# ------------------------------------------------------------------ program types

@router.get("/program-types/{branch_id}/")
def list_program_types(branch_id: int, ctx=Depends(require_branch_access())):
    db: Session = ctx["db"]
    rows = db.query(ProgramType).filter(ProgramType.branch_id == branch_id).all()
    counts = dict(
        db.query(Program.program_type_id, func.count(Program.id))
        .filter(Program.branch_id == branch_id)
        .group_by(Program.program_type_id)
        .all()
    )
    return [{"id": t.id, "name": t.name, "duration_months": t.duration_months,
             "programs_count": counts.get(t.id, 0)} for t in rows]


class ProgramTypeIn(BaseModel):
    name: str
    duration_months: int | None = None


@router.post("/program-types/{branch_id}/")
def create_program_type(branch_id: int, data: ProgramTypeIn, ctx=Depends(require_perm("programs.edit"))):
    db: Session = ctx["db"]
    t = ProgramType(branch_id=branch_id, name=data.name, duration_months=data.duration_months)
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"id": t.id, "name": t.name, "duration_months": t.duration_months}


@router.delete("/program-types/{branch_id}/{type_id}/")
def delete_program_type(branch_id: int, type_id: int, ctx=Depends(require_perm("programs.edit"))):
    db: Session = ctx["db"]
    t = db.get(ProgramType, type_id)
    if not t or t.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    used = db.query(func.count(Business.id)).join(
        Business.program).filter(Program.program_type_id == type_id).scalar()
    if used:
        raise HTTPException(status_code=400, detail="Type is used by programmes.")
    db.delete(t)
    db.commit()
    return {"detail": "Deleted"}


# ------------------------------------------------------------------ programs

def program_ser(p: Program, db: Session) -> dict:
    businesses = db.query(func.count(Business.id)).filter(Business.program_id == p.id).scalar()
    courses = db.query(func.count(Course.id)).filter(Course.program_id == p.id).scalar()
    return {
        "id": p.id, "branch": p.branch_id, "name": p.name, "description": p.description,
        "program_type": {"id": p.program_type.id, "name": p.program_type.name} if p.program_type else None,
        "status": {"id": p.status_id} if p.status_id else None,
        "scoring_required": bool(p.scoring_required),
        "creation_date": str(p.creation_date or ""),
        "businesses_count": businesses or 0,
        "courses_count": courses or 0,
    }


@router.get("/programs/{branch_id}/")
def list_programs(branch_id: int, request: Request, ctx=Depends(require_perm("programs.view"))):
    db: Session = ctx["db"]
    page, size = parse_page(request)
    q = db.query(Program).filter(Program.branch_id == branch_id)
    if s := request.query_params.get("search"):
        q = q.filter(Program.name.ilike(f"%{s}%"))
    q = q.order_by(Program.creation_date.desc())
    return paginate(q, page, size, lambda p: program_ser(p, db))


class ProgramIn(BaseModel):
    name: str
    description: str = ""
    program_type_id: int | None = None
    scoring_required: bool = False
    status: str | None = None


@router.post("/programs/{branch_id}/")
def create_program(branch_id: int, data: ProgramIn, ctx=Depends(require_perm("programs.edit"))):
    db: Session = ctx["db"]
    p = Program(branch_id=branch_id, name=data.name, description=data.description,
                program_type_id=data.program_type_id, scoring_required=data.scoring_required)
    st = db.query(ProgramStatus).filter(ProgramStatus.code_name == (data.status or "active")).first()
    p.status_id = st.id if st else None
    db.add(p)
    db.commit()
    db.refresh(p)
    return program_ser(p, db)


@router.get("/programs/{branch_id}/{program_id}/")
def program_detail(branch_id: int, program_id: int, ctx=Depends(require_perm("programs.view"))):
    db: Session = ctx["db"]
    p = db.get(Program, program_id)
    if not p or p.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    data = program_ser(p, db)
    data["review_questions"] = [
        {"id": q.id, "text": q.text, "order": q.order}
        for q in db.query(MentorReviewQuestion).filter_by(program_id=p.id).order_by(MentorReviewQuestion.order)]
    data["conclusion_questions"] = [
        {"id": q.id, "text": q.text, "order": q.order}
        for q in db.query(MentorConclusionQuestion).filter_by(program_id=p.id).order_by(
            MentorConclusionQuestion.order)]
    return data


@router.patch("/programs/{branch_id}/{program_id}/")
def update_program(branch_id: int, program_id: int, data: ProgramIn,
                   ctx=Depends(require_perm("programs.edit"))):
    db: Session = ctx["db"]
    p = db.get(Program, program_id)
    if not p or p.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    p.name, p.description = data.name, data.description
    p.program_type_id = data.program_type_id
    p.scoring_required = data.scoring_required
    if data.status:
        st = db.query(ProgramStatus).filter(ProgramStatus.code_name == data.status).first()
        if st:
            p.status_id = st.id
    db.commit()
    return program_ser(p, db)


@router.delete("/programs/{branch_id}/{program_id}/")
def delete_program(branch_id: int, program_id: int, ctx=Depends(require_perm("programs.edit"))):
    db: Session = ctx["db"]
    p = db.get(Program, program_id)
    if not p or p.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    used = db.query(Business).filter(Business.program_id == program_id).count()
    if used:
        raise HTTPException(status_code=400, detail="Program has enrolled businesses.")
    db.delete(p)
    db.commit()
    return {"detail": "Deleted"}


# ------------------------------------------------------------------ program businesses

@router.get("/v2/programs/{branch_id}/{program_id}/businesses/")
def program_businesses(branch_id: int, program_id: int, request: Request,
                       ctx=Depends(require_perm("programs.view"))):
    db: Session = ctx["db"]
    page, size = parse_page(request)
    q = db.query(Business).filter(Business.branch_id == branch_id, Business.program_id == program_id)
    if s := request.query_params.get("business_name"):
        q = q.filter(Business.name.ilike(f"%{s}%"))
    q = q.order_by(Business.created_at.desc())
    return paginate(q, page, size, lambda b: business_ser(b, db))


class EnrollIn(BaseModel):
    applicant_id: int | None = None
    name: str | None = None
    type_id: int | None = None
    industry_id: int | None = None
    first_name: str = ""
    last_name: str = ""
    email: str = ""


@router.post("/v2/programs/{branch_id}/{program_id}/businesses/")
def enroll_business(branch_id: int, program_id: int, data: EnrollIn,
                    ctx=Depends(require_perm("programs.edit"))):
    db: Session = ctx["db"]
    p = db.get(Program, program_id)
    if not p or p.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Program not found.")

    applicant = db.get(Applicant, data.applicant_id) if data.applicant_id else None
    if applicant and applicant.branch_id != branch_id:
        raise HTTPException(status_code=400, detail="Applicant not in this branch.")

    biz = Business(
        branch_id=branch_id, program_id=program_id, applicant_id=applicant.id if applicant else None,
        name=data.name or (applicant.business_name if applicant else ""),
        type_id=data.type_id,
        industry_id=data.industry_id or (applicant.industry_id if applicant else None),
        average_evaluator_score=(applicant.average_score or 0.0) if applicant else 0.0,
    )
    founder_first = data.first_name or (applicant.first_name if applicant else "")
    founder_last = data.last_name or (applicant.last_name if applicant else "")
    founder_email = data.email or (applicant.email if applicant else "")
    if founder_first or founder_email:
        biz.founders.append(BusinessFounder(
            first_name=founder_first, last_name=founder_last, email=founder_email))
    db.add(biz)
    db.commit()
    db.refresh(biz)
    return business_ser(biz, db)


class BusinessPatch(BaseModel):
    graduation_status: str | None = None
    mentor_ids: list[int] | None = None
    course_score: float | None = None
    name: str | None = None


@router.patch("/businesses/{branch_id}/{business_id}/")
def patch_business(branch_id: int, business_id: int, data: BusinessPatch,
                   ctx=Depends(require_perm("programs.edit"))):
    db: Session = ctx["db"]
    b = db.get(Business, business_id)
    if not b or b.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    if data.graduation_status is not None:
        b.graduation_status = data.graduation_status
    if data.name:
        b.name = data.name
    if data.course_score is not None:
        b.course_score = data.course_score
    if data.mentor_ids is not None:
        b.mentor_links = [Mentorship(mentor_id=m) for m in data.mentor_ids]
    db.commit()
    return business_ser(b, db)


class InvestIn(BaseModel):
    tier_id: int | None = None
    round_id: int | None = None
    amount_requested: float = 0.0
    currency: str = "USD"


@router.post("/businesses/{branch_id}/{business_id}/invest/")
def invest_business(branch_id: int, business_id: int, data: InvestIn,
                    ctx=Depends(require_perm("dealflow.edit"))):
    """Promote a business into the investment track (spec §5 step 5)."""
    db: Session = ctx["db"]
    b = db.get(Business, business_id)
    if not b or b.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    stage = db.query(InvestmentStage).filter(InvestmentStage.branch_id == branch_id).order_by(
        InvestmentStage.order).first()
    status = db.query(InvestmentStatus).filter(InvestmentStatus.code_name == "in_approval").first()
    case = InvestmentCase(
        branch_id=branch_id, business_id=b.id, company_name=b.name,
        type_id=b.type_id, industry_id=b.industry_id,
        tier_id=data.tier_id, round_id=data.round_id,
        stage_id=stage.id if stage else None,
        status_id=status.id if status else None,
        amount_requested=data.amount_requested, currency=data.currency,
        ceo_name=(f"{b.founders[0].first_name} {b.founders[0].last_name}".strip()
                  if b.founders else ""),
    )
    b.invested = True
    db.add(case)
    db.commit()
    db.refresh(case)
    return {"id": case.id, "company_name": case.company_name}


# ------------------------------------------------------------------ mentor questions

class QuestionIn(BaseModel):
    text: str
    order: int = 0


def _questions_out(db: Session, model, program_id: int):
    rows = db.query(model).filter(model.program_id == program_id).order_by(model.order).all()
    return [{"id": q.id, "text": q.text, "order": q.order} for q in rows]


@router.get("/v2/programs/{program_id}/business-review/questions/")
def review_questions(program_id: int, ctx=Depends(require_perm("programs.view"))):
    return _questions_out(ctx["db"], MentorReviewQuestion, program_id)


@router.post("/v2/programs/{program_id}/business-review/questions/")
def add_review_question(program_id: int, data: QuestionIn, ctx=Depends(require_perm("programs.edit"))):
    db: Session = ctx["db"]
    q = MentorReviewQuestion(program_id=program_id, text=data.text, order=data.order)
    db.add(q)
    db.commit()
    db.refresh(q)
    return {"id": q.id, "text": q.text, "order": q.order}


@router.get("/v2/programs/{program_id}/mentor-conclusion/questions/")
def conclusion_questions(program_id: int, ctx=Depends(require_perm("programs.view"))):
    return _questions_out(ctx["db"], MentorConclusionQuestion, program_id)


@router.post("/v2/programs/{program_id}/mentor-conclusion/questions/")
def add_conclusion_question(program_id: int, data: QuestionIn,
                            ctx=Depends(require_perm("programs.edit"))):
    db: Session = ctx["db"]
    q = MentorConclusionQuestion(program_id=program_id, text=data.text, order=data.order)
    db.add(q)
    db.commit()
    db.refresh(q)
    return {"id": q.id, "text": q.text, "order": q.order}


def _delete_question(model, question_id, ctx):
    db: Session = ctx["db"]
    q = db.get(model, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Not found.")
    db.query(QuestionAnswer).filter_by(question_kind="review" if model is MentorReviewQuestion
                                       else "conclusion", question_id=question_id).delete()
    db.delete(q)
    db.commit()
    return {"detail": "Deleted"}


@router.delete("/v2/programs/{program_id}/business-review/questions/{question_id}/")
def delete_review_question(program_id: int, question_id: int,
                           ctx=Depends(require_perm("programs.edit"))):
    return _delete_question(MentorReviewQuestion, question_id, ctx)


@router.delete("/v2/programs/{program_id}/mentor-conclusion/questions/{question_id}/")
def delete_conclusion_question(program_id: int, question_id: int,
                               ctx=Depends(require_perm("programs.edit"))):
    return _delete_question(MentorConclusionQuestion, question_id, ctx)


class AnswerIn(BaseModel):
    question_kind: str   # review | conclusion
    question_id: int
    answer_text: str = ""
    score: float | None = None


@router.post("/businesses/{branch_id}/{business_id}/mentor-answers/")
def save_mentor_answer(branch_id: int, business_id: int, data: AnswerIn,
                       ctx=Depends(require_perm("mentor.review"))):
    db: Session = ctx["db"]
    b = db.get(Business, business_id)
    if not b or b.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    ans = QuestionAnswer(
        question_kind=data.question_kind, question_id=data.question_id,
        business_id=business_id, mentor_id=ctx["user"].id,
        answer_text=data.answer_text, score=data.score,
    )
    db.add(ans)
    db.commit()
    db.refresh(ans)
    return {"id": ans.id}


@router.get("/businesses/{branch_id}/{business_id}/mentor-answers/")
def get_mentor_answers(branch_id: int, business_id: int, kind: str = "review",
                       ctx=Depends(require_perm("programs.view"))):
    db: Session = ctx["db"]
    rows = db.query(QuestionAnswer).filter_by(business_id=business_id, question_kind=kind).all()
    return [{
        "id": r.id, "question_id": r.question_id, "answer_text": r.answer_text,
        "score": r.score, "mentor_id": r.mentor_id, "created_at": str(r.created_at),
    } for r in rows]


@router.get("/programs/{branch_id}/{program_id}/courses-list/")
def program_courses_progress(branch_id: int, program_id: int,
                             ctx=Depends(require_perm("programs.view"))):
    """Per-course average progress across the cohort (program detail tab)."""
    db: Session = ctx["db"]
    from ..models import ContentBlock, Course, Enrollment, ProgressRecord
    courses = db.query(Course).filter(
        (Course.program_id == program_id) | (Course.branch_id == branch_id)).all()
    out = []
    for c in courses:
        lesson_ids = [l.id for m in c.modules for l in m.lessons]
        total_blocks = sum(len(l.blocks) for m in c.modules for l in m.lessons)
        user_ids = [r[0] for r in db.query(Enrollment.user_id).filter_by(course_id=c.id).all()]
        avg = 0.0
        if total_blocks and user_ids and lesson_ids:
            done = db.query(func.count(ProgressRecord.id)).join(
                ContentBlock, ContentBlock.id == ProgressRecord.content_block_id).filter(
                ProgressRecord.user_id.in_(user_ids),
                ContentBlock.lesson_id.in_(lesson_ids)).scalar()
            expected = total_blocks * len(user_ids)
            avg = round(100.0 * (done or 0) / expected, 1) if expected else 0.0
        out.append({"id": c.id, "name": c.name, "avg_progress": avg})
    return out


# ------------------------------------------------------------------ export
@router.get("/programs/{branch_id}/{program_id}/export/")
def export_program_businesses(branch_id: int, program_id: int,
                              ctx=Depends(require_perm("reports.export"))):
    import io

    from openpyxl import Workbook

    db: Session = ctx["db"]
    p = db.get(Program, program_id)
    if not p or p.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    wb = Workbook()
    ws = wb.active
    ws.title = "Businesses"
    ws.append(["Business/Project", "Founders", "Course progress %", "Course score %",
               "Average evaluator score %", "Mentors", "Graduation"])
    for b in db.query(Business).filter(Business.program_id == program_id).all():
        ws.append([
            b.name,
            ", ".join(f"{f.first_name} {f.last_name}".strip() for f in b.founders),
            round(b.course_progress or 0, 1),
            round(b.course_score or 0, 1),
            round(b.average_evaluator_score or 0, 1),
            ", ".join(f"{m.mentor.first_name} {m.mentor.last_name}".strip() for m in b.mentor_links),
            b.graduation_status,
        ])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    safe_name = "".join(ch if ch.isascii() and (ch.isalnum() or ch in " _-") else "_"
                        for ch in p.name)
    filename = f"{safe_name}_businesses.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
