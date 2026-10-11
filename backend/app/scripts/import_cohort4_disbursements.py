"""Script to import and reconcile official Cohort 4 Track I Payments.

Dataset source: OCIF Jordan — Cohort 4 Track I: Payments by Startup and Month (EUR).
Reconciled for July 2026 and August 2026.
Contains:
- July 2026 Monthly Allowance Batch (paid 2026-07-31) @ EUR 250 base:
    - 37 startups paid = EUR 9,250.00 (7,030.000 JOD)
    - 3 startups pending compliance/bank details (BRAINTECH AI, Nurse Home, Minimed Tender) = EUR 0.00
    - Total: EUR 9,250.00
- August 2026 Monthly Allowance Batch (paid 2026-08-11) @ EUR 250 base:
    - 39 startups paid = EUR 9,750.00 (7,410.000 JOD) (Nurse Home & Minimed Tender resolved and paid)
    - 1 startup pending compliance/bank details (BRAINTECH AI) = EUR 0.00
    - Total: EUR 9,750.00
"""
import sys
import os
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Program, Business, BusinessFounder, Applicant, DisbursementBatch, DisbursementItem, User

# List of 40 Cohort 4 startups:
# (index, startup_name, recipient_name, jul_amount, aug_amount)
COHORT4_DATA = [
    (1, 'EV Solution', 'Basel Saleh Salou', 250.0, 250.0),
    (2, 'RehabLex', 'Zaid Amin Dayarneh', 250.0, 250.0),
    (3, 'IRIS', 'Tareq Khedr Hamdan', 250.0, 250.0),
    (4, 'Qatrah', 'Dalia Ziad Abboud', 250.0, 250.0),
    (5, 'iLegalWorks - Ask AzzamAI: Your Bilingual Co-Counsel', 'Amer Azzam Nabulsi', 250.0, 250.0),
    (6, 'Semsem', 'Laith Abdallah Almadi', 250.0, 250.0),
    (7, 'FreezeDriedJO', 'Amanhy Suhail Sahoury', 250.0, 250.0),
    (8, 'Bara\'ah altawarh for natural products manufacturing', 'Bara\'ah Salman Moh\'d Altawarah', 250.0, 250.0),
    (9, 'BRAINTECH AI', 'Mohammad Jaafar Mohammad Al-Sweiti', 0.0, 0.0),
    (10, 'Grains of Goodness', 'Ala\'a Suleiman Al-Omari', 250.0, 250.0),
    (11, 'Anbta', 'Yousef Jameel Jadallah', 250.0, 250.0),
    (12, 'Butterfly Effect', 'Bushra Ahmad Al-Jarabea', 250.0, 250.0),
    (13, 'Aqd Platform', 'Abdalrahman Maghaireh', 250.0, 250.0),
    (14, 'Feyn Ai', 'Mohammad Khaleel Alqasem', 250.0, 250.0),
    (15, 'Ay Mazadak (Your Auction)', 'Alaa Mohammad Hassan Al-Omari', 250.0, 250.0),
    (16, 'SYSTEM', 'Salam Ismail Taha Abu Al-Hayjaa', 250.0, 250.0),
    (17, 'MonoFilm', 'Anas Samer Zaitoun', 250.0, 250.0),
    (18, 'EDU-CORE', 'Khalid Sameer Bakroon', 250.0, 250.0),
    (19, 'Muqasah Smart Software Company (LLC)', 'Dr. Yaser Abdelhadi', 250.0, 250.0),
    (20, 'Internz', 'Suhayb Qasem', 250.0, 250.0),
    (21, 'JoVenture', 'Yousef Abdullah AlZiwary', 250.0, 250.0),
    (22, 'Takween', 'Suhaib Ramzi Abukhater', 250.0, 250.0),
    (23, 'Hissa', 'Nour Al-Tahhan', 250.0, 250.0),
    (24, 'GAWWAK', 'Faisal Hashem Naji', 250.0, 250.0),
    (25, 'Learnify', 'Zaid Dweiri', 250.0, 250.0),
    (26, 'zafraancom', 'Mona Mahmoud Hamdan Al-Sayah', 250.0, 250.0),
    (27, 'SARD', 'Haitham Firas Shlool', 250.0, 250.0),
    (28, 'PoultryHealth Ai', 'Malek Anas Al-Betar', 250.0, 250.0),
    (29, 'Kaleem', 'Bayan Anwar Al-Deiri', 250.0, 250.0),
    (30, 'care.ai', 'Mahmoud Ahmad Hamed Alkhwalda', 250.0, 250.0),
    (31, 'Khutwa', 'Sanad Abdelelah Dhaimesh', 250.0, 250.0),
    (32, 'SolaRosette Brand', 'Aseel Ahmad AlAzzi', 250.0, 250.0),
    (33, 'Pentra', 'Abdulaziz Refaat Al-Johari', 250.0, 250.0),
    (34, 'Eshara', 'Nour Salah Al-Farraj', 250.0, 250.0),
    (35, 'Galaxy of Pharmacy', 'Alaa Mahmoud Allaryeh', 250.0, 250.0),
    (36, 'JaymnJO', 'Sami Jalal Abbassi', 250.0, 250.0),
    (37, 'Smart Farm', 'Anwar Mohammad Al-Talafha', 250.0, 250.0),
    (38, 'PathMaker (PathAI)', 'Hala Nizam Al-Hashlamoun', 250.0, 250.0),
    (39, 'Nurse Home', 'Abeer Khaled Qishawi', 0.0, 250.0),
    (40, 'Minimed Tender', 'Feras Naser Hasan', 0.0, 250.0),
]

ALIAS_MAP = {
    'aqd platform': 'شركة البنان / منصة عقد',
    'zafraancom': 'زعفرانكم',
    'poultryhealth ai': 'sirb',
    'learnify': 'behindit',
    'gawwak': 'gawak',
    'ay mazadak (your auction)': 'emazadak',
    'pathmaker (pathai)': 'pathai',
    'braintech ai': 'braintech',
    'nurse home': 'nurse',
    'minimed tender': 'minimed',
    'muqasah smart software company (llc)': 'muqasa smart software company (llc)',
    "bara'ah altawarh for natural products manufacturing": "bara’ah al-tawara for natural materials manufacturing",
}


def norm(t: str) -> str:
    return ''.join(c.lower() for c in (t or '') if c.isalnum())


def import_cohort4_disbursements(db: Session, branch_id: int = 1):
    c4_program = db.query(Program).filter(
        Program.branch_id == branch_id,
        Program.name.like('%Cohort 4%')
    ).first()

    if not c4_program:
        raise ValueError("Cohort 4 program not found for branch")

    admin_user = db.query(User).filter(User.email.like("%admin%")).first()
    admin_id = admin_user.id if admin_user else None
    db_businesses = db.query(Business).filter(Business.program_id == c4_program.id).all()

    # Align startup names and founders to official dataset
    for b in db_businesses:
        if b.name in ['NurseHome', 'Universal Accessible Content Platform', 'Nurse Home']:
            b.name = 'Nurse Home'
            if b.founders:
                b.founders[0].first_name = 'Abeer Khaled'
                b.founders[0].last_name = 'Qishawi'
                b.founders[0].position = 'Co-Founder & Project Lead'
                b.founders[0].email = 'qishawiabeer71@gmail.com'
            if b.applicant_id:
                app = db.get(Applicant, b.applicant_id)
                if app:
                    app.business_name = 'Nurse Home'
                    app.first_name = 'Abeer Khaled'
                    app.last_name = 'Qishawi'
                    app.email = 'qishawiabeer71@gmail.com'
        elif b.name in ['MiniMed Tender', 'KPIron', 'Minimed Tender']:
            b.name = 'Minimed Tender'
            if b.founders:
                b.founders[0].first_name = 'Feras Naser'
                b.founders[0].last_name = 'Hasan'
                b.founders[0].position = 'Founder & CEO'
                b.founders[0].email = 'ferasnhayasrah@gmail.com'
            if b.applicant_id:
                app = db.get(Applicant, b.applicant_id)
                if app:
                    app.business_name = 'Minimed Tender'
                    app.first_name = 'Feras Naser'
                    app.last_name = 'Hasan'
                    app.email = 'ferasnhayasrah@gmail.com'
        elif b.name in ['BrainTech', 'BRAINTECH AI']:
            b.name = 'BRAINTECH AI'
            if b.founders:
                b.founders[0].first_name = 'Mohammad Jaafar Mohammad'
                b.founders[0].last_name = 'Al-Sweiti'
                b.founders[0].position = 'Founder & CEO'
                b.founders[0].email = 'mohammad.alsweiti@braintech.jo'
            if b.applicant_id:
                app = db.get(Applicant, b.applicant_id)
                if app:
                    app.business_name = 'BRAINTECH AI'
                    app.first_name = 'Mohammad Jaafar Mohammad'
                    app.last_name = 'Al-Sweiti'
                    app.email = 'mohammad.alsweiti@braintech.jo'
    db.commit()

    # Re-fetch businesses after alignment
    db_businesses = db.query(Business).filter(Business.program_id == c4_program.id).all()

    # Build startup mapping
    biz_by_name = {norm(b.name): b for b in db_businesses}

    mapped_by_biz_id = {}
    for idx, sname, fname, jul_amt, aug_amt in COHORT4_DATA:
        target = ALIAS_MAP.get(sname.lower(), sname.lower())
        b = biz_by_name.get(norm(sname)) or biz_by_name.get(norm(target))
        if not b:
            target_norm = norm(target)
            for bn, candidate in biz_by_name.items():
                if target_norm in bn or bn in target_norm:
                    b = candidate
                    break
        if not b:
            fn_parts = fname.split()
            for candidate in db_businesses:
                if candidate.founders and candidate.founders[0].first_name:
                    if norm(fn_parts[0]) == norm(candidate.founders[0].first_name.split()[0]):
                        b = candidate
                        break
        if not b:
            raise ValueError(f"Could not map Cohort 4 startup: {sname} ({fname})")
        mapped_by_biz_id[b.id] = (sname, fname, jul_amt, aug_amt)

    print(f"Mapped {len(mapped_by_biz_id)}/{len(COHORT4_DATA)} Cohort 4 businesses.")

    # Remove any existing batches for Cohort 4 for idempotent re-runs
    existing_batches = db.query(DisbursementBatch).filter(
        DisbursementBatch.branch_id == branch_id,
        DisbursementBatch.program_id == c4_program.id
    ).all()
    if existing_batches:
        print(f"Removing {len(existing_batches)} existing Cohort 4 batches for clean re-import.")
        for eb in existing_batches:
            db.delete(eb)
        db.commit()

    # Batch configs: (month_label, payment_date, data_idx, notes_summary, confirmed_dt)
    batches_config = [
        (
            'Cohort 4 Track I: Monthly Stipend — July 2026',
            date(2026, 7, 31),
            2,  # index for jul_amt in (sname, fname, jul_amt, aug_amt)
            'First monthly allowance for Cohort 4 (Reconciled Jul 2026). 37 received payment; 3 pending compliance/bank details.',
            datetime(2026, 7, 31, 12, 0)
        ),
        (
            'Cohort 4 Track I: Monthly Stipend — August 2026',
            date(2026, 8, 11),
            3,  # index for aug_amt
            'Second monthly allowance for Cohort 4 (Paid Aug 11, 2026). 39 received payment (including Nurse Home and Minimed Tender); 1 pending compliance/bank details (BRAINTECH AI).',
            datetime(2026, 8, 11, 12, 0)
        ),
    ]

    for title, pay_date, amt_idx, batch_notes, conf_dt in batches_config:
        batch = DisbursementBatch(
            branch_id=branch_id,
            program_id=c4_program.id,
            title=title,
            payment_date=pay_date,
            currency='EUR',
            disbursement_currency='JOD',
            exchange_rate=0.76,
            base_amount=250.0,
            notes=batch_notes,
            status='processed',
            confirmed_by_id=admin_id,
            confirmed_at=conf_dt,
        )
        db.add(batch)
        db.flush()

        batch_total = 0.0
        batch_total_jod = 0.0
        paid_count = 0
        pending_count = 0

        for b in db_businesses:
            sname, fname, jul_amt, aug_amt = mapped_by_biz_id[b.id]
            amt = jul_amt if amt_idx == 2 else aug_amt
            pct = int(amt / 250.0 * 100)
            is_inc = (amt > 0)
            note = 'Standard monthly stipend' if amt == 250.0 else 'Pending compliance / bank details'
            amt_jod = round(amt * 0.76, 3)

            db.add(DisbursementItem(
                batch_id=batch.id,
                business_id=b.id,
                percentage=pct,
                amount=amt,
                amount_jod=amt_jod,
                disbursement_date=pay_date,
                exchange_rate=0.76,
                is_included=is_inc,
                notes=note
            ))
            batch_total += amt
            batch_total_jod += amt_jod
            if amt > 0:
                paid_count += 1
            else:
                pending_count += 1

        batch.total_amount = batch_total
        batch.total_amount_jod = round(batch_total_jod, 3)
        db.commit()

        print(f"Successfully created '{batch.title}':")
        print(f"  - Payment Date: {batch.payment_date}")
        print(f"  - Batch Total: EUR {batch_total:,.2f} ({batch.total_amount_jod:,.3f} JOD)")
        print(f"  - Paid Startups: {paid_count}")
        print(f"  - Pending Compliance Startups: {pending_count}")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        import_cohort4_disbursements(db, branch_id=1)
    finally:
        db.close()
