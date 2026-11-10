import re

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_branch_access
from ..models import (
    Applicant, Business, BusinessFounder, BusinessIndustry, BusinessType, Country, District,
    Gender, Province, DisbursementBatch, DisbursementItem, Program,
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
    if v := params.get("year"):
        # "Selected" means a business that came out of the applicant pool of
        # that year — follow the applicant link; imports without one fall back
        # to their own creation year
        biz_q = biz_q.outerjoin(
            Applicant, Business.applicant_id == Applicant.id).filter(
            func.strftime("%Y",
                          func.coalesce(Applicant.application_date,
                                        Business.created_at)) == str(v))
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

    # Disbursements aggregation per cohort / programme. Track II cohorts live
    # in separate programmes ("OCIF - Track II - Cohort 3"), so when filtering
    # by a cohort programme, pull in its Track II sibling batches too — the
    # cohort's loan money belongs in the same story.
    disb_q = db.query(DisbursementBatch).filter(DisbursementBatch.branch_id == branch_id)
    program_filter = params.get("program")
    if program_filter:
        pid = int(program_filter)
        pname = db.get(Program, pid).name if db.get(Program, pid) else ""
        program_ids = [pid]
        if "track ii" not in pname.lower():
            m = re.search(r"cohort\s*(\d+)", pname.lower())
            if m:
                # digit match (not "cohort N") so the shared "Track II -
                # Cohorts 1 & 2" programme is caught for both 1 and 2
                program_ids += [p.id for p in db.query(Program).filter(
                    Program.branch_id == branch_id, Program.id != pid,
                    Program.name.ilike(f"%track ii%{m.group(1)}%")).all()]
        # a cohort's businesses can also receive items in batches filed under
        # OTHER programmes (e.g. iCash's Track II grant halves were recorded
        # under Cohort 2's programme) — pull those batches in too; the item
        # scoping below attributes every euro to the right cohort
        item_batch_ids = {r[0] for r in db.query(DisbursementItem.batch_id).join(
            Business, DisbursementItem.business_id == Business.id).filter(
            Business.program_id == pid).all()}
        if item_batch_ids:
            disb_q = disb_q.filter(or_(
                DisbursementBatch.program_id.in_(program_ids),
                DisbursementBatch.id.in_(item_batch_ids)))
        else:
            disb_q = disb_q.filter(DisbursementBatch.program_id.in_(program_ids))
    if v := params.get("year"):
        disb_q = disb_q.filter(func.strftime("%Y", DisbursementBatch.payment_date) == str(v))
    batches = disb_q.all()

    programs_map = {p.id: p.name for p in db.query(Program).filter(Program.branch_id == branch_id).all()}
    disb_by_program: dict[int, dict] = {}

    # the amounts a batch actually carries live on its included items --
    # batch-level totals can go stale when items are added/removed/excluded,
    # so the dashboard must agree with the disbursement module (item-based)
    from sqlalchemy import func as _func
    _item_rows = db.query(
        DisbursementItem.batch_id,
        _func.coalesce(_func.sum(DisbursementItem.amount), 0.0),
        _func.coalesce(_func.sum(DisbursementItem.amount_jod), 0.0),
    ).filter(
        DisbursementItem.batch_id.in_([b.id for b in batches]),
        DisbursementItem.is_included == True,   # noqa: E712
    ).group_by(DisbursementItem.batch_id).all() if batches else []
    _item_sums = {bid: (float(eur), float(jod)) for bid, eur, jod in _item_rows}

    # when a cohort is selected, scope every batch's item sums to businesses of
    # that cohort — sibling programmes ("Cohorts 1 & 2") mix cohorts, and even
    # own-programme batches can carry items of businesses that since moved.
    # Batches with no matching items must drop to zero, not keep stale sums.
    if program_filter:
        _scoped = {bid: (float(eur), float(jod)) for bid, eur, jod in db.query(
                DisbursementItem.batch_id,
                _func.coalesce(_func.sum(DisbursementItem.amount), 0.0),
                _func.coalesce(_func.sum(DisbursementItem.amount_jod), 0.0),
        ).join(Business, DisbursementItem.business_id == Business.id).filter(
                DisbursementItem.batch_id.in_([b.id for b in batches]),
                DisbursementItem.is_included == True,   # noqa: E712
                Business.program_id == int(program_filter),
        ).group_by(DisbursementItem.batch_id).all()}
        _item_sums = {b.id: _scoped.get(b.id, (0.0, 0.0)) for b in batches}

    for b in batches:
        # when a cohort programme is selected, its Track II sibling batches
        # roll up under the same row — one bar, one story
        pid = int(program_filter) if program_filter else b.program_id
        pname = programs_map.get(pid, f"Programme {pid}")
        if pid not in disb_by_program:
            disb_by_program[pid] = {
                "program_id": pid,
                "name": pname,
                "short_name": pname.replace("OCIF ", ""),
                "total_amount": 0.0,
                "total_amount_eur": 0.0,
                "total_amount_jod": 0.0,
                "processed_amount": 0.0,
                "processed_amount_eur": 0.0,
                "processed_amount_jod": 0.0,
                "draft_amount": 0.0,
                "draft_amount_eur": 0.0,
                "draft_amount_jod": 0.0,
                "batches_count": 0,
                "currency": b.currency or "EUR",
                "disbursement_currency": getattr(b, "disbursement_currency", None) or "JOD",
                "exchange_rate": float(getattr(b, "exchange_rate", None) if getattr(b, "exchange_rate", None) is not None else 0.76),
            }
        amt_eur, amt_jod = _item_sums.get(b.id, (0.0, 0.0))
        rate = float(getattr(b, "exchange_rate", None) if getattr(b, "exchange_rate", None) is not None else 0.76)

        disb_by_program[pid]["batches_count"] += 1
        disb_by_program[pid]["total_amount"] += amt_eur
        disb_by_program[pid]["total_amount_eur"] += amt_eur
        disb_by_program[pid]["total_amount_jod"] += amt_jod
        if b.status == "processed":
            disb_by_program[pid]["processed_amount"] += amt_eur
            disb_by_program[pid]["processed_amount_eur"] += amt_eur
            disb_by_program[pid]["processed_amount_jod"] += amt_jod
        else:
            disb_by_program[pid]["draft_amount"] += amt_eur
            disb_by_program[pid]["draft_amount_eur"] += amt_eur
            disb_by_program[pid]["draft_amount_jod"] += amt_jod

    if not params.get("program"):
        for pid, pname in programs_map.items():
            if pid not in disb_by_program:
                disb_by_program[pid] = {
                    "program_id": pid,
                    "name": pname,
                    "short_name": pname.replace("OCIF ", ""),
                    "total_amount": 0.0,
                    "total_amount_eur": 0.0,
                    "total_amount_jod": 0.0,
                    "processed_amount": 0.0,
                    "processed_amount_eur": 0.0,
                    "processed_amount_jod": 0.0,
                    "draft_amount": 0.0,
                    "draft_amount_eur": 0.0,
                    "draft_amount_jod": 0.0,
                    "batches_count": 0,
                    "currency": "EUR",
                    "disbursement_currency": "JOD",
                    "exchange_rate": 0.76,
                }

    disbursements_list = sorted(disb_by_program.values(), key=lambda x: -x["total_amount_eur"])
    total_cohort_disbursements_eur = sum(x["total_amount_eur"] for x in disbursements_list)
    total_cohort_disbursements_jod = sum(x["total_amount_jod"] for x in disbursements_list)

    # headline disbursement tiles for the dashboard home — same classification
    # and item-based sums as the disbursements module's summary endpoint,
    # restricted to the current program/year filters
    from .repayments import _classify_disbursement
    by_track = {
        "grant_I": {"eur": 0.0, "jod": 0.0, "batches": 0},
        "loan_II": {"eur": 0.0, "jod": 0.0, "batches": 0},
        "grant_II": {"eur": 0.0, "jod": 0.0, "batches": 0},
    }
    processed_eur = processed_jod = 0.0
    draft_batches = 0
    for b in batches:
        eur, jod = _item_sums.get(b.id, (0.0, 0.0))
        if b.status != "processed":
            draft_batches += 1
            continue
        processed_eur += eur
        processed_jod += jod
        kind, track = _classify_disbursement(b.title)
        key = f"{kind}_{track}"
        if key in by_track:
            by_track[key]["eur"] += eur
            by_track[key]["jod"] += jod
            by_track[key]["batches"] += 1
    disbursement_summary = {
        "processed_eur": round(processed_eur, 2),
        "disbursed_jod": round(processed_jod, 3),
        "draft_batches": draft_batches,
        "by_track": by_track,
    }

    return {
        "funnel": {"applied": applied, "selected": selected, "graduated": graduated},
        "tiles": {
            "graduation_rate": round(100.0 * graduated / selected, 1) if selected else 0.0,
            "selected_businesses": selected,
            "graduated_businesses": graduated,
            "selection_rate": round(100.0 * selected / applied, 1) if applied else 0.0,
            "total_disbursed": round(total_cohort_disbursements_eur, 2),
            "total_disbursed_eur": round(total_cohort_disbursements_eur, 2),
            "total_disbursed_jod": round(total_cohort_disbursements_jod, 3),
            "currency": "EUR",
            "disbursement_currency": "JOD",
        },
        "disbursement_summary": disbursement_summary,
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


@router.get("/dashboard-loans-by-cohort/")
def dashboard_loans_by_cohort(request: Request, ctx=Depends(require_branch_access())):
    """Per-cohort loan figures for the dashboard chart: approved (EUR), the
    principal disbursed (EUR + JOD at each loan's own rate), collected and the
    recovery percentage -- both outstanding views included."""
    db: Session = ctx["db"]
    branch_id = ctx["branch_id"]
    from ..models import LoanRepayment, PaymentScheduleEntry, RepaymentBatch, \
        InvestmentCase, Business, Program

    cases = db.query(InvestmentCase).filter(
        InvestmentCase.branch_id == branch_id,
        InvestmentCase.investment_amount > 0).all()
    processed_ids = {b.id for b in db.query(RepaymentBatch.id).filter(
        RepaymentBatch.branch_id == branch_id,
        RepaymentBatch.status == "processed").all()}
    repayments = [r for r in db.query(LoanRepayment).filter(
        LoanRepayment.branch_id == branch_id).all()
        if r.status == "completed" and (r.batch_id is None or r.batch_id in processed_ids)]

    from ..routers.repayments import _case_repay_position
    rows = {}
    for c in cases:
        if not c.business_id:
            continue
        biz = db.get(Business, c.business_id)
        prog = biz.program if biz else None
        if prog is None:
            continue
        key = prog.id
        row = rows.setdefault(key, {
            "program_id": prog.id, "cohort": prog.name,
            "approved_eur": 0.0, "disbursed_eur": 0.0, "disbursed_jod": 0.0,
            "collected_eur": 0.0, "collected_jod": 0.0,
            "outstanding_principal_eur": 0.0, "outstanding_incl_eur": 0.0,
            "loans": 0,
        })
        row["approved_eur"] += float(c.investment_amount or 0.0)
        disb_eur = float(c.disbursement_amount or 0.0)
        disb_jod = float(c.disbursement_amount_jod or 0.0)
        # only count disbursed loans (never-disbursed cases have nothing to chart)
        if disb_eur > 0 or disb_jod > 0:
            row["loans"] += 1
            row["disbursed_eur"] += disb_eur
            row["disbursed_jod"] += disb_jod
            case_reps = [r for r in repayments if r.case_id == c.id]
            entries = db.query(PaymentScheduleEntry).filter(
                PaymentScheduleEntry.case_id == c.id).all()
            pos = _case_repay_position(c, case_reps, entries)
            sccy = (entries[0].currency or "").upper() if entries else                 str(c.currency or "").upper()
            rate = float(c.forex_rate or 0.76) or 0.76
            if sccy == "EUR":
                row["collected_eur"] += pos["settled_principal_i"] + pos["settled_charges_i"]
                row["collected_jod"] += (pos["settled_principal_i"] + pos["settled_charges_i"]) * rate
            else:
                row["collected_jod"] += pos["settled_principal_i"] + pos["settled_charges_i"]
                row["collected_eur"] += (pos["settled_principal_i"] + pos["settled_charges_i"]) / rate
            row["outstanding_principal_eur"] += pos["principal_out_eur"]
            row["outstanding_incl_eur"] += pos["incl_out_eur"]

    out = []
    for r in rows.values():
        disb_eur = round(r["disbursed_eur"], 2)
        r["collected_eur"] = round(r["collected_eur"], 2)
        r["collected_jod"] = round(r["collected_jod"], 2)
        r["disbursed_jod"] = round(r["disbursed_jod"], 2)
        r["pct_repaid"] = round(100.0 * r["collected_jod"] / r["disbursed_jod"], 1) \
            if r["disbursed_jod"] > 0 else 0.0
        out.append(r)
    out.sort(key=lambda r: r["cohort"])
    return {"results": out, "count": len(out)}


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
    if v := params.get("year"):
        # same selection-year semantics as the program dashboard: follow the
        # applicant link, fall back to the business's own creation year
        biz_q = biz_q.outerjoin(
            Applicant, Business.applicant_id == Applicant.id).filter(
            func.strftime("%Y",
                          func.coalesce(Applicant.application_date,
                                        Business.created_at)) == str(v))
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

