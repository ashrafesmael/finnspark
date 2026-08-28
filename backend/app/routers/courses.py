from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_branch_access, require_perm
from ..models import (
    Business, BusinessFounder, ContentBlock, Course, CourseStatus, Enrollment, Lesson, Module,
    ProgressRecord,
)
from ..utils import paginate, parse_page


def block_done_ids(db: Session, user_id: int, course: Course) -> set[int]:
    ids = {b.id for b in [bl for m in course.modules for l in m.lessons for bl in l.blocks]}
    rows = db.query(ProgressRecord.content_block_id).filter(
        ProgressRecord.user_id == user_id, ProgressRecord.content_block_id.in_(ids or [0])).all()
    return {r[0] for r in rows}


def course_ser(c: Course, db: Session, user_id: int | None = None, lang: str = "en") -> dict:
    status = db.get(CourseStatus, c.status_id) if c.status_id else None
    done = block_done_ids(db, user_id, c) if user_id else set()
    total = 0
    completed_modules = 0
    started = bool(done)
    for m in c.modules:
        m_total = sum(len(l.blocks) for l in m.lessons)
        m_done = sum(1 for l in m.lessons for b in l.blocks if b.id in done)
        total += m_total
        if m_total and m_done == m_total:
            completed_modules += 1
    progress = round(100.0 * len(done) / total, 1) if total else 0.0
    return {
        "id": c.id, "branch": c.branch_id, "program_id": c.program_id,
        "name": c.name,
        "description": c.description, "language": c.language,
        "subtitle_languages": c.subtitle_languages or [],
        "status": {"id": status.id, "name": status.name, "code_name": status.code_name} if status else None,
        "modules_count": len(c.modules),
        "is_started": started and progress > 0,
        "is_completed": bool(total and len(done) >= total),
        "completed_modules_count": completed_modules,
        "progress": progress,
    }


router = APIRouter(tags=["courses"])


@router.get("/courses/{branch_id}/")
def list_courses(branch_id: int, request: Request, ctx=Depends(require_perm("courses.view"))):
    db: Session = ctx["db"]
    page, size = parse_page(request)
    q = db.query(Course).filter(Course.branch_id == branch_id)
    if v := request.query_params.get("program"):
        q = q.filter((Course.program_id == int(v)) | (Course.program_id.is_(None)))
    if v := request.query_params.get("language"):
        q = q.filter(Course.language == v)
    if s := request.query_params.get("search"):
        q = q.filter(func.lower(Course.name).contains(s.lower()))
    q = q.order_by(Course.created_at.desc())
    return paginate(q, page, size, lambda c: course_ser(c, db, ctx["user"].id))


@router.get("/my-courses/{branch_id}/")
def my_courses(branch_id: int, ctx=Depends(require_perm("courses.view"))):
    """Courses visible to an entrepreneur: branch-wide + attached to their program(s)."""
    db: Session = ctx["db"]
    user = ctx["user"]
    from ..models import Applicant
    program_ids = [
        r[0] for r in db.query(Applicant.program_id).filter_by(user_id=user.id).all()
        if r[0]
    ]
    q = db.query(Course).filter(Course.branch_id == branch_id).filter(
        (Course.program_id.is_(None)) |
        (Course.program_id.in_(program_ids or [0]))
    )
    return [course_ser(c, db, user.id) for c in q.order_by(Course.created_at.desc()).all()]


class BlockIn(BaseModel):
    block_type: str = "text"   # video|text|file|image|quiz
    title: str = ""
    payload: dict = {}
    order: int = 0


class LessonIn(BaseModel):
    name: str
    description: str = ""
    blocks: list[BlockIn] = []


class ModuleIn(BaseModel):
    name: str
    description: str = ""
    lessons: list[LessonIn] = []


class CourseIn(BaseModel):
    name: str
    description: str = ""
    language: str = "en"
    subtitle_languages: list[str] = []
    program_id: int | None = None
    status: str | None = None
    modules: list[ModuleIn] = []


def _write_structure(db: Session, course: Course, data: CourseIn):
    course.modules = []
    for mo_order, mod_in in enumerate(data.modules):
        module = Module(name=mod_in.name, description=mod_in.description, order=mo_order)
        for le_order, les_in in enumerate(mod_in.lessons):
            lesson = Lesson(name=les_in.name, description=les_in.description, order=le_order)
            for bl_order, blk_in in enumerate(les_in.blocks):
                lesson.blocks.append(ContentBlock(
                    block_type=blk_in.block_type, title=blk_in.title,
                    payload=blk_in.payload, order=bl_order))
            module.lessons.append(lesson)
        course.modules.append(module)


@router.post("/courses/{branch_id}/")
def create_course(branch_id: int, data: CourseIn, ctx=Depends(require_perm("courses.edit"))):
    db: Session = ctx["db"]
    status = db.query(CourseStatus).filter(CourseStatus.code_name == (data.status or "draft")).first()
    course = Course(
        branch_id=branch_id, program_id=data.program_id, name=data.name,
        description=data.description, language=data.language,
        subtitle_languages=data.subtitle_languages,
        status_id=status.id if status else None,
    )
    _write_structure(db, course, data)
    db.add(course)
    db.commit()
    return course_ser(course, db, ctx["user"].id)


@router.get("/courses/{branch_id}/{course_id}/")
def course_detail(branch_id: int, course_id: int, request: Request,
                  ctx=Depends(require_perm("courses.view"))):
    db: Session = ctx["db"]
    user = ctx["user"]
    course = db.get(Course, course_id)
    if not course or course.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    done = block_done_ids(db, user.id, course)

    def block_out(bl):
        return {
            "id": bl.id, "block_type": bl.block_type, "title": bl.title,
            "payload": bl.payload or {}, "order": bl.order, "is_completed": bl.id in done,
        }

    def lesson_out(le):
        blocks = sorted(le.blocks, key=lambda x: x.order)
        return {
            "id": le.id, "name": le.name, "description": le.description, "order": le.order,
            "is_completed": all(b.id in done for b in blocks) if blocks else False,
            "blocks": [block_out(b) for b in blocks],
        }

    def module_out(mo):
        lessons = sorted(mo.lessons, key=lambda x: x.order)
        m_total = sum(len(l.blocks) for l in lessons)
        m_done = sum(1 for l in lessons for b in l.blocks if b.id in done)
        return {
            "id": mo.id, "name": mo.name, "description": mo.description, "order": mo.order,
            "progress": round(100.0 * m_done / m_total, 1) if m_total else 0.0,
            "is_completed": m_total > 0 and m_done == m_total,
            "lessons": [lesson_out(l) for l in lessons],
        }

    data = course_ser(course, db, user.id, request.query_params.get("lang", "en"))
    data["modules"] = [module_out(m) for m in sorted(course.modules, key=lambda x: x.order)]
    enrolled = db.query(Enrollment).filter_by(user_id=user.id, course_id=course.id).first()
    data["is_enrolled"] = bool(enrolled)
    return data


@router.patch("/courses/{branch_id}/{course_id}/")
def update_course(branch_id: int, course_id: int, data: CourseIn,
                  ctx=Depends(require_perm("courses.edit"))):
    db: Session = ctx["db"]
    course = db.get(Course, course_id)
    if not course or course.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    course.name, course.description = data.name, data.description
    course.language, course.subtitle_languages = data.language, data.subtitle_languages
    course.program_id = data.program_id
    if data.status:
        st = db.query(CourseStatus).filter(CourseStatus.code_name == data.status).first()
        if st:
            course.status_id = st.id
    if data.modules:
        _write_structure(db, course, data)
    db.commit()
    return course_ser(course, db, ctx["user"].id)


@router.post("/courses/{branch_id}/{course_id}/enroll/")
def enroll_course(branch_id: int, course_id: int, ctx=Depends(require_perm("courses.view"))):
    db: Session = ctx["db"]
    course = db.get(Course, course_id)
    if not course or course.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    row = db.query(Enrollment).filter_by(user_id=ctx["user"].id, course_id=course.id).first()
    if not row:
        db.add(Enrollment(user_id=ctx["user"].id, course_id=course.id, started_at=datetime.utcnow()))
        db.commit()
    return {"detail": "Enrolled"}


@router.post("/content-blocks/{block_id}/complete/")
def complete_block(block_id: int, ctx=Depends(require_perm("courses.view"))):
    db: Session = ctx["db"]
    user = ctx["user"]
    block = db.get(ContentBlock, block_id)
    if not block:
        raise HTTPException(status_code=404, detail="Not found.")
    exists = db.query(ProgressRecord).filter_by(user_id=user.id, content_block_id=block.id).first()
    if not exists:
        db.add(ProgressRecord(user_id=user.id, content_block_id=block.id))
        db.commit()
    # recompute aggregates up the tree + denormalise onto the entrepreneur's businesses
    lesson = db.get(Lesson, block.lesson_id)
    module = db.get(Module, lesson.module_id) if lesson else None
    course = db.get(Course, module.course_id) if module else None
    if course:
        done = block_done_ids(db, user.id, course)
        total = sum(len(l.blocks) for m in course.modules for l in m.lessons)
        progress = round(100.0 * len(done) / total, 1) if total else 0.0
        if total and len(done) >= total:
            enr = db.query(Enrollment).filter_by(user_id=user.id, course_id=course.id).first()
            if enr and not enr.completed_at:
                enr.completed_at = datetime.utcnow()
        # entrepreneurs' businesses get progress/score denormalised
        apps = db.query(BusinessFounder).filter(BusinessFounder.email == user.email).all()
        for link in apps:
            biz = db.get(Business, link.business_id)
            if biz:
                biz.course_progress = progress
                if progress >= 100 and biz.course_score < 100:
                    biz.course_score = min(100.0, biz.course_score + 25.0)
        db.commit()
        return {"progress": progress}
    return {"detail": "ok"}
