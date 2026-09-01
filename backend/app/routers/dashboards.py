from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_branch_access
from ..models import (
    Applicant, Business, BusinessFounder, BusinessIndustry, BusinessType, Country, District,
    Gender, Province, DisbursementBatch, Program,
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

    # Disbursements aggregation per cohort / programme
    disb_q = db.query(DisbursementBatch).filter(DisbursementBatch.branch_id == branch_id)
    if params.get("program"):
        disb_q = disb_q.filter(DisbursementBatch.program_id == int(params["program"]))
    batches = disb_q.all()

    programs_map = {p.id: p.name for p in db.query(Program).filter(Program.branch_id == branch_id).all()}
    disb_by_program: dict[int, dict] = {}

    for b in batches:
        pid = b.program_id
        pname = programs_map.get(pid, f"Programme {pid}")
        if pid not in disb_by_program:
            disb_by_program[pid] = {
                "program_id": pid,
                "name": pname,
                "short_name": pname.replace("OCIF ", ""),
                "total_amount": 0.0,
                "processed_amount": 0.0,
                "draft_amount": 0.0,
                "batches_count": 0,
                "currency": b.currency or "USD",
            }
        amt = float(b.total_amount or 0.0)
        disb_by_program[pid]["batches_count"] += 1
        disb_by_program[pid]["total_amount"] += amt
        if b.status == "processed":
            disb_by_program[pid]["processed_amount"] += amt
        else:
            disb_by_program[pid]["draft_amount"] += amt

    if not params.get("program"):
        for pid, pname in programs_map.items():
            if pid not in disb_by_program:
                disb_by_program[pid] = {
                    "program_id": pid,
                    "name": pname,
                    "short_name": pname.replace("OCIF ", ""),
                    "total_amount": 0.0,
                    "processed_amount": 0.0,
                    "draft_amount": 0.0,
                    "batches_count": 0,
                    "currency": "USD",
                }

    disbursements_list = sorted(disb_by_program.values(), key=lambda x: -x["total_amount"])
    total_cohort_disbursements = sum(x["total_amount"] for x in disbursements_list)

    return {
        "funnel": {"applied": applied, "selected": selected, "graduated": graduated},
        "tiles": {
            "graduation_rate": round(100.0 * graduated / selected, 1) if selected else 0.0,
            "selected_businesses": selected,
            "graduated_businesses": graduated,
            "selection_rate": round(100.0 * selected / applied, 1) if applied else 0.0,
            "total_disbursed": round(total_cohort_disbursements, 2),
        },
        "disbursements": disbursements_list,
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


@router.get("/dashboard-drilldown/")
def dashboard_drilldown(request: Request, ctx=Depends(require_branch_access())):
    """Drill-down endpoint returning detailed startup/applicant records for any dashboard metric/chart category."""
    db: Session = ctx["db"]
    branch_id = ctx["branch_id"]
    params = request.query_params

    category = (params.get("category") or "").lower()
    value = params.get("value") or ""
    program_id = params.get("program")

    if category in ("stage", "stage of business"):
        # Look up in businesses
        btype = db.query(BusinessType).filter(BusinessType.name.ilike(value)).first()
        biz_q = db.query(Business).filter(Business.branch_id == branch_id)
        if program_id:
            try:
                biz_q = biz_q.filter(Business.program_id == int(program_id))
            except ValueError:
                pass
        if btype:
            biz_q = biz_q.filter(Business.type_id == btype.id)
        businesses = biz_q.all()
        return {
            "category": category,
            "value": value,
            "count": len(businesses),
            "results": [
                {
                    "id": b.id,
                    "business_name": b.name,
                    "founders": [f"{f.first_name} {f.last_name}".strip() for f in b.founders],
                    "program_name": b.program.name if b.program else None,
                    "type_name": btype.name if btype else None,
                    "graduation_status": b.graduation_status,
                    "course_progress": b.course_progress,
                    "average_score": b.average_evaluator_score,
                }
                for b in businesses
            ]
        }

    q = db.query(Applicant).filter(Applicant.branch_id == branch_id)
    if program_id:
        try:
            q = q.filter(Applicant.program_id == int(program_id))
        except ValueError:
            pass

    if category == "gender":
        gender = db.query(Gender).filter(Gender.name.ilike(value)).first()
        if gender:
            q = q.filter(Applicant.gender_id == gender.id)
    elif category == "industry":
        ind = db.query(BusinessIndustry).filter(BusinessIndustry.name.ilike(value)).first()
        if ind:
            q = q.filter(Applicant.industry_id == ind.id)
    elif category == "country":
        ctry = db.query(Country).filter(Country.name.ilike(value)).first()
        if ctry:
            q = q.filter(Applicant.country_id == ctry.id)
    elif category == "province":
        prov = db.query(Province).filter(Province.name.ilike(value)).first()
        if prov:
            q = q.filter(Applicant.province_id == prov.id)
    elif category == "district":
        dist = db.query(District).filter(District.name.ilike(value)).first()
        if dist:
            q = q.filter(Applicant.district_id == dist.id)
    elif category in ("age", "age band"):
        for band, lo, hi in AGE_BANDS:
            if band == value:
                q = q.filter(Applicant.age >= lo, Applicant.age <= hi)
                break

    applicants = q.order_by(Applicant.application_date.desc()).all()
    results = []
    for a in applicants:
        results.append({
            "id": a.id,
            "business_name": a.business_name or f"{a.first_name} {a.last_name}",
            "contact_name": f"{a.first_name} {a.last_name}".strip(),
            "email": a.email,
            "age": a.age,
            "program_name": a.program.name if a.program else None,
            "status": a.status.name if a.status else "Applied",
            "country": a.country.name if a.country else None,
            "average_score": a.average_score,
            "application_date": str(a.application_date or "")[:10],
        })

    return {
        "category": category,
        "value": value,
        "count": len(results),
        "results": results,
    }


@router.get("/dashboard-funnel-drilldown/")
def dashboard_funnel_drilldown(request: Request, ctx=Depends(require_branch_access())):
    """Drill-down for Funnel stages: Applied, Selected, Graduated."""
    db: Session = ctx["db"]
    branch_id = ctx["branch_id"]
    params = request.query_params

    stage = (params.get("stage") or "applied").lower()
    program_id = params.get("program")

    if stage in ("selected", "graduated"):
        biz_q = db.query(Business).filter(Business.branch_id == branch_id)
        if program_id:
            try:
                biz_q = biz_q.filter(Business.program_id == int(program_id))
            except ValueError:
                pass
        if stage == "graduated":
            biz_q = biz_q.filter(Business.graduation_status == "Graduated")
        businesses = biz_q.order_by(Business.created_at.desc()).all()
        return {
            "stage": stage,
            "count": len(businesses),
            "results": [
                {
                    "id": b.id,
                    "business_name": b.name,
                    "founders": [f"{f.first_name} {f.last_name}".strip() for f in b.founders],
                    "program_name": b.program.name if b.program else None,
                    "graduation_status": b.graduation_status,
                    "course_progress": b.course_progress,
                    "course_score": b.course_score,
                    "average_score": b.average_evaluator_score,
                    "created_at": str(b.created_at or "")[:10],
                }
                for b in businesses
            ]
        }
    else:  # applied
        q = db.query(Applicant).filter(Applicant.branch_id == branch_id)
        if program_id:
            try:
                q = q.filter(Applicant.program_id == int(program_id))
            except ValueError:
                pass
        applicants = q.order_by(Applicant.application_date.desc()).all()
        return {
            "stage": "applied",
            "count": len(applicants),
            "results": [
                {
                    "id": a.id,
                    "business_name": a.business_name or f"{a.first_name} {a.last_name}",
                    "founders": [f"{a.first_name} {a.last_name}".strip()],
                    "email": a.email,
                    "program_name": a.program.name if a.program else None,
                    "status": a.status.name if a.status else "Applied",
                    "average_score": a.average_score,
                    "country": a.country.name if a.country else None,
                    "created_at": str(a.application_date or "")[:10],
                }
                for a in applicants
            ]
        }

