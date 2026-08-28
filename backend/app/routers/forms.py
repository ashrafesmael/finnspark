from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_optional_user, require_branch_access, require_perm
from ..models import (
    ApplicationForm, ApplicationFormField, ApplicationFormFieldOption, Applicant, BusinessIndustry,
    Country, FieldType, FormStatus, Gender, Program, ScoringForm, ScoringQuestion, SelectionStage,
)
from ..utils import loc, paginate, parse_page, serialize_ref

router = APIRouter(tags=["forms"])


# ------------------------------------------------------------------ serializers

def _field_ser(f: ApplicationFormField, lang: str) -> dict:
    ft = f.field_type_id
    return {
        "id": f.id,
        "name": loc(f.name_i18n, lang=lang),
        "name_i18n": f.name_i18n or {},
        "field_type": {"id": ft} | (serialize_ref(_ft_cache.get(ft)) if ft in _ft_cache else {}),
        "is_required": bool(f.is_required),
        "order": f.order,
        "options": [
            {"id": o.id, "name": loc(o.name_i18n, lang=lang), "name_i18n": o.name_i18n or {}}
            for o in f.options
        ],
    }


def application_form_ser(f: ApplicationForm, lang: str = "en", nested: bool = True) -> dict:
    status = _status_cache.get(f.status_id)
    data = {
        "id": f.id,
        "branch": f.branch_id,
        "program_id": f.program_id,
        "program_name": (db_program_name.get(f.program_id) if f.program_id in db_program_name else None),
        "name": loc(f.name_i18n, lang=lang),
        "name_i18n": f.name_i18n or {},
        "main_language": f.main_language,
        "form_description": f.form_description,
        "kind": f.kind,
        "status": dict(status) if status else None,
        "created_at": str(f.created_at or ""),
    }
    if nested:
        data["fields"] = [_field_ser(x, lang) for x in f.fields]
    return data


def scoring_form_ser(f: ScoringForm, lang: str = "en", nested: bool = True) -> dict:
    status = _status_cache.get(f.status_id)
    stage = None
    data = {
        "id": f.id,
        "branch": f.branch_id,
        "program_id": f.program_id,
        "selection_stage_id": f.selection_stage_id,
        "is_for_graduation": bool(f.is_for_graduation),
        "name": loc(f.name_i18n, lang=lang),
        "name_i18n": f.name_i18n or {},
        "main_language": f.main_language,
        "form_description": f.form_description,
        "status": dict(status) if status else None,
    }
    if nested:
        data["questions"] = [{
            "id": q.id, "name": q.name, "description": q.description,
            "weightage": q.weightage, "is_required": bool(q.is_required), "order": q.order,
        } for q in f.questions]
    return data


_status_cache: dict[int, dict] = {}
_ft_cache: dict[int, object] = {}
db_program_name: dict[int, str] = {}


def warm_caches(db: Session):
    _status_cache.clear()
    for s in db.query(FormStatus).all():
        _status_cache[s.id] = {"id": s.id, "name": s.name, "code_name": s.code_name}
    _ft_cache.clear()
    for t in db.query(FieldType).all():
        _ft_cache[t.id] = t
    db_program_name.clear()
    for p in db.query(Program).all():
        db_program_name[p.id] = p.name


def _write_fields(db: Session, form: ApplicationForm, fields_in: list[dict]):
    form.fields = []
    for order, fld in enumerate(fields_in):
        field = ApplicationFormField(
            name_i18n=fld.get("name_i18n") or {"en": fld.get("name", "")},
            field_type_id=fld.get("field_type") or fld.get("field_type_id"),
            is_required=bool(fld.get("is_required")),
            order=fld.get("order", order),
        )
        for opt_order, opt in enumerate(fld.get("options", [])):
            field.options.append(ApplicationFormFieldOption(
                name_i18n=opt.get("name_i18n") or {"en": opt.get("name", "")},
                order=opt.get("order", opt_order),
            ))
        form.fields.append(field)


class FormIn(BaseModel):
    name_i18n: dict | None = None
    name: str | None = None
    main_language: str = "en"
    form_description: str = ""
    program_id: int | None = None
    status: str | None = None          # code_name draft|published
    fields: list[dict] = []


@router.get("/application-forms/{branch_id}/")
def list_application_forms(branch_id: int, request: Request, ctx=Depends(require_branch_access())):
    db: Session = ctx["db"]
    warm_caches(db)
    lang = request.query_params.get("lang", "en")
    page, size = parse_page(request)
    q = db.query(ApplicationForm).filter(
        ApplicationForm.branch_id == branch_id, ApplicationForm.kind == "application")
    return paginate(q, page, size, lambda f: application_form_ser(f, lang))


@router.post("/application-forms/{branch_id}/")
def create_application_form(branch_id: int, data: FormIn, ctx=Depends(require_perm("forms.edit"))):
    db: Session = ctx["db"]
    warm_caches(db)
    status = db.query(FormStatus).filter(FormStatus.code_name == (data.status or "draft")).first()
    form = ApplicationForm(
        branch_id=branch_id,
        program_id=data.program_id,
        name_i18n=data.name_i18n or {"en": data.name or ""},
        main_language=data.main_language,
        form_description=data.form_description,
        kind="application",
        status_id=status.id if status else None,
    )
    _write_fields(db, form, data.fields)
    db.add(form)
    db.commit()
    return application_form_ser(form)


@router.get("/application-forms/{branch_id}/{form_id}/")
def get_application_form(branch_id: int, form_id: int, request: Request,
                         ctx=Depends(require_branch_access())):
    db: Session = ctx["db"]
    warm_caches(db)
    form = db.get(ApplicationForm, form_id)
    if not form or form.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    lang = request.query_params.get("lang", "en")
    return application_form_ser(form, lang)


@router.patch("/application-forms/{branch_id}/{form_id}/")
def update_application_form(branch_id: int, form_id: int, data: FormIn,
                            ctx=Depends(require_perm("forms.edit"))):
    db: Session = ctx["db"]
    warm_caches(db)
    form = db.get(ApplicationForm, form_id)
    if not form or form.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    if data.name_i18n is not None:
        form.name_i18n = data.name_i18n
    elif data.name is not None:
        form.name_i18n = {**({"en": form.name_i18n.get("en")} if isinstance(form.name_i18n, dict) else {}), "en": data.name}
    form.main_language = data.main_language or form.main_language
    form.form_description = data.form_description if data.form_description else form.form_description
    form.program_id = data.program_id if data.program_id is not None else form.program_id
    if data.status:
        st = db.query(FormStatus).filter(FormStatus.code_name == data.status).first()
        if st:
            form.status_id = st.id
    if data.fields:
        _write_fields(db, form, data.fields)
    db.commit()
    return application_form_ser(form)


@router.delete("/application-forms/{branch_id}/{form_id}/")
def delete_application_form(branch_id: int, form_id: int, ctx=Depends(require_perm("forms.edit"))):
    db: Session = ctx["db"]
    form = db.get(ApplicationForm, form_id)
    if not form or form.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    db.delete(form)
    db.commit()
    return {"detail": "Deleted"}


# ------------------------------------------------------------------ scoring forms

@router.get("/scoring-forms/{branch_id}/")
def list_scoring_forms(branch_id: int, request: Request, ctx=Depends(require_branch_access())):
    db: Session = ctx["db"]
    warm_caches(db)
    lang = request.query_params.get("lang", "en")
    page, size = parse_page(request)
    q = db.query(ScoringForm).filter(ScoringForm.branch_id == branch_id)
    program = request.query_params.get("program")
    if program:
        q = q.filter(ScoringForm.program_id == int(program))
    graduation = request.query_params.get("is_for_graduation")
    if graduation is not None:
        q = q.filter(ScoringForm.is_for_graduation == (graduation.lower() == "true"))
    return paginate(q, page, size, lambda f: scoring_form_ser(f, lang))


class ScoringQuestionIn(BaseModel):
    name: str
    description: str = ""
    weightage: float = 0.0
    is_required: bool = True


class ScoringFormIn(BaseModel):
    name_i18n: dict | None = None
    name: str | None = None
    main_language: str = "en"
    form_description: str = ""
    program_id: int | None = None
    selection_stage_id: int | None = None
    is_for_graduation: bool = False
    status: str | None = None
    questions: list[ScoringQuestionIn] = []


@router.post("/scoring-forms/{branch_id}/")
def create_scoring_form(branch_id: int, data: ScoringFormIn, ctx=Depends(require_perm("forms.edit"))):
    db: Session = ctx["db"]
    warm_caches(db)
    status = db.query(FormStatus).filter(FormStatus.code_name == (data.status or "draft")).first()
    form = ScoringForm(
        branch_id=branch_id, program_id=data.program_id,
        selection_stage_id=data.selection_stage_id, is_for_graduation=data.is_for_graduation,
        name_i18n=data.name_i18n or {"en": data.name or ""}, main_language=data.main_language,
        form_description=data.form_description, status_id=status.id if status else None,
    )
    for order, q in enumerate(data.questions):
        form.questions.append(ScoringQuestion(
            name=q.name, description=q.description, weightage=q.weightage,
            is_required=q.is_required, order=q.order if hasattr(q, "order") else order,
        ))
    db.add(form)
    db.commit()
    return scoring_form_ser(form)


@router.get("/scoring-forms/{branch_id}/{form_id}/")
def get_scoring_form(branch_id: int, form_id: int, request: Request, ctx=Depends(require_branch_access())):
    db: Session = ctx["db"]
    warm_caches(db)
    form = db.get(ScoringForm, form_id)
    if not form or form.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    return scoring_form_ser(form, request.query_params.get("lang", "en"))


@router.patch("/scoring-forms/{branch_id}/{form_id}/")
def update_scoring_form(branch_id: int, form_id: int, data: ScoringFormIn,
                        ctx=Depends(require_perm("forms.edit"))):
    db: Session = ctx["db"]
    form = db.get(ScoringForm, form_id)
    if not form or form.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Not found.")
    if data.name_i18n is not None:
        form.name_i18n = data.name_i18n
    elif data.name:
        form.name_i18n = {"en": data.name}
    form.program_id = data.program_id if data.program_id is not None else form.program_id
    form.selection_stage_id = data.selection_stage_id if data.selection_stage_id is not None else form.selection_stage_id
    form.is_for_graduation = data.is_for_graduation
    form.form_description = data.form_description or form.form_description
    if data.status:
        st = db.query(FormStatus).filter(FormStatus.code_name == data.status).first()
        if st:
            form.status_id = st.id
    if data.questions:
        form.questions = []
        for order, q in enumerate(data.questions):
            form.questions.append(ScoringQuestion(
                name=q.name, description=q.description, weightage=q.weightage,
                is_required=q.is_required, order=order))
    db.commit()
    return scoring_form_ser(form)


# ------------------------------------------------------------------ investment forms

@router.get("/investment-application-forms/{branch_id}/")
def list_investment_forms(branch_id: int, request: Request, ctx=Depends(require_branch_access())):
    db: Session = ctx["db"]
    warm_caches(db)
    lang = request.query_params.get("lang", "en")
    page, size = parse_page(request)
    q = db.query(ApplicationForm).filter(
        ApplicationForm.branch_id == branch_id, ApplicationForm.kind == "investment")
    return paginate(q, page, size, lambda f: application_form_ser(f, lang))


@router.post("/investment-application-forms/{branch_id}/")
def create_investment_form(branch_id: int, data: FormIn, ctx=Depends(require_perm("forms.edit"))):
    db: Session = ctx["db"]
    warm_caches(db)
    status = db.query(FormStatus).filter(FormStatus.code_name == (data.status or "draft")).first()
    form = ApplicationForm(
        branch_id=branch_id, program_id=data.program_id,
        name_i18n=data.name_i18n or {"en": data.name or ""}, main_language=data.main_language,
        form_description=data.form_description, kind="investment",
        status_id=status.id if status else None,
    )
    _write_fields(db, form, data.fields)
    db.add(form)
    db.commit()
    return application_form_ser(form)


@router.get("/investment-application-forms/{branch_id}/{form_id}/")
def get_investment_form(branch_id: int, form_id: int, request: Request,
                        ctx=Depends(require_branch_access())):
    db: Session = ctx["db"]
    warm_caches(db)
    form = db.get(ApplicationForm, form_id)
    if not form or form.branch_id != branch_id or form.kind != "investment":
        raise HTTPException(status_code=404, detail="Not found.")
    return application_form_ser(form, request.query_params.get("lang", "en"))


@router.patch("/investment-application-forms/{branch_id}/{form_id}/")
def update_investment_form(branch_id: int, form_id: int, data: FormIn,
                           ctx=Depends(require_perm("forms.edit"))):
    db: Session = ctx["db"]
    warm_caches(db)
    form = db.get(ApplicationForm, form_id)
    if not form or form.branch_id != branch_id or form.kind != "investment":
        raise HTTPException(status_code=404, detail="Not found.")
    if data.name_i18n is not None:
        form.name_i18n = data.name_i18n
    elif data.name:
        form.name_i18n = {"en": data.name}
    form.form_description = data.form_description or form.form_description
    if data.status:
        st = db.query(FormStatus).filter(FormStatus.code_name == data.status).first()
        if st:
            form.status_id = st.id
    if data.fields:
        _write_fields(db, form, data.fields)
    db.commit()
    return application_form_ser(form)


@router.delete("/investment-application-forms/{branch_id}/{form_id}/")
def delete_investment_form(branch_id: int, form_id: int, ctx=Depends(require_perm("forms.edit"))):
    db: Session = ctx["db"]
    form = db.get(ApplicationForm, form_id)
    if not form or form.branch_id != branch_id or form.kind != "investment":
        raise HTTPException(status_code=404, detail="Not found.")
    db.delete(form)
    db.commit()
    return {"detail": "Deleted"}


# ------------------------------------------------------------------ public surface

@router.get("/public/forms/{form_id}/")
def public_form(form_id: int, request: Request, db: Session = Depends(get_db)):
    """Unauthenticated published application form for the public apply page."""
    warm_caches(db)
    form = db.get(ApplicationForm, form_id)
    if not form or _status_cache.get(form.status_id, {}).get("code_name") != "published":
        raise HTTPException(status_code=404, detail="Form not found or not published.")
    return application_form_ser(form, request.query_params.get("lang", "en"))


class PublicSubmitIn(BaseModel):
    answers: dict = {}
    labels: dict = {}          # {answer_key: field label} for semantic mapping
    program_id: int | None = None


@router.post("/public/forms/{form_id}/submit/")
def public_submit(form_id: int, data: PublicSubmitIn, db: Session = Depends(get_db)):
    """Create an Applicant from a public application form submission."""
    from ..models import ApplicantStatus, Channel
    warm_caches(db)
    form = db.get(ApplicationForm, form_id)
    if not form:
        raise HTTPException(status_code=404, detail="Form not found.")

    answers = data.answers or {}
    labels = data.labels or {}

    def label_of(key: str) -> str:
        return str(labels.get(key, key)).strip().lower()

    email = first_name = last_name = business_name = ""
    age = None
    gender_name = ""
    for k, v in answers.items():
        s = str(v).strip()
        if not s:
            continue
        lab = label_of(k)
        if "email" in lab and not email:
            email = s.lower()
        elif ("first" in lab and "name" in lab) or lab == "firstname":
            first_name = first_name or s
        elif ("last" in lab and "name" in lab) or "surname" in lab or "family" in lab:
            last_name = last_name or s
        elif "business" in lab or "company" in lab or "project" in lab:
            business_name = business_name or s
        elif lab == "age" or "age" == lab:
            age = _to_int(s)
        elif "gender" in lab:
            gender_name = s.lower()
        elif lab in ("date of birth", "dob", "birth"):
            try:
                from datetime import date as _d
                birth = _d.fromisoformat(s[:10])
                today = _d.today()
                age = today.year - birth.year - (
                    (today.month, today.day) < (birth.month, birth.day))
            except ValueError:
                pass

    applicant = Applicant(
        branch_id=form.branch_id,
        program_id=data.program_id or form.program_id,
        answers=answers,
        answer_labels=data.labels or {},
        email=email, first_name=first_name, last_name=last_name, business_name=business_name,
        age=age,
    )
    if gender_name:
        g = db.query(Gender).filter(
            Gender.name.ilike(f"%{gender_name[:4]}%")).first()
        if g:
            applicant.gender_id = g.id
    # industry: match spinner/option text against the taxonomy
    industries = db.query(BusinessIndustry).all()
    for k, v in answers.items():
        s = str(v).strip().lower()
        if not s or len(s) < 3 or applicant.industry_id:
            continue
        lab = label_of(k)
        if "industry" in lab or "sector" in lab:
            match = next((x for x in industries if x.name.lower() == s), None)
            if match:
                applicant.industry_id = match.id
    invited = db.query(ApplicantStatus).filter(ApplicantStatus.code_name == "invited").first()
    applicant.status_id = invited.id if invited else None
    first_stage = db.query(SelectionStage).filter(
        SelectionStage.branch_id == form.branch_id).order_by(SelectionStage.order).first()
    applicant.selection_stage_id = first_stage.id if first_stage else None
    if form.program_id:
        # keep applicant on the form's program unless overridden
        applicant.program_id = data.program_id or form.program_id
    channel = db.query(Channel).filter(Channel.branch_id == form.branch_id).first()
    applicant.channel_id = channel.id if channel else None
    db.add(applicant)
    db.commit()
    return {"detail": "Application received.", "applicant_id": applicant.id}


def _to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
