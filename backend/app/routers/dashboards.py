from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_branch_access
from ..models import (
    Applicant, Business, BusinessFounder, BusinessIndustry, BusinessType, Country, District,
    Gender, Province,
)

router = APIRouter(tags=["dashboards"])


AGE_BANDS = [("<17", 0, 17), ("18–24", 18, 24), ("25–34", 25, 34),
             ("35–44", 35, 44), ("45–54", 45, 54), ("55–64", 55, 64), ("65+", 65, 200)]


def _dist(rows, label_fn):
    counts: dict[str, int] = {}
    for r in rows:
        label = label_fn(r)
        if label:
            counts[label] = counts.get(label, 0) + 1
    return [{"name": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])]


@router.get("/dashboard-program/")
def dashboard_program(request: Request, ctx=Depends(require_branch_access())):
    """Program analytics view (spec §6.1): funnel, tiles and distributions."""
    db: Session = ctx["db"]
    branch_id = ctx["branch_id"]
    params = request.query_params

    q = db.query(Applicant).filter(Applicant.branch_id == branch_id)
    if v := params.get("program"):
        q = q.filter(Applicant.program_id == int(v))
    if v := params.get("year"):
        q = q.filter(func.strftime("%Y", Applicant.application_date) == str(v))
    applicants = q.all()

    # founders drive gender/age distributions; fall back to applicant records
    biz_q = db.query(Business).filter(Business.branch_id == branch_id)
    if params.get("program"):
        biz_q = biz_q.filter(Business.program_id == int(params["program"]))
    businesses = biz_q.all()
    founder_rows = []
    if businesses:
        founder_rows = db.query(BusinessFounder).filter(
            BusinessFounder.business_id.in_([b.id for b in businesses])).all()

    applied = len(applicants)
    selected = len(businesses)
    graduated = sum(1 for b in businesses if b.graduation_status == "Graduated")

    def dist_for(attr_id, model):
        ids = {}
        for a in applicants:
            val = getattr(a, attr_id)
            if val:
                ids.setdefault(val, 0)
                ids[val] += 1
        out = []
        for i, cnt in ids.items():
            ref = db.get(model, i)
            if ref:
                out.append({"id": i, "name": ref.name, "count": cnt})
        return sorted(out, key=lambda x: -x["count"])

    genders = dist_for("gender_id", Gender)
    countries = dist_for("country_id", Country)
    provinces = dist_for("province_id", Province)
    districts = dist_for("district_id", District)
    industries = dist_for("industry_id", BusinessIndustry)

    age_counts: dict[str, int] = {}
    ages = [f.age for f in founder_rows if f.age] or [a.age for a in applicants if a.age]
    for band, lo, hi in AGE_BANDS:
        c = sum(1 for x in ages if x and lo <= x <= hi)
        if c:
            age_counts[band] = c

    return {
        "funnel": {"applied": applied, "selected": selected, "graduated": graduated},
        "tiles": {
            "graduation_rate": round(100.0 * graduated / selected, 1) if selected else 0.0,
            "selected_businesses": selected,
            "graduated_businesses": graduated,
            "selection_rate": round(100.0 * selected / applied, 1) if applied else 0.0,
        },
        "distributions": {
            "gender": genders,
            "industry": industries,
            "age": [{"name": k, "count": v} for k, v in age_counts.items()],
            "country": countries,
            "province": provinces,
            "district": districts,
            "stage_of_business": [
                {"id": t.id, "name": t.name,
                 "count": sum(1 for b in businesses if b.type_id == t.id)}
                for t in db.query(BusinessType).all()
            ],
        },
    }


@router.get("/dashboard-businesses/")
def dashboard_businesses(request: Request, ctx=Depends(require_branch_access())):
    """Businesses/Investment/Learning views aggregated from live data."""
    db: Session = ctx["db"]
    branch_id = ctx["branch_id"]
    from ..models import (
        Course, Enrollment, InvestmentCase, InvestmentStatus, InvestmentStage, InvestmentRound,
        User as U, UserRole,
    )
    params = request.query_params
    biz_q = db.query(Business).filter(Business.branch_id == branch_id)
    if params.get("program"):
        biz_q = biz_q.filter(Business.program_id == int(params["program"]))
    businesses = biz_q.all()

    cases = db.query(InvestmentCase).filter(InvestmentCase.branch_id == branch_id).all()
    approved_status = db.query(InvestmentStatus).filter_by(code_name="approved").first()
    approved_cases = [c for c in cases if approved_status and c.status_id == approved_status.id]

    courses = db.query(Course).filter(Course.branch_id == branch_id).all()
    enrollments = db.query(Enrollment).filter(
        Enrollment.course_id.in_([c.id for c in courses] or [0])).all()

    users_count = db.query(UserRole.user_id).filter(UserRole.branch_id == branch_id).distinct().count()

    stage_dist = {}
    stage_ref = {s.id: s.name for s in db.query(InvestmentStage).filter_by(branch_id=branch_id)}
    for c in cases:
        n = stage_ref.get(c.stage_id, "Unknown")
        stage_dist[n] = stage_dist.get(n, 0) + 1
    round_dist = {}
    rounds = {r.id: r.name for r in db.query(InvestmentRound).all()}
    for c in cases:
        if c.round_id:
            n = rounds.get(c.round_id, "?")
            round_dist[n] = round_dist.get(n, 0) + 1

    total_invested = sum(c.investment_amount or 0 for c in approved_cases)
    return {
        "businesses": {
            "total": len(businesses),
            "graduated": sum(1 for b in businesses if b.graduation_status == "Graduated"),
            "avg_course_progress": round(
                sum(b.course_progress or 0 for b in businesses) / len(businesses), 1) if businesses else 0,
            "avg_evaluator_score": round(
                sum(b.average_evaluator_score or 0 for b in businesses) / len(businesses), 1) if businesses else 0,
        },
        "investment": {
            "total_cases": len(cases),
            "approved": len(approved_cases),
            "total_invested": round(total_invested, 2),
            "by_stage": [{"name": k, "count": v} for k, v in stage_dist.items()],
            "by_round": [{"name": k, "count": v} for k, v in round_dist.items()],
        },
        "learning": {
            "courses": len(courses),
            "enrollments": len(enrollments),
            "completions": sum(1 for e in enrollments if e.completed_at),
            "completion_rate": round(
                100.0 * sum(1 for e in enrollments if e.completed_at) / len(enrollments), 1)
            if enrollments else 0.0,
        },
        "team": {"users": users_count},
    }
