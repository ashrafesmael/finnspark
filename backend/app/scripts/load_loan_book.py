"""Load the OCIF Track II loan book (Loandisk extract) into the system.

Source: 'OCIF Track II Loan Book-17-Oct-2026.xlsx' with three sheets:
  (a) Loans               - loan terms from Loandisk (authoritative)
  (b) Repayment Schedules - full per-loan instalment schedules
  (c) Repayments          - the payment register (same 120 rows as the PDF)

What this does, per loan:
  * maps the startup to its Business (creating Eduhax, which exists nowhere)
  * sets the case's approved EUR (already correct for the ten loaded startups)
    and the case FX rate from the loan itself: principal disbursed (loan ccy)
    over approved EUR -- the register's EUR instalments of the EUR loan confirm
    this rate (~0.816 for the Jun 2025 cohort), not the platform's 0.76 default
  * loads the repayment schedule into payment_schedule_entries, per loan and
    in the loan's own currency, with paid flags from Loandisk's status
  * re-derives the EUR side of already-imported repayments at the case rate
    (JOD source amounts are untouched)

Run:  python3 app/scripts/load_loan_book.py [workbook.xlsx] [--apply]
Dry run by default.
"""

import os
import sys
from datetime import date, datetime

import openpyxl

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Business, InvestmentCase, LoanRepayment, PaymentScheduleEntry,
    DisbursementBatch, DisbursementItem, Program,
)

DEFAULT_WB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "..", "OCIF Track II Loan Book-17-Oct-2026.xlsx")

# register startup name -> business name in the system. 'Saqer (PhytoBase)'
# trades as Smart Green for Phytobase Solution and 'House of Dolls' is registered
# in Arabic; both confirmed via the founder names in the loan book
BUSINESS_MAP = {
    "Saqer (PhytoBase)": "Smart Green for Phytobase Solution",
    "House of Dolls": "بنات العيله للحياكه",
}
EDUHAX = {"name": "Eduhax", "cohort": "C#2", "program_hint": "Cohort 2"}
CLOSED_STATUS_WORDS = ("fully", "paid", "restructur", "closed", "written")


def _norm(s):
    import re
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _find_business(db, target):
    biz = db.query(Business).filter(Business.name == target).first()
    if biz:
        return biz
    t = _norm(target)
    for b in db.query(Business).all():
        n = _norm(b.name)
        if n and (n == t or n.startswith(t) or t.startswith(n)):
            return b
    return None


def as_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return None


def num(v, default=0.0):
    if v is None or v == "":
        return default
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return default


def read_workbook(path):
    wb = openpyxl.load_workbook(path, data_only=True)

    loans = []
    ws = wb["(a) Loans"]
    rows = list(ws.iter_rows(values_only=True))
    hdr_i = next(i for i, r in enumerate(rows) if r[0] == "Loan ref")
    hdr = [str(c) if c else "" for c in rows[hdr_i]]
    for r in rows[hdr_i + 1:]:
        if not r[0] or "total" in str(r[0]).lower():
            continue
        if not str(r[1] or "").strip().startswith("C#"):   # skip trailing notes
            continue
        loans.append({hdr[i].strip(): r[i] for i in range(len(hdr)) if hdr[i].strip()})

    schedules = []
    ws = wb["(b) Repayment Schedules"]
    rows = list(ws.iter_rows(values_only=True))
    hdr_i = next(i for i, r in enumerate(rows) if r[0] == "Loan ref")
    hdr = [str(c) if c else "" for c in rows[hdr_i]]
    for r in rows[hdr_i + 1:]:
        if not r[0] or "total" in str(r[0]).lower():
            continue
        schedules.append({hdr[i].strip(): r[i] for i in range(len(hdr)) if hdr[i].strip()})

    repayments = []
    ws = wb["(c) Repayments"]
    rows = list(ws.iter_rows(values_only=True))
    hdr_i = next(i for i, r in enumerate(rows) if r[0] == "Loan ref")
    hdr = [str(c) if c else "" for c in rows[hdr_i]]
    for r in rows[hdr_i + 1:]:
        if not r[0] or "total" in str(r[0]).lower() or "grand" in str(r[0]).lower() \
                or "of which" in str(r[0]).lower():
            continue
        repayments.append({hdr[i].strip(): r[i] for i in range(len(hdr)) if hdr[i].strip()})

    return loans, schedules, repayments


def main():
    wb_path = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else DEFAULT_WB
    apply = "--apply" in sys.argv
    loans, schedules, repayments = read_workbook(wb_path)
    print(f"loan book: {len(loans)} loans, {len(schedules)} schedule rows, {len(repayments)} repayment rows")
    print("mode:", "APPLY" if apply else "DRY RUN")
    print()

    db = SessionLocal()
    report, warnings = [], []

    # ---------------------------------------------------------------- businesses
    biz_by_ref = {}
    for loan in loans:
        ref = str(loan["Loan ref"]).strip()
        startup = str(loan["Startup"]).strip()
        if ref in biz_by_ref:
            continue
        target = BUSINESS_MAP.get(startup, startup)
        biz = _find_business(db, target)
        would_create = biz is None and ref.startswith("Eduhax")
        if would_create:
            prog = db.query(Program).filter(Program.name.ilike(f"%{EDUHAX['program_hint']}%")).first()
            if apply:
                biz = Business(name=target, branch_id=1, program_id=prog.id if prog else None)
                db.add(biz)
                db.flush()
                warnings.append(f"created business 'Eduhax' (branch 1, programme "
                                f"{prog.name if prog else '?'})")
            else:
                warnings.append("would create business 'Eduhax'")
        if biz is None and not would_create:
            warnings.append(f"NO BUSINESS for loan ref '{ref}' (startup '{startup}')")
            continue
        if biz is None:
            continue
        biz_by_ref[ref] = biz

    # ---------------------------------------------------------------- cases
    case_by_biz = {}
    for loan in loans:
        biz = biz_by_ref.get(str(loan["Loan ref"]).strip())
        if biz is None:
            continue
        if biz.id not in case_by_biz:
            case = db.query(InvestmentCase).filter(
                InvestmentCase.business_id == biz.id).first()
            if case is None:
                warnings.append(f"NO INVESTMENT CASE for {biz.name} — loan book values not applied")
            case_by_biz[biz.id] = case

    approved_by_biz = {}
    disbursed_by_biz = {}
    rate_by_biz = {}
    for loan in loans:
        biz = biz_by_ref.get(str(loan["Loan ref"]).strip())
        if biz is None:
            continue
        approved_eur = num(loan.get("Approved loan (EUR)"))
        disbursed = num(loan.get("Principal disbursed"))
        ccy = str(loan.get("Ccy") or "").strip().upper()
        approved_by_biz[biz.id] = approved_by_biz.get(biz.id, 0.0) + approved_eur
        if ccy == "JOD" and approved_eur > 0 and loan.get("Approved loan (EUR)") is not None:
            # the restructured loan's 'disbursed' is a rollover, not new money:
            # it carries no approved EUR of its own, so it must not drag the rate
            rate_by_biz.setdefault(biz.id, disbursed / approved_eur)
        elif ccy == "EUR":
            rate_by_biz.setdefault(biz.id, None)   # EUR loan: cohort rate below

    # create cases for businesses the loan book covers but the system does not
    for ref, biz in biz_by_ref.items():
        if biz.id in case_by_biz and case_by_biz[biz.id] is not None:
            continue
        approved = round(approved_by_biz.get(biz.id, 0.0), 2)
        if approved <= 0:
            continue
        loan = next(l for l in loans if biz_by_ref.get(str(l["Loan ref"]).strip()).id == biz.id)
        cofin = 9000.0 if ref.startswith("Eduhax") else 0.0
        if cofin:
            warnings.append("Eduhax co-financing set to EUR 9,000 by cohort pattern "
                            "(every C#2 EUR-13,500 loan carries EUR 9,000) - not from the loan book, please confirm")
        else:
            warnings.append(f"created case for {biz.name} with co-financing 0 - grant amount not in the loan book")
        if apply:
            case = InvestmentCase(
                branch_id=biz.branch_id, business_id=biz.id, company_name=biz.name,
                investment_amount=approved, co_financing_amount=cofin,
                forex_rate=round(rate_by_biz.get(biz.id) or 0.816, 4),
                disbursement_amount=num(loan.get("Approved loan (EUR)")),
                disbursement_amount_jod=num(loan.get("Principal disbursed")),
                currency="EUR",
                ceo_name=str(loan.get("Borrower (Loandisk)") or "").strip(),
                collateral_description=f"Track II loan {loan.get('Loan #')} ({loan.get('Product')}), "
                                       f"released {as_date(loan.get('Release date'))} via {loan.get('Disbursed by')}")
            db.add(case)
            db.flush()
            case_by_biz[biz.id] = case
            warnings.append(f"created investment case for {biz.name} (approved EUR {approved})")

    for biz_id, case in case_by_biz.items():
        if case is None:
            continue
        approved = round(approved_by_biz.get(biz_id, 0.0), 2)
        old = float(case.investment_amount or 0.0)
        if abs(old - approved) > 0.01 and old > 0:
            warnings.append(f"{biz_name(db, biz_id)}: approved EUR {old} (system) vs "
                            f"{approved} (loan book) — NOT changed, review")
        rate = rate_by_biz.get(biz_id)
        if rate is None:
            # EUR-ccy loan or no JOD anchor: fall back to the June 2025 cohort rate
            rate = 0.816
        old_rate = float(case.forex_rate or 0.0)
        new_rate = round(rate, 4)
        # approved EUR per grant letters is the authoritative commitment figure;
        # deriving it from the JOD cash gives non-round numbers, inflates
        # OrganicG's 2nd loan (rolled-over balance is not new money) and counts
        # Denally's restructured loan as a fresh disbursement
        disb_eur = round(sum(
            num(l.get("Approved loan (EUR)"))
            for l in loans
            if biz_by_ref.get(str(l["Loan ref"]).strip()) and
            biz_by_ref[str(l["Loan ref"]).strip()].id == biz_id and
            l.get("Approved loan (EUR)") is not None), 2)
        # JOD total: native JOD loans plus the EUR loan converted at its own rate,
        # so cohort JOD totals cover every disbursed loan
        disb_jod = round(sum(
            num(l.get("Principal disbursed"))
            if str(l.get("Ccy") or "").upper() == "JOD"
            else round(num(l.get("Principal disbursed")) * new_rate, 3)
            for l in loans
            if biz_by_ref.get(str(l["Loan ref"]).strip()) and
            biz_by_ref[str(l["Loan ref"]).strip()].id == biz_id
            and l.get("Principal disbursed") is not None), 3)
        if apply:
            case.investment_amount = approved if old > 0 else case.investment_amount
            case.forex_rate = new_rate
            case.disbursement_amount = disb_eur
            case.disbursement_amount_jod = disb_jod
            borrower = str(next((l.get("Borrower (Loandisk)") for l in loans
                                 if biz_by_ref.get(str(l["Loan ref"]).strip()).id == biz_id), "")).strip()
            if not (case.ceo_name or "").strip() and borrower:
                case.ceo_name = borrower
        report.append(f"case {biz_name(db, biz_id):38} approved EUR {old:>9.2f} -> {approved:>9.2f}   "
                      f"fx {old_rate:.4f} -> {new_rate:.4f}")
    db.flush()

    # ---------------------------------------------------------------- Eduhax disbursement
    eduhax = biz_by_ref.get("Eduhax")
    if eduhax is not None:
        loan = next(l for l in loans if str(l["Loan ref"]).strip() == "Eduhax")
        existing = db.query(DisbursementItem).filter(
            DisbursementItem.business_id == eduhax.id).count()
        if existing == 0:
            if apply:
                prog = db.get(Program, eduhax.program_id) if eduhax.program_id else None
                batch = DisbursementBatch(
                    branch_id=eduhax.branch_id, program_id=prog.id if prog else 1,
                    title="Cohort 2 Track II: Loan Disbursement — Eduhax (Loandisk loan book import)",
                    payment_date=as_date(loan["Release date"]), currency="EUR",
                    disbursement_currency="JOD", exchange_rate=rate_by_biz[eduhax.id],
                    base_amount=num(loan["Approved loan (EUR)"]),
                    total_amount_jod=num(loan["Principal disbursed"]),
                    status="processed",
                    notes="Created from the Loandisk loan book import; no tranche batch existed for this startup.")
                db.add(batch)
                db.flush()
                db.add(DisbursementItem(
                    batch_id=batch.id, business_id=eduhax.id, percentage=100.0,
                    amount=num(loan["Approved loan (EUR)"]),
                    amount_jod=num(loan["Principal disbursed"]), is_included=True,
                    notes=f"Loan {loan['Loan #']}, disbursed {loan['Disbursed by']}, "
                          f"release {as_date(loan['Release date'])}"))
                warnings.append("created Track II disbursement batch + item for Eduhax "
                                "(it had none; every other startup already had one)")
            else:
                warnings.append("would create Track II disbursement batch + item for Eduhax")

    # ---------------------------------------------------------------- schedules
    schedule_status = {}
    for loan in loans:
        ref = str(loan["Loan ref"]).strip()
        biz = biz_by_ref.get(ref)
        if biz is None:
            continue
        case = case_by_biz.get(biz.id)
        if case is None:
            continue
        schedule_status[ref] = (case.id, str(loan.get("Loan #") or "").strip(),
                                str(loan.get("Ccy") or "").strip().upper(),
                                int(num(loan.get("Instalments paid"))),
                                str(loan.get("Loandisk status") or "").lower(),
                                "fee" in str(loan.get("Notes") or "").lower()
                                or str(loan.get("Product") or "").lower().startswith("ocif - qard"))

    inserted = replaced = 0
    for s in schedules:
        ref = str(s["Loan ref"]).strip()
        if ref not in schedule_status:
            continue
        case_id, loan_no, ccy, inst_paid, status, has_fee = schedule_status[ref]
        if apply:
            gone = db.query(PaymentScheduleEntry).filter(
                PaymentScheduleEntry.case_id == case_id,
                PaymentScheduleEntry.loan_number == loan_no).delete()
            replaced += 1 if gone else 0
        inst = int(num(s.get("Inst. #")))
        if any(w in status for w in CLOSED_STATUS_WORDS):
            paid = True                       # closed/restructured: fully settled
        elif inst == 0:
            paid = True                       # up-front fee, paid at release
        else:
            paid = inst <= inst_paid - (1 if has_fee else 0)
        if apply:
            db.add(PaymentScheduleEntry(
                case_id=case_id, loan_number=loan_no, currency=ccy,
                due_date=as_date(s.get("Due date")),
                amount=num(s.get("Total instalment")),
                principal_amount=num(s.get("Principal")),
                interest_amount=num(s.get("Interest")),
                fee_amount=num(s.get("Fees")),
                paid=paid))
            inserted += 1

    print("— cases (approved EUR, fx) —")
    for line in report:
        print("  " + line)
    print(f"— schedules: {inserted} rows to insert across {len(schedule_status)} loans"
          f" ({replaced} loans had existing rows replaced)" if apply else
          f"— schedules: would insert {len(schedules)} rows across {len(schedule_status)} loans")
    print()
    if warnings:
        print("NOTES / ACTIONS:")
        for w in warnings:
            print("  ! " + w)

    if apply:
        db.commit()
        print("\nCOMMITTED.")
    else:
        db.rollback()
        print("\ndry run — nothing written. Re-run with --apply.")
    db.close()


def biz_name(db, biz_id):
    b = db.get(Business, biz_id)
    return (b.name if b else "?")[:38]


if __name__ == "__main__":
    main()
