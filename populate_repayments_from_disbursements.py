import sys
import os
import re
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import (
    Branch, Business, BusinessFounder, InvestmentCase, LoanRepayment,
    FinanceTimelineEntry, User, DisbursementBatch, DisbursementItem
)

RAW_DATA = """
10/08/2026 Ms. Saud Battikeh 1000014 Wafaa Sakriyeh Online Transfer 31,778.00
21/07/2026 Mr. Saqr Bassam Ali Marayha 1000007 Wafaa Sakriyeh Cash 48,000.00
22/07/2026 Mr. Mohammad Issam Hussein Yaseen 1000006 Wafaa Sakriyeh Online Transfer 48,435.00
23/07/2026 Mrs. Randa Kamal Rezqi Elayyan 1000009 Wafaa Sakriyeh Cash 57,000.00
27/07/2026 Mr. Mohammad Majed Abdelrazzaq Alhadidi 1000003 Wafaa Sakriyeh Online Transfer 48,775.00
04/08/2026 Mr. Yazan Nabeel Ayed Tadros 1000001 Wafaa Sakriyeh Online Transfer 48,800.00
21/07/2026 Mr. Moayad Mahmoud Abed Al-Najdawi 1000011 Wafaa Sakriyeh Online Transfer 44,240.00
26/07/2026 Miss Aseel Ihssan Mahmoud Yaseen 1000012 Wafaa Sakriyeh Online Transfer 47,600.00
28/07/2026 Ms. Shorouq AlMazraawi 1000015 Wafaa Sakriyeh Online Transfer 31,600.00
01/07/2026 Mr. Mohammad Majed Abdelrazzaq Alhadidi 1000003 Wafaa Sakriyeh Online Transfer 48,775.00
01/07/2026 Mr. Yazan Nabeel Ayed Tadros 1000001 Wafaa Sakriyeh Online Transfer 48,800.00
18/06/2026 Mr. Mohammad Issam Hussein Yaseen 1000006 Wafaa Sakriyeh Online Transfer 48,435.00
23/06/2026 Mr. Saqr Bassam Ali Marayha 1000007 Wafaa Sakriyeh Cash 48,000.00
28/06/2026 Mrs. Randa Kamal Rezqi Elayyan 1000008 finnpact Administrator Online Transfer 5,353.89
28/06/2026 Mrs. Randa Kamal Rezqi Elayyan 1000008 Wafaa Sakriyeh Cash 49,000.00
13/05/2026 Mr. Mohammad Issam Hussein Yaseen 1000006 Wafaa Sakriyeh Online Transfer 48,435.00
21/05/2026 Mr. Mohammad Majed Abdelrazzaq Alhadidi 1000003 Wafaa Sakriyeh Online Transfer 48,775.00
21/05/2026 Mr. Saqr Bassam Ali Marayha 1000007 Wafaa Sakriyeh Cash 48,000.00
02/06/2026 Mrs. Randa Kamal Rezqi Elayyan 1000008 Wafaa Sakriyeh Cash 48,900.00
04/06/2026 Mr. Yazan Nabeel Ayed Tadros 1000001 Wafaa Sakriyeh Online Transfer 48,800.00
15/04/2026 Mr. Mohammad Issam Hussein Yaseen 1000006 Wafaa Sakriyeh Online Transfer 48,435.00
19/04/2026 Mr. Saqr Bassam Ali Marayha 1000007 Wafaa Sakriyeh Cash 48,000.00
27/04/2026 Mr. Yazan Nabeel Ayed Tadros 1000001 Wafaa Sakriyeh Online Transfer 48,800.00
28/04/2026 Mr. Mohammad Majed Abdelrazzaq Alhadidi 1000003 Wafaa Sakriyeh Online Transfer 48,775.00
26/04/2026 Mrs. Randa Kamal Rezqi Elayyan 1000008 Wafaa Sakriyeh Cash 48,900.00
17/03/2026 Mr. Mohammad Issam Hussein Yaseen 1000006 Wafaa Sakriyeh Online Transfer 48,435.00
19/03/2026 Mrs. Randa Kamal Rezqi Elayyan 1000008 Wafaa Sakriyeh Cash 48,900.00
24/03/2026 Mr. Yazan Nabeel Ayed Tadros 1000001 Wafaa Sakriyeh Online Transfer 48,800.00
26/03/2026 Mr. Saqr Bassam Ali Marayha 1000007 Wafaa Sakriyeh Cash 48,000.00
26/03/2026 Mrs. Yousra AI Hamed 1000005 Wafaa Sakriyeh Cash 32,230.00
26/03/2026 Mr. Mohammad Majed Abdelrazzaq Alhadidi 1000003 Wafaa Sakriyeh Online Transfer 48,775.00
03/03/2026 Mr. Yazan Nabeel Ayed Tadros 1000001 Wafaa Sakriyeh Cash 48,900.00
02/03/2026 Mrs. Yousra AI Hamed 1000005 Wafaa Sakriyeh Cash 32,230.00
01/03/2026 Mr. Saqr Bassam Ali Marayha 1000007 Wafaa Sakriyeh Cash 48,000.00
15/02/2026 Mr. Mohammad Issam Hussein Yaseen 1000006 Wafaa Sakriyeh Online Transfer 48,435.00
22/02/2026 Mrs. Randa Kamal Rezqi Elayyan 1000008 Wafaa Sakriyeh Cash 48,900.00
23/02/2026 Mr. Mohammad Majed Abdelrazzaq Alhadidi 1000003 Wafaa Sakriyeh Online Transfer 48,775.00
31/01/2026 Mr. Yazan Nabeel Ayed Tadros 1000001 Wafaa Sakriyeh Online Transfer 48,900.00
15/01/2026 Mr. Mohammad Issam Hussein Yaseen 1000006 Wafaa Sakriyeh Online Transfer 48,435.00
26/01/2026 Mrs. Yousra AI Hamed 1000005 Wafaa Sakriyeh Cash 32,230.00
27/01/2026 Mr. Saqr Bassam Ali Marayha 1000007 Wafaa Sakriyeh Cash 48,000.00
28/01/2026 Mrs. Randa Kamal Rezqi Elayyan 1000008 Wafaa Sakriyeh Cash 48,900.00
01/02/2026 Mr. Mohammad Majed Abdelrazzaq Alhadidi 1000003 Wafaa Sakriyeh Online Transfer 48,775.00
16/12/2025 Mr. Saqr Bassam Ali Marayha 1000007 Wafaa Sakriyeh Cash 48,000.00
16/12/2025 Mr. Mohammad Issam Hussein Yaseen 1000006 Wafaa Sakriyeh Online Transfer 48,435.00
18/12/2025 Mr. Yazan Nabeel Ayed Tadros 1000001 Wafaa Sakriyeh Online Transfer 48,800.00
22/12/2025 Mrs. Yousra AI Hamed 1000005 Wafaa Sakriyeh Cash 32,230.00
23/12/2025 Mrs. Randa Kamal Rezqi Elayyan 1000008 Wafaa Sakriyeh Cash 48,900.00
24/12/2025 Mr. Mohammad Majed Abdelrazzaq Alhadidi 1000003 Wafaa Sakriyeh Online Transfer 48,775.00
03/12/2025 Mrs. Yousra AI Hamed 1000005 Wafaa Sakriyeh Cash 32,230.00
17/11/2025 Mr. Saqr Bassam Ali Marayha 1000007 Wafaa Sakriyeh Cash 48,000.00
18/11/2025 Mr. Mohammad Issam Hussein Yaseen 1000006 Wafaa Sakriyeh Online Transfer 48,435.00
24/11/2025 Mr. Mohammad Majed Abdelrazzaq Alhadidi 1000003 Wafaa Sakriyeh Online Transfer 48,775.00
24/11/2025 Mr. Yazan Nabeel Ayed Tadros 1000001 Wafaa Sakriyeh Online Transfer 48,800.00
30/11/2025 Mrs. Randa Kamal Rezqi Elayyan 1000008 Wafaa Sakriyeh Cash 48,900.00
28/10/2025 Mr. Saqr Bassam Ali Marayha 1000007 Wafaa Sakriyeh Online Transfer 48,000.00
16/10/2025 Mr. Mohammad Issam Hussein Yaseen 1000006 Wafaa Sakriyeh Online Transfer 48,435.00
20/10/2025 Mrs. Yousra AI Hamed 1000005 Wafaa Sakriyeh Cash 32,230.00
22/10/2025 Mrs. Randa Kamal Rezqi Elayyan 1000008 Wafaa Sakriyeh Cash 48,900.00
23/10/2025 Mr. Mohammad Majed Abdelrazzaq Alhadidi 1000003 Wafaa Sakriyeh Online Transfer 48,775.00
21/10/2025 Mr. Yazan Nabeel Ayed Tadros 1000001 Wafaa Sakriyeh Online Transfer 48,800.00
23/09/2025 Mr. Yazan Nabeel Ayed Tadros 1000001 Wafaa Sakriyeh Online Transfer 48,800.00
15/09/2025 Mr. Mohammad Issam Hussein Yaseen 1000006 Wafaa Sakriyeh Online Transfer 48,435.00
22/09/2025 Mr. Saqr Bassam Ali Marayha 1000007 Wafaa Sakriyeh Cash 48,000.00
23/09/2025 Mr. Mohammad Majed Abdelrazzaq Alhadidi 1000003 Wafaa Sakriyeh Online Transfer 48,775.00
23/09/2025 Mrs. Randa Kamal Rezqi Elayyan 1000008 Wafaa Sakriyeh Cash 48,900.00
24/09/2025 Mrs. Yousra AI Hamed 1000005 Wafaa Sakriyeh Cash 32,230.00
19/08/2025 Mrs. Yousra AI Hamed 1000005 Wafaa Sakriyeh Online Transfer 32,230.00
24/08/2025 Mrs. Randa Kamal Rezqi Elayyan 1000008 Wafaa Sakriyeh Online Transfer 48,925.00
13/08/2025 Mr. Yazan Nabeel Ayed Tadros 1000001 Natasha Dokhgan Online Transfer 48,800.00
18/08/2025 Mr. Saqr Bassam Ali Marayha 1000007 Natasha Dokhgan Online Transfer 48,000.00
14/08/2025 Mr. Mohammad Issam Hussein Yaseen 1000006 Natasha Dokhgan Online Transfer 48,435.00
18/08/2025 Mr. Mohammad Majed Abdelrazzaq Alhadidi 1000003 Wafaa Sakriyeh Online Transfer 48,775.00
21/07/2025 Mrs. Yousra AI Hamed 1000005 Wafaa Sakriyeh Cash 32,230.00
24/07/2025 Mr. Saqr Bassam Ali Marayha 1000007 Wafaa Sakriyeh Cash 48,000.00
27/07/2025 Mrs. Randa Kamal Rezqi Elayyan 1000008 Wafaa Sakriyeh Cash 48,925.00
15/07/2025 Mr. Yazan Nabeel Ayed Tadros 1000001 Wafaa Sakriyeh Online Transfer 48,724.00
16/07/2025 Mr. Mohammad Issam Hussein Yaseen 1000006 Wafaa Sakriyeh Online Transfer 48,435.00
20/07/2025 Mr. Mohammad Majed Abdelrazzaq Alhadidi 1000003 Wafaa Sakriyeh Online Transfer 48,775.00
24/06/2025 Mr. Mohammad Issam Hussein Yaseen 1000006 Natasha Dokhgan Online Transfer 8,150.00
02/07/2025 Mr. Saqr Bassam Ali Marayha 1000007 Natasha Dokhgan Online Transfer 8,100.00
"""

# Map to the official 14 Track II startups from disbursements module
LOAN_MAPPING = {
    "1000001": {"biz_name": "Math Mania", "case_id": 5},
    "1000003": {"biz_name": "Avancer", "case_id": 4},
    "1000005": {"biz_name": "Denally (Dr. NALY)", "case_id": 6},
    "1000006": {"biz_name": "iCash", "case_id": 3},
    "1000007": {"biz_name": "Smart Green for Phytobase Solution", "case_id": 2},
    "1000008": {"biz_name": "OrganicG", "case_id": 1},
    "1000009": {"biz_name": "OrganicG", "case_id": 1},
    "1000011": {"biz_name": "BarqBoxes", "case_id": 13},
    "1000012": {"biz_name": "THE ACT CAST", "case_id": 10},
    "1000014": {"biz_name": "بنات العيله للحياكه", "case_id": 12},
    "1000015": {"biz_name": "House of Shorouq", "case_id": 11},
}


def repopulate_repayments():
    db: Session = SessionLocal()

    # 1. Reset all existing repayments and repayment timeline entries
    db.query(LoanRepayment).delete()
    db.query(FinanceTimelineEntry).filter(
        FinanceTimelineEntry.label.ilike("%Loan Repayment%")
    ).delete(synchronize_session=False)
    db.commit()

    admin_user = db.query(User).filter(User.email.like("%admin%")).first()
    admin_id = admin_user.id if admin_user else 1

    # Load business map
    biz_map = {}
    for loan_no, info in LOAN_MAPPING.items():
        biz = db.query(Business).filter(Business.name == info["biz_name"]).first()
        if not biz:
            biz = db.query(Business).filter(Business.name.ilike(f"%{info['biz_name']}%")).first()
        case = db.query(InvestmentCase).filter(InvestmentCase.business_id == biz.id).first() if biz else None
        biz_map[loan_no] = (biz, case)

    lines = [l.strip() for l in RAW_DATA.strip().split("\n") if l.strip()]
    print(f"Repopulating repayments for {len(lines)} official transactions...")

    total_jod = 0.0
    total_eur = 0.0
    imported_count = 0

    for idx, l in enumerate(lines, 1):
        m = re.match(r"^(\d{2}/\d{2}/\d{4})\s+(.+?)\s+(1000\d{3})\s+(Wafaa Sakriyeh|Natasha Dokhgan|finnpact Administrator)\s+(Online Transfer|Cash)\s+([\d,]+\.\d{2})$", l)
        if not m:
            continue

        dt_str, name, loan_no, collector, method, amt_str = m.groups()
        if loan_no not in biz_map:
            continue

        raw_val = float(amt_str.replace(",", ""))

        # The core banking statement logs amounts in fils (where 1 JOD = 1,000 fils),
        # so 48,000.00 is 480.000 JOD; 48,435.00 is 484.350 JOD; 8,150.00 is 81.500 JOD; 5,353.89 is 53.539 JOD.
        amt_jod = round(raw_val / 100.0, 3)

        # Exchange rate EUR to JOD is 0.7600
        rate = 0.7600
        amt_eur = round(amt_jod / rate, 2)

        pay_date = datetime.strptime(dt_str, "%d/%m/%Y").date()
        biz, case = biz_map[loan_no]

        ref_no = f"LN-{loan_no}-TX{idx:03d}"
        notes = f"Loan #{loan_no} | Collected by {collector} ({method}) | Borrower: {name}"

        repay = LoanRepayment(
            branch_id=1,
            business_id=biz.id if biz else None,
            case_id=case.id if case else None,
            payment_date=pay_date,
            amount=amt_eur,
            currency="EUR",
            disbursement_currency="JOD",
            exchange_rate=rate,
            amount_jod=amt_jod,
            principal_amount=amt_eur,
            interest_amount=0.0,
            payment_method=method,
            reference_number=ref_no,
            status="completed",
            notes=notes,
            recorded_by_id=admin_id,
            created_at=datetime.utcnow(),
        )
        db.add(repay)

        if case:
            db.add(FinanceTimelineEntry(
                case_id=case.id,
                entry_date=pay_date,
                label=f"Loan Repayment: {biz.name} ({method})",
                amount=amt_eur,
                direction="in",
            ))

        imported_count += 1
        total_jod += amt_jod
        total_eur += amt_eur

    db.commit()

    print(f"\nSUCCESS: Populated {imported_count} loan repayments!")
    print(f"Total Repaid (JOD): {total_jod:,.3f} JOD")
    print(f"Total Repaid (EUR): €{total_eur:,.2f}")


if __name__ == "__main__":
    repopulate_repayments()
