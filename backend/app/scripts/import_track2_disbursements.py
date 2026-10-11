"""Script to import and reconcile official Track II blended finance disbursements.

Dataset source: OCIF Jordan — Track II: Approved Amounts & Disbursements by Startup (EUR).
Reconciliation to 30 June 2026 + July 2026 Loan Disbursals.

Contains:
- Cohorts 1 & 2 Track II:
  * Tranche 1 (S3) Jan–Jun 2025: EUR 90,000.00 (7 startups)
  * Tranche 2 (S4) Jul–Dec 2025: EUR 30,000.00 (7 startups)
  * Tranche 3 (S5) Jan–Jun 2026: EUR 39,000.00 (7 startups)
  * Sub-total: EUR 159,000.00
- Cohort 3 Track II:
  * Loan Tranche July 2026: EUR 96,000.00 (7 startups)
  * Sub-total: EUR 96,000.00
- Grand Total Track II Disbursed: EUR 255,000.00 across 4 batches
- Full Dealflow InvestmentCase & PaymentScheduleEntry creation for all 14 winners
"""
import sys
import os
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import (
    Program, ProgramType, ProgramStatus, Business, BusinessFounder,
    DisbursementBatch, DisbursementItem, User, InvestmentCase,
    PaymentScheduleEntry, FinanceTimelineEntry, InvestmentStage,
    InvestmentStatus, InvestmentTier, InvestmentRound, Applicant, SelectionStage, ApplicantStatus
)

COHORT12_TRACK2_STARTUPS = [
    {
        "name": "OrganicG",
        "alias": "OrganicG",
        "ceo": "Randa Kamal Aliyan",
        "loan_approved": 22500.0,
        "grant_approved": 15000.0,
        "total_approved": 37500.0,
        "s3": 13500.0,
        "s4": 4500.0,
        "s5": 13500.0,  # includes 9,000 additional loan disbursed 24 Jun 2026
        "disbursed": 31500.0,
        "undisbursed": 6000.0,
        "notes": "Includes €9,000 additional loan disbursed 24 Jun 2026; €6,000 grant remains undisbursed @ 30 Jun.",
    },
    {
        "name": "PhytoBase",
        "alias": "Smart Green for Phytobase Solution",
        "ceo": "Ali Bassam Saqer Marayhah",
        "loan_approved": 13500.0,
        "grant_approved": 9000.0,
        "total_approved": 22500.0,
        "s3": 13500.0,
        "s4": 4500.0,
        "s5": 4500.0,
        "disbursed": 22500.0,
        "undisbursed": 0.0,
        "notes": "Fully disbursed blended package.",
    },
    {
        "name": "iCash",
        "alias": "iCash",
        "ceo": "Mohammad Esam Hussein Yaseen",
        "loan_approved": 13500.0,
        "grant_approved": 9000.0,
        "total_approved": 22500.0,
        "s3": 13500.0,
        "s4": 4500.0,
        "s5": 4500.0,
        "disbursed": 22500.0,
        "undisbursed": 0.0,
        "notes": "Fully disbursed blended package.",
    },
    {
        "name": "Avancer",
        "alias": "Avancer",
        "ceo": "Abdelrazzaq Majid Mohammed Al-Hadidi",
        "loan_approved": 13500.0,
        "grant_approved": 9000.0,
        "total_approved": 22500.0,
        "s3": 13500.0,
        "s4": 4500.0,
        "s5": 4500.0,
        "disbursed": 22500.0,
        "undisbursed": 0.0,
        "notes": "Fully disbursed blended package.",
    },
    {
        "name": "EduHax",
        "alias": "Math Mania",
        "ceo": "Yazan Nabeel Tadros",
        "loan_approved": 22500.0,
        "grant_approved": 15000.0,
        "total_approved": 37500.0,
        "s3": 13500.0,
        "s4": 4500.0,
        "s5": 4500.0,
        "disbursed": 22500.0,
        "undisbursed": 15000.0,
        "notes": "Initial loan (€13,500) and grants (€9,000) disbursed; second funding tranche of €15,000 (€9,000 loan and €6,000 grant) has not been disbursed.",
    },
    {
        "name": "Denally",
        "alias": "Denally",
        "ceo": "Yousri Abdel Fattah Hamed",
        "loan_approved": 9000.0,
        "grant_approved": 6000.0,
        "total_approved": 15000.0,
        "s3": 9000.0,
        "s4": 3000.0,
        "s5": 3000.0,
        "disbursed": 15000.0,
        "undisbursed": 0.0,
        "notes": "Fully disbursed blended package.",
    },
    {
        "name": "BabPlus",
        "alias": "Bab Plus",
        "ceo": "Omar Hamza Hammad",
        "loan_approved": 13500.0,
        "grant_approved": 9000.0,
        "total_approved": 22500.0,
        "s3": 13500.0,
        "s4": 4500.0,
        "s5": 4500.0,
        "disbursed": 22500.0,
        "undisbursed": 0.0,
        "notes": "Fully disbursed blended package.",
    },
]

COHORT3_TRACK2_STARTUPS = [
    {
        "name": "Dragon Ferti",
        "alias": "Dragon Ferti",
        "ceo": "Hanadi Husain Ibrahim Al Hyari",
        "loan_approved": 30000.0,
        "grant_approved": 20000.0,
        "total_approved": 50000.0,
        "s3": 0.0,
        "s4": 0.0,
        "s5": 0.0,
        "jul26_loan": 30000.0,
        "disbursed": 30000.0,
        "undisbursed": 20000.0,
        "notes": "Loan (€30,000) disbursed July 2026; grants (€20,000) staggered at +3m and +6m.",
    },
    {
        "name": "GGEZ1",
        "alias": "GGEZ1",
        "ceo": "Mu'Taz Ma'En Rafiq Majdoub",
        "loan_approved": 12000.0,
        "grant_approved": 8000.0,
        "total_approved": 20000.0,
        "s3": 0.0,
        "s4": 0.0,
        "s5": 0.0,
        "jul26_loan": 12000.0,
        "disbursed": 12000.0,
        "undisbursed": 8000.0,
        "notes": "Loan (€12,000) disbursed July 2026; grants (€8,000) staggered at +3m and +6m.",
    },
    {
        "name": "The Act Cast",
        "alias": "THE ACT CAST",
        "ceo": "Aseel Ihssan Mahmoud Yaseen",
        "loan_approved": 13500.0,
        "grant_approved": 9000.0,
        "total_approved": 22500.0,
        "s3": 0.0,
        "s4": 0.0,
        "s5": 0.0,
        "jul26_loan": 13500.0,
        "disbursed": 13500.0,
        "undisbursed": 9000.0,
        "notes": "Loan (€13,500) disbursed July 2026; grants (€9,000) staggered at +3m and +6m.",
    },
    {
        "name": "House of Shorouq",
        "alias": "House of Shorouq",
        "ceo": "Shrouq Mohammad Mahmoud Al-Mazrawi",
        "loan_approved": 9000.0,
        "grant_approved": 6000.0,
        "total_approved": 15000.0,
        "s3": 0.0,
        "s4": 0.0,
        "s5": 0.0,
        "jul26_loan": 9000.0,
        "disbursed": 9000.0,
        "undisbursed": 6000.0,
        "notes": "Loan (€9,000) disbursed July 2026; grants (€6,000) staggered at +3m and +6m.",
    },
    {
        "name": "House of Dolls",
        "alias": "بنات العيله للحياكه",
        "ceo": "Suad Yahia Ahmad Battikha",
        "loan_approved": 9000.0,
        "grant_approved": 6000.0,
        "total_approved": 15000.0,
        "s3": 0.0,
        "s4": 0.0,
        "s5": 0.0,
        "jul26_loan": 9000.0,
        "disbursed": 9000.0,
        "undisbursed": 6000.0,
        "notes": "Loan (€9,000) disbursed July 2026; grants (€6,000) staggered at +3m and +6m.",
    },
    {
        "name": "BarqBoxes",
        "alias": "BarqBoxes",
        "ceo": "Moayad Mahmoud Abed Alnajdawi",
        "loan_approved": 9000.0,
        "grant_approved": 6000.0,
        "total_approved": 15000.0,
        "s3": 0.0,
        "s4": 0.0,
        "s5": 0.0,
        "jul26_loan": 9000.0,
        "disbursed": 9000.0,
        "undisbursed": 6000.0,
        "notes": "Loan (€9,000) disbursed July 2026; grants (€6,000) staggered at +3m and +6m.",
    },
    {
        "name": "EXP",
        "alias": "ERP System \"EXP\"",
        "ceo": "Hamza Mahmmoud Abed Shaheen",
        "loan_approved": 13500.0,
        "grant_approved": 9000.0,
        "total_approved": 22500.0,
        "s3": 0.0,
        "s4": 0.0,
        "s5": 0.0,
        "jul26_loan": 0.0,
        "disbursed": 0.0,
        "undisbursed": 22500.0,
        "notes": "Loan and grants not disbursed yet / pending disbursement.",
    },
]


def norm(t: str) -> str:
    return ''.join(c.lower() for c in (t or '') if c.isalnum())


def import_track2_disbursements(db: Session, branch_id: int = 1):
    admin_user = db.query(User).filter(User.email.like("%admin%")).first()
    prog_status = db.query(ProgramStatus).first()
    prog_type = db.query(ProgramType).filter(ProgramType.branch_id == branch_id).first()
    if not prog_type:
        prog_type = db.query(ProgramType).first()

    # 1. Ensure Track II Programs exist
    p_track2_c12 = db.query(Program).filter(
        Program.branch_id == branch_id,
        Program.name.like("%Track II%Cohort%1%2%") | Program.name.like("%Track II%Cohorts 1 & 2%")
    ).first()
    if not p_track2_c12:
        p_track2_c12 = Program(
            branch_id=branch_id,
            program_type_id=prog_type.id if prog_type else 1,
            name="OCIF - Track II - Cohorts 1 & 2",
            status_id=prog_status.id if prog_status else None,
            creation_date=datetime(2025, 1, 15),
        )
        db.add(p_track2_c12)
        db.flush()

    p_track2_c3 = db.query(Program).filter(
        Program.branch_id == branch_id,
        Program.name.like("%Track II%Cohort 3%") | Program.name.like("%Track II%Cohort%3%")
    ).first()
    if not p_track2_c3:
        p_track2_c3 = Program(
            branch_id=branch_id,
            program_type_id=prog_type.id if prog_type else 1,
            name="OCIF - Track II - Cohort 3",
            status_id=prog_status.id if prog_status else None,
            creation_date=datetime(2025, 8, 1),
        )
        db.add(p_track2_c3)
        db.flush()

    # Clean any stray temporary BabPlus or Denally business in Track II program
    stray_babs = db.query(Business).filter(
        Business.branch_id == branch_id,
        Business.program_id == p_track2_c12.id,
        Business.name.in_(["BabPlus", "Denally"])
    ).all()
    for sb in stray_babs:
        db.delete(sb)
    db.commit()

    # Refresh businesses map
    all_businesses = db.query(Business).filter(Business.branch_id == branch_id).all()
    biz_by_name = {norm(b.name): b for b in all_businesses}

    # Match Cohorts 1 & 2 businesses
    c12_biz_map = {}
    for item in COHORT12_TRACK2_STARTUPS:
        b = biz_by_name.get(norm(item["name"])) or biz_by_name.get(norm(item["alias"]))
        if not b:
            for bn, candidate in biz_by_name.items():
                if norm(item["name"]) in bn or bn in norm(item["name"]) or norm(item["alias"]) in bn:
                    b = candidate
                    break
        if not b:
            raise ValueError(f"Could not map Track II startup: {item['name']}")
        c12_biz_map[item["name"]] = (b, item)

    # Match Cohort 3 businesses
    c3_biz_map = {}
    for item in COHORT3_TRACK2_STARTUPS:
        b = biz_by_name.get(norm(item["name"])) or biz_by_name.get(norm(item["alias"]))
        if not b:
            for bn, candidate in biz_by_name.items():
                if norm(item["name"]) in bn or bn in norm(item["name"]) or norm(item["alias"]) in bn:
                    b = candidate
                    break
        if not b:
            raise ValueError(f"Could not map Cohort 3 Track II startup: {item['name']}")
        c3_biz_map[item["name"]] = (b, item)

    # 3. Clean any existing Track II disbursement batches for idempotency
    for p_id in [p_track2_c12.id, p_track2_c3.id]:
        ebs = db.query(DisbursementBatch).filter(
            DisbursementBatch.branch_id == branch_id,
            DisbursementBatch.program_id == p_id
        ).all()
        for eb in ebs:
            db.delete(eb)
        db.commit()

    # 4. Create Cohorts 1 & 2 Track II Disbursement Batches
    c12_batches_meta = [
        ("Cohort 1 & 2 Track II: Tranche 1 (S3) — H1 Year 2 (Jan–Jun 2025)", date(2025, 6, 30), "s3"),
        ("Cohort 1 & 2 Track II: Tranche 2 (S4) — H2 Year 2 (Jul–Dec 2025)", date(2025, 12, 31), "s4"),
        ("Cohort 1 & 2 Track II: Tranche 3 (S5) — H1 Year 3 (Jan–Jun 2026)", date(2026, 6, 30), "s5"),
    ]

    total_c12_disbursed = 0.0
    for title, p_date, col_key in c12_batches_meta:
        batch = DisbursementBatch(
            branch_id=branch_id,
            program_id=p_track2_c12.id,
            title=title,
            payment_date=p_date,
            currency="EUR",
            disbursement_currency="JOD",
            exchange_rate=0.76,
            base_amount=0.0,
            notes=f"Track II blended finance disbursement for {title} (Reconciled).",
            status="processed",
            confirmed_by_id=admin_user.id if admin_user else None,
            confirmed_at=datetime(p_date.year, p_date.month, p_date.day, 12, 0),
        )
        db.add(batch)
        db.flush()

        b_total = 0.0
        b_total_jod = 0.0
        for s_data in COHORT12_TRACK2_STARTUPS:
            b, _ = c12_biz_map[s_data["name"]]
            amt = float(s_data[col_key])
            pct = 100.0 if amt > 0 else 0.0
            is_inc = (amt > 0)
            note = s_data["notes"] if col_key == "s5" else "Scheduled blended finance tranche"
            amt_jod = round(amt * 0.76, 3)
            db.add(DisbursementItem(
                batch_id=batch.id,
                business_id=b.id,
                percentage=pct,
                amount=amt,
                amount_jod=amt_jod,
                disbursement_date=p_date,
                exchange_rate=0.76,
                is_included=is_inc,
                notes=note
            ))
            b_total += amt
            b_total_jod += amt_jod

        batch.total_amount = b_total
        batch.total_amount_jod = round(b_total_jod, 3)
        db.commit()
        total_c12_disbursed += b_total
        print(f"Created Track II Batch: '{batch.title}' -> Total: EUR {b_total:,.2f}")

    # 5. Create Cohort 3 Track II Loan Disbursement Batch (July 2026)
    c3_date = date(2026, 7, 31)
    batch_c3 = DisbursementBatch(
        branch_id=branch_id,
        program_id=p_track2_c3.id,
        title="Cohort 3 Track II: Loan Tranche — July 2026",
        payment_date=c3_date,
        currency="EUR",
        disbursement_currency="JOD",
        exchange_rate=0.76,
        base_amount=0.0,
        notes="Track II loan package disbursement for Cohort 3 (July 2026). Grants (€64,000) staggered at +3m and +6m.",
        status="processed",
        confirmed_by_id=admin_user.id if admin_user else None,
        confirmed_at=datetime(2026, 7, 31, 12, 0),
    )
    db.add(batch_c3)
    db.flush()

    c3_total = 0.0
    c3_total_jod = 0.0
    for s_data in COHORT3_TRACK2_STARTUPS:
        b, _ = c3_biz_map[s_data["name"]]
        amt = float(s_data["jul26_loan"])
        pct = 100.0 if amt > 0 else 0.0
        is_inc = (amt > 0)
        amt_jod = round(amt * 0.76, 3)
        db.add(DisbursementItem(
            batch_id=batch_c3.id,
            business_id=b.id,
            percentage=pct,
            amount=amt,
            amount_jod=amt_jod,
            disbursement_date=c3_date,
            exchange_rate=0.76,
            is_included=is_inc,
            notes=s_data["notes"]
        ))
        c3_total += amt
        c3_total_jod += amt_jod

    batch_c3.total_amount = c3_total
    batch_c3.total_amount_jod = round(c3_total_jod, 3)
    db.commit()
    print(f"Created Track II Batch: '{batch_c3.title}' -> Total: EUR {c3_total:,.2f}")

    # 6. Dealflow / InvestmentCase Creation for all 14 winners
    stage = db.query(InvestmentStage).filter_by(branch_id=branch_id).order_by(InvestmentStage.order.desc()).first()
    status_approved = db.query(InvestmentStatus).filter(InvestmentStatus.code_name.in_(["approved", "funded", "active"])).first()
    tier = db.query(InvestmentTier).first()
    iround = db.query(InvestmentRound).first()

    # Clear previous cases for these businesses to prevent duplicates
    all_track2_biz_ids = [b.id for b, _ in list(c12_biz_map.values()) + list(c3_biz_map.values())]
    old_cases = db.query(InvestmentCase).filter(
        InvestmentCase.branch_id == branch_id,
        InvestmentCase.business_id.in_(all_track2_biz_ids)
    ).all()
    for oc in old_cases:
        db.delete(oc)
    db.commit()

    created_cases = 0
    # Add Cohorts 1 & 2 Cases
    for s_data in COHORT12_TRACK2_STARTUPS:
        b, _ = c12_biz_map[s_data["name"]]
        case = InvestmentCase(
            branch_id=branch_id,
            business_id=b.id,
            company_name=b.name,
            type_id=b.type_id,
            industry_id=b.industry_id,
            tier_id=tier.id if tier else None,
            round_id=iround.id if iround else None,
            stage_id=stage.id if stage else None,
            status_id=status_approved.id if status_approved else None,
            owner_id=admin_user.id if admin_user else None,
            amount_requested=s_data["total_approved"],
            investment_amount=s_data["loan_approved"],
            co_financing_amount=s_data["grant_approved"],
            currency="EUR",
            ceo_name=s_data["ceo"],
            sustainability_notes="Blended finance package (60% loan / 40% grant).",
            innovation_notes=s_data["notes"],
        )
        db.add(case)
        db.flush()

        # Payment schedule entries
        case.payments.append(PaymentScheduleEntry(
            case_id=case.id, due_date=date(2025, 6, 30), amount=s_data["s3"], paid=True, paid_date=date(2025, 6, 30)
        ))
        case.payments.append(PaymentScheduleEntry(
            case_id=case.id, due_date=date(2025, 12, 31), amount=s_data["s4"], paid=True, paid_date=date(2025, 12, 31)
        ))
        case.payments.append(PaymentScheduleEntry(
            case_id=case.id, due_date=date(2026, 6, 30), amount=s_data["s5"], paid=True, paid_date=date(2026, 6, 30)
        ))
        if s_data["name"] == "EduHax":
            case.payments.append(PaymentScheduleEntry(
                case_id=case.id, due_date=date(2026, 12, 31), amount=9000.0, paid=False, paid_date=None
            ))
            case.payments.append(PaymentScheduleEntry(
                case_id=case.id, due_date=date(2027, 3, 31), amount=6000.0, paid=False, paid_date=None
            ))
        elif s_data["undisbursed"] > 0:
            case.payments.append(PaymentScheduleEntry(
                case_id=case.id, due_date=date(2026, 12, 31), amount=s_data["undisbursed"], paid=False, paid_date=None
            ))

        # Timeline entries
        case.timeline_entries.append(FinanceTimelineEntry(
            case_id=case.id, entry_date=date(2025, 6, 30), label="Tranche 1 (S3) Disbursement", amount=s_data["s3"], direction="out"
        ))
        case.timeline_entries.append(FinanceTimelineEntry(
            case_id=case.id, entry_date=date(2025, 12, 31), label="Tranche 2 (S4) Disbursement", amount=s_data["s4"], direction="out"
        ))
        case.timeline_entries.append(FinanceTimelineEntry(
            case_id=case.id, entry_date=date(2026, 6, 30), label="Tranche 3 (S5) Disbursement", amount=s_data["s5"], direction="out"
        ))
        created_cases += 1

    # Add Cohort 3 Cases
    for s_data in COHORT3_TRACK2_STARTUPS:
        b, _ = c3_biz_map[s_data["name"]]
        case = InvestmentCase(
            branch_id=branch_id,
            business_id=b.id,
            company_name=b.name,
            type_id=b.type_id,
            industry_id=b.industry_id,
            tier_id=tier.id if tier else None,
            round_id=iround.id if iround else None,
            stage_id=stage.id if stage else None,
            status_id=status_approved.id if status_approved else None,
            owner_id=admin_user.id if admin_user else None,
            amount_requested=s_data["total_approved"],
            investment_amount=s_data["loan_approved"],
            co_financing_amount=s_data["grant_approved"],
            currency="EUR",
            ceo_name=s_data["ceo"],
            sustainability_notes="Blended finance package (60% loan / 40% grant). Grants staggered at +3m and +6m.",
            innovation_notes=s_data["notes"],
        )
        db.add(case)
        db.flush()

        # Payment schedule entries
        loan_is_paid = bool(s_data.get("jul26_loan", 0) > 0)
        case.payments.append(PaymentScheduleEntry(
            case_id=case.id,
            due_date=date(2026, 7, 31),
            amount=s_data["loan_approved"],
            paid=loan_is_paid,
            paid_date=date(2026, 7, 31) if loan_is_paid else None
        ))
        case.payments.append(PaymentScheduleEntry(
            case_id=case.id, due_date=date(2026, 10, 31), amount=s_data["grant_approved"] * 0.5, paid=False, paid_date=None
        ))
        case.payments.append(PaymentScheduleEntry(
            case_id=case.id, due_date=date(2027, 1, 31), amount=s_data["grant_approved"] * 0.5, paid=False, paid_date=None
        ))

        # Timeline entry (only if loan was disbursed)
        if loan_is_paid:
            case.timeline_entries.append(FinanceTimelineEntry(
                case_id=case.id, entry_date=date(2026, 7, 31), label="Loan Tranche Disbursement", amount=s_data["loan_approved"], direction="out"
            ))
        created_cases += 1

    db.commit()
    print(f"Created {created_cases} Dealflow InvestmentCase records for Track II winners.")

    # 7. Assign stages & statuses:
    # Cohorts 1 & 2 Track II participants completed the programme in June 2026
    stage_prog = db.query(SelectionStage).filter(
        SelectionStage.branch_id == branch_id,
        SelectionStage.name.ilike("%programme completed%")
    ).first()
    status_prog = db.query(ApplicantStatus).filter(
        ApplicantStatus.code_name == "programme_completed"
    ).first()

    for b, _ in c12_biz_map.values():
        b.graduation_status = "Programme Completed"
        app = db.query(Applicant).filter(
            (Applicant.branch_id == branch_id) &
            ((Applicant.id == b.applicant_id) | (Applicant.business_name == b.name))
        ).first()
        if app:
            if stage_prog:
                app.selection_stage_id = stage_prog.id
            if status_prog:
                app.status_id = status_prog.id

    # Cohort 3 Track II startups are STILL IN TRACK II (loan disbursed July 2026; grants ongoing)
    stage_t2 = db.query(SelectionStage).filter(
        SelectionStage.branch_id == branch_id,
        SelectionStage.name.ilike("%track ii support%")
    ).first()
    status_invited = db.query(ApplicantStatus).filter(
        ApplicantStatus.code_name == "invited"
    ).first()

    for b, _ in c3_biz_map.values():
        b.graduation_status = "Track II Winner"
        app = db.query(Applicant).filter(
            (Applicant.branch_id == branch_id) &
            ((Applicant.id == b.applicant_id) | (Applicant.business_name == b.name))
        ).first()
        if app:
            if stage_t2:
                app.selection_stage_id = stage_t2.id
            if status_invited:
                app.status_id = status_invited.id

    db.commit()
    print("Assigned Cohort 1 & 2 Track II alumni to 'Programme Completed', and Cohort 3 startups still in Track II to 'Track II Support' / 'Invited'.")

    print(f"\nTrack II import summary:")
    print(f"  - Cohorts 1 & 2 Disbursed: EUR {total_c12_disbursed:,.2f} (3 batches)")
    print(f"  - Cohort 3 Disbursed: EUR {c3_total:,.2f} (1 batch)")
    print(f"  - Total Track II Disbursed: EUR {total_c12_disbursed + c3_total:,.2f}")
    print(f"  - Investment Cases: {created_cases}")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        import_track2_disbursements(db, branch_id=1)
    finally:
        db.close()
