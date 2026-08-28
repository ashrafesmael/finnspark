from fastapi import APIRouter, Depends, Request
from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import (
    Applicant, ApplicantStatus, BusinessIndustry, BusinessType, CommitteeLevel, Country, CourseStatus,
    District, FieldType, FormStatus, Gender, InvestmentRound, InvestmentStage, InvestmentStatus,
    InvestmentTier, OrganizationStatus, ProgramStatus, Province, AnnouncementStatus, SelectionStage,
    Program,
)
from ..utils import serialize_ref

router = APIRouter(tags=["references"])


@router.get("/genders/")
def genders(db: Session = Depends(get_db)):
    return [serialize_ref(g) for g in db.query(Gender).all()]


@router.get("/countries/")
def countries(db: Session = Depends(get_db)):
    return [serialize_ref(c) for c in db.query(Country).order_by(Country.name).all()]


@router.get("/countries/selected_countries/{branch_id}/")
def selected_countries(branch_id: int, db: Session = Depends(get_db)):
    ids = [r[0] for r in db.query(Applicant.country_id).filter(
        Applicant.branch_id == branch_id, Applicant.country_id.isnot(None)).distinct()]
    return [serialize_ref(db.get(Country, i)) for i in sorted({i for i in ids if i})]


@router.get("/countries/selected_provinces/{branch_id}/")
def selected_provinces(branch_id: int, db: Session = Depends(get_db)):
    ids = [r[0] for r in db.query(Applicant.province_id).filter(
        Applicant.branch_id == branch_id, Applicant.province_id.isnot(None)).distinct()]
    out = []
    for i in sorted({i for i in ids if i}):
        p = db.get(Province, i)
        if p:
            out.append({"id": p.id, "name": p.name})
    return out


@router.get("/countries/selected_districts/{branch_id}/")
def selected_districts(branch_id: int, db: Session = Depends(get_db)):
    ids = [r[0] for r in db.query(Applicant.district_id).filter(
        Applicant.branch_id == branch_id, Applicant.district_id.isnot(None)).distinct()]
    out = []
    for i in sorted({i for i in ids if i}):
        d = db.get(District, i)
        if d:
            out.append({"id": d.id, "name": d.name})
    return out


@router.get("/business-types/")
def business_types(db: Session = Depends(get_db)):
    return [serialize_ref(b) for b in db.query(BusinessType).all()]


@router.get("/business-industries/")
def business_industries(db: Session = Depends(get_db)):
    return [serialize_ref(b) for b in db.query(BusinessIndustry).order_by(BusinessIndustry.name).all()]


@router.get("/form-statuses/")
def form_statuses(db: Session = Depends(get_db)):
    return [serialize_ref(f) for f in db.query(FormStatus).all()]


@router.get("/investment-form-statuses/")
def investment_form_statuses(db: Session = Depends(get_db)):
    return [serialize_ref(f) for f in db.query(FormStatus).all()]


@router.get("/course-statuses/")
def course_statuses(db: Session = Depends(get_db)):
    return [serialize_ref(c) for c in db.query(CourseStatus).all()]


@router.get("/program-statuses/{branch_id}/")
def program_statuses(branch_id: int, db: Session = Depends(get_db)):
    rows = db.query(ProgramStatus).filter(
        (ProgramStatus.branch_id == branch_id) | (ProgramStatus.branch_id.is_(None))).all()
    return [serialize_ref(p) for p in rows]


@router.get("/announcement-statuses/")
def announcement_statuses(db: Session = Depends(get_db)):
    return [serialize_ref(a) for a in db.query(AnnouncementStatus).all()]


@router.get("/applicant-statuses/")
def applicant_statuses(db: Session = Depends(get_db)):
    return [serialize_ref(a) for a in db.query(ApplicantStatus).all()]


@router.get("/investment-statuses/")
def investment_statuses(db: Session = Depends(get_db)):
    return [serialize_ref(i) for i in db.query(InvestmentStatus).all()]


@router.get("/investment-tiers/")
def investment_tiers(db: Session = Depends(get_db)):
    return [serialize_ref(i) for i in db.query(InvestmentTier).all()]


@router.get("/investment-rounds/")
def investment_rounds(db: Session = Depends(get_db)):
    return [serialize_ref(i) for i in db.query(InvestmentRound).all()]


@router.get("/investment-stages/{branch_id}/")
def investment_stages(branch_id: int, db: Session = Depends(get_db)):
    return [serialize_ref(i) for i in db.query(InvestmentStage).filter(
        InvestmentStage.branch_id == branch_id).order_by(InvestmentStage.order)]


@router.get("/stages/{branch_id}/")
def selection_stages(branch_id: int, db: Session = Depends(get_db)):
    return [serialize_ref(s) for s in db.query(SelectionStage).filter(
        SelectionStage.branch_id == branch_id).order_by(SelectionStage.order)]


@router.get("/committee-levels/{branch_id}/")
def committee_levels(branch_id: int, db: Session = Depends(get_db)):
    return [serialize_ref(c) for c in db.query(CommitteeLevel).filter(
        CommitteeLevel.branch_id == branch_id).order_by(CommitteeLevel.order)]


@router.get("/field-types/")
def field_types(db: Session = Depends(get_db)):
    return [serialize_ref(f) for f in db.query(FieldType).all()]


@router.get("/organization-statuses/")
def organization_statuses(db: Session = Depends(get_db)):
    return [serialize_ref(o) for o in db.query(OrganizationStatus).all()]


@router.get("/program-list/")
def program_list(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    branch_id = request.query_params.get("branch_id")
    q = db.query(Applicant.program_id).filter(Applicant.program_id.isnot(None))
    if branch_id:
        q = q.filter(Applicant.branch_id == int(branch_id))
    ids = sorted({r[0] for r in q.distinct()})
    programs = db.query(Program).filter(Program.id.in_(ids)).all()
    return [{"id": p.id, "name": p.name} for p in programs]


@router.get("/applicants/application-years/{branch_id}/")
@router.get("/v2/applicants/{branch_id}/application-years/")
def application_years(branch_id: int, db: Session = Depends(get_db)):
    years = db.query(distinct(func.strftime("%Y", Applicant.application_date))).filter(
        Applicant.branch_id == branch_id).all()
    return sorted({int(y[0]) for y in years if y and y[0]}, reverse=True)
