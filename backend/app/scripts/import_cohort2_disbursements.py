"""Script to import and reconcile the official Cohort 2 Track I Disbursements.

Dataset source: OCIF Jordan Payment Reconciliation (Feb 2025).
Contains:
- 6 Monthly Allowance Batches (Sep 2024 - Feb 2025) @ EUR 250 base (Sub-total: EUR 53,500.00)
- 2 Prototype Voucher Batches (Nov 2024, Dec 2024) @ EUR 1,000 base (Sub-total: EUR 36,000.00)
- Total Disbursed: EUR 89,500.00 across 40 startups
"""
import sys
import os
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Program, Business, DisbursementBatch, DisbursementItem, User

COHORT2_RECONCILED = [
    (1, 'AiGO', 'Oduai Mohammad Aburub', [0, 0, 0, 0, 0, 0], [0, 0]),
    (2, 'Aisel Organic', 'Ala Omar Abu Al-Saud', [250, 250, 0, 500, 250, 250], [0, 1000]),
    (3, 'Anti-Gravity Skin', 'Lamees Mohammad Fathi Aalbudi', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (4, 'Arabon', 'Basil Mohammed Ibrahim', [250, 250, 0, 500, 250, 250], [0, 1000]),
    (5, 'Avancer', 'Abdelrazzaq Majid Mohammed Al-Hadidi', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (6, 'BioHive', 'Suhaib Ziyad Kamal', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (7, 'Campaigner', 'Awn Khaled Nuwwar', [0, 0, 0, 0, 0, 0], [0, 0]),
    (8, 'DAL', 'Diab Saddin Zaanin', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (9, 'Designer Little', 'Ahmad Ghannam Jarrar', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (10, 'Dotsession', 'Hadeel Hisham Al-Jarboa', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (11, 'Dr. NALY Natural Skin Care Products', 'Yousri Abdel Fattah Hamed', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (12, 'Eleyy', 'Shady Tariq Qaddoura', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (13, 'Elli Creators', 'Dalia Mustafa Abu Ghoush', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (14, 'Fundkom', 'Ahmad Abualfeilat', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (15, 'EmanDiets', 'Ali Hasan Ghojah', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (16, 'Jordan Verde Vita (JVV)', 'Sarah Ahmad Hudaib', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (17, 'Applykom', 'Abdulrahman Raed Albishawi', [0, 0, 0, 500, 250, 250], [0, 1000]),
    (18, 'Leasifier', 'Abdallah Mazin Qoraan', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (19, 'MASH Technology', 'Emad Munir Al-Halabi', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (20, 'Math Mania', 'Yazan Nabeel Tadros', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (21, 'Molar', 'Wissam Alhakim', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (22, 'Mudarrib', 'Tareq Mustafa Abu Muailish', [250, 250, 0, 500, 250, 250], [0, 1000]),
    (23, 'Bab Plus', 'Omar Hamza Hammad', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (24, 'OIA', 'Malak Radwan Al-Mashaqba', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (25, 'OrganicG', 'Randa Kamal Aliyan', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (26, 'Plant Patch', 'Noor Abdul Mohammad Al-Rudaini', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (27, 'R-FEED', 'Ammar Mamdouh Al-Rafou', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (28, 'Ruqaa', 'Khaled Sujood Qaoud', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (29, 'Sa3idd Freelance Platform', 'Ayman Mohammed Haroun', [0, 0, 0, 0, 0, 0], [0, 0]),
    (30, 'Sahel Platform', 'Khaled Amjad Alsaidi', [0, 0, 0, 0, 0, 0], [0, 0]),
    (31, 'Sin(Sign)', 'Sarah Essam Shaheen', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (32, 'Smart Green for Phytobase Solution', 'Ali Bassam Saqer Marayhah', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (33, 'StartSmart', 'Nada Ahmad ALMaslamani', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (34, 'Maakani', 'Faisal Jawad Rababah', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (35, 'Studio B.O.R.', 'Batoul Omar Al-Rashdan', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (36, 'Talentspace.ai', 'Mohannad Yousef Alsouqi', [250, 250, 0, 500, 250, 250], [0, 1000]),
    (37, 'Tarjim', 'Mohammed Fahmi Almuqtare', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (38, 'Vibrant Vials', 'Israa Abdallah Elshebli', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (39, 'Wondersoftheorient', 'Romouz Sadeq Mohammad', [250, 250, 250, 250, 250, 250], [1000, 0]),
    (40, 'Yalla', 'Ahmad Mohammad Sweilem', [250, 250, 250, 250, 250, 250], [1000, 0]),
]

MONTH_DATES = [
    ('Sep-24', date(2024, 9, 30), 'Monthly Stipend — September 2024'),
    ('Oct-24', date(2024, 10, 31), 'Monthly Stipend — October 2024'),
    ('Nov-24', date(2024, 11, 30), 'Monthly Stipend — November 2024'),
    ('Dec-24', date(2024, 12, 31), 'Monthly Stipend — December 2024'),
    ('Jan-25', date(2025, 1, 31), 'Monthly Stipend — January 2025'),
    ('Feb-25', date(2025, 2, 28), 'Monthly Stipend — February 2025'),
]

PROTO_MONTHS = [
    (0, 'Nov-24', date(2024, 11, 30), 'Prototype Voucher — November 2024 Batch'),
    (1, 'Dec-24', date(2024, 12, 31), 'Prototype Voucher — December 2024 Batch'),
]

ALIAS_MAP = {
    'sa3idd freelance platform': 'sa3id freelance platform',
    'emandiets': 'emandiets website',
    'dr. naly natural skin care products': 'denally dr naly',
}


def norm(t: str) -> str:
    return ''.join(c.lower() for c in (t or '') if c.isalnum())


def import_cohort2_disbursements(db: Session, branch_id: int = 1):
    c2_program = db.query(Program).filter(
        Program.branch_id == branch_id,
        Program.name.like('%Cohort 2%')
    ).first()

    if not c2_program:
        raise ValueError("Cohort 2 program not found for branch")

    admin_user = db.query(User).filter(User.email.like("%admin%")).first()
    db_businesses = db.query(Business).filter(Business.program_id == c2_program.id).all()

    # Build startup mapping
    biz_by_name = {}
    for b in db_businesses:
        biz_by_name[norm(b.name)] = b

    reconciled_by_biz_id = {}
    for idx, sname, fname, m_list, p_list in COHORT2_RECONCILED:
        target = ALIAS_MAP.get(sname.lower(), sname.lower())
        b = biz_by_name.get(norm(target))
        if not b:
            # Fallback substring
            for bn, candidate in biz_by_name.items():
                if norm(target) in bn or bn in norm(target):
                    b = candidate
                    break
        if not b:
            raise ValueError(f"Could not map startup: {sname} ({fname})")
        reconciled_by_biz_id[b.id] = (m_list, p_list, sname)

    print(f"Mapped {len(reconciled_by_biz_id)}/{len(COHORT2_RECONCILED)} Cohort 2 businesses.")

    # Remove any existing batches for Cohort 2 to allow clean idempotent re-run
    existing_batches = db.query(DisbursementBatch).filter(
        DisbursementBatch.branch_id == branch_id,
        DisbursementBatch.program_id == c2_program.id
    ).all()
    if existing_batches:
        print(f"Removing {len(existing_batches)} existing Cohort 2 batches for clean re-import.")
        for eb in existing_batches:
            db.delete(eb)
        db.commit()

    created_batches = 0
    total_cohort2_disbursed = 0.0

    # 1. Create 6 Monthly Allowance Batches
    for m_idx, (m_label, m_date, m_title) in enumerate(MONTH_DATES):
        batch = DisbursementBatch(
            branch_id=branch_id,
            program_id=c2_program.id,
            title=f'Cohort 2 Track I: {m_title}',
            payment_date=m_date,
            currency='EUR',
            disbursement_currency='JOD',
            exchange_rate=0.76,
            base_amount=250.0,
            notes=f'Official monthly allowance payment for {m_label} (Reconciled Feb 2025).',
            status='processed',
            confirmed_by_id=admin_user.id if admin_user else None,
            confirmed_at=datetime(m_date.year, m_date.month, m_date.day, 12, 0),
        )
        db.add(batch)
        db.flush()

        b_total = 0.0
        b_total_jod = 0.0
        paid_recipients = 0
        for b in db_businesses:
            m_list, _, sname = reconciled_by_biz_id[b.id]
            amt = float(m_list[m_idx])
            pct = int(amt / 250.0 * 100)
            note = (
                'Includes catch-up payment for missed month' if amt == 500 else
                'Standard monthly stipend' if amt == 250 else
                'Attendance / milestone requirement not met (or inactive)'
            )
            is_inc = (amt > 0)
            amt_jod = round(amt * 0.76, 3)
            db.add(DisbursementItem(
                batch_id=batch.id,
                business_id=b.id,
                percentage=pct,
                amount=amt,
                amount_jod=amt_jod,
                disbursement_date=m_date,
                exchange_rate=0.76,
                is_included=is_inc,
                notes=note
            ))
            b_total += amt
            b_total_jod += amt_jod
            if amt > 0:
                paid_recipients += 1

        batch.total_amount = b_total
        batch.total_amount_jod = round(b_total_jod, 3)
        db.commit()
        created_batches += 1
        total_cohort2_disbursed += b_total
        print(f"Created Monthly Batch: '{batch.title}' -> Total: EUR {b_total:,.2f} ({paid_recipients} paid)")

    # 2. Create 2 Prototype Voucher Batches
    for p_idx, p_label, p_date, p_title in PROTO_MONTHS:
        batch = DisbursementBatch(
            branch_id=branch_id,
            program_id=c2_program.id,
            title=f'Cohort 2 Track I: {p_title}',
            payment_date=p_date,
            currency='EUR',
            disbursement_currency='JOD',
            exchange_rate=0.76,
            base_amount=1000.0,
            notes=f'One-off prototype voucher milestone disbursement for {p_label} (Reconciled Feb 2025).',
            status='processed',
            confirmed_by_id=admin_user.id if admin_user else None,
            confirmed_at=datetime(p_date.year, p_date.month, p_date.day, 12, 0),
        )
        db.add(batch)
        db.flush()

        p_total = 0.0
        p_total_jod = 0.0
        paid_recipients = 0
        for b in db_businesses:
            _, p_list, sname = reconciled_by_biz_id[b.id]
            amt = float(p_list[p_idx])
            pct = 100 if amt == 1000 else 0
            note = (
                'Prototype milestone voucher approved' if amt == 1000 else
                'Prototype milestone pending or not eligible'
            )
            is_inc = (amt > 0)
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
            p_total += amt
            p_total_jod += amt_jod
            if amt > 0:
                paid_recipients += 1

        batch.total_amount = p_total
        batch.total_amount_jod = round(p_total_jod, 3)
        db.commit()
        created_batches += 1
        total_cohort2_disbursed += p_total
        print(f"Created Prototype Batch: '{batch.title}' -> Total: EUR {p_total:,.2f} ({paid_recipients} paid)")

    print(f"\nSuccessfully imported Cohort 2 disbursements:")
    print(f"  - Batches created: {created_batches}")
    print(f"  - Total disbursed: EUR {total_cohort2_disbursed:,.2f}")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        import_cohort2_disbursements(db, branch_id=1)
    finally:
        db.close()
