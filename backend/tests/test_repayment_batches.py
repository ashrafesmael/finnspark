import io
from datetime import date

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app, _migrate
from app.database import get_db, engine, Base
from app.models import (
    Branch, Business, InvestmentCase, LoanRepayment, RepaymentBatch,
    DisbursementBatch, DisbursementItem, User, Role, UserRole, Program,
)

client = TestClient(app)

HEADERS_ROW = ["Cohort", "Startup", "Loan #", "Paid by", "Date of repayment",
               "Cash / Bank", "Channel", "Amount (JOD)", "Amount (EUR)",
               "Instalment / notes", "Verified against"]


def _xlsx(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADERS_ROW)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:////tmp/opencode/finnspark_batchtest.db")
    # env is read at config import; tests are run with it set on the command line
    Base.metadata.create_all(bind=engine)
    _migrate(engine)   # startup events don't fire for a module-level TestClient
    db = next(get_db())
    res = client.post("/auth/login/", json={"email": "admin@finnpact.jo", "password": "Admin123!"})
    assert res.status_code == 200, res.text
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    user = db.query(User).filter_by(email="admin@finnpact.jo").first()

    program = db.query(Program).filter_by(branch_id=1).first()
    biz = Business(name="Ledger Test Startup", branch_id=1, program_id=program.id if program else None)
    db.add(biz)
    db.flush()
    case = InvestmentCase(branch_id=1, business_id=biz.id, company_name=biz.name,
                          investment_amount=10000.0, co_financing_amount=5000.0,
                          forex_rate=0.76, currency="EUR")
    db.add(case)
    db.flush()

    # Track II loan tranche of 10,000 EUR and a Track I stipend of 1,000 EUR
    loan_batch = DisbursementBatch(branch_id=1, program_id=program.id if program else 1,
                                   title="Cohort 2 Track II: Tranche 1 (S3) — H1 Year 2",
                                   payment_date=date(2025, 7, 1), currency="EUR",
                                   disbursement_currency="JOD", exchange_rate=0.76,
                                   base_amount=10000.0, status="processed")
    db.add(loan_batch)
    db.flush()
    db.add(DisbursementItem(batch_id=loan_batch.id, business_id=biz.id, percentage=100.0,
                            amount=10000.0, amount_jod=7600.0, is_included=True))
    grant_batch = DisbursementBatch(branch_id=1, program_id=program.id if program else 1,
                                    title="Cohort 2 Track I: Monthly Stipend — July 2025",
                                    payment_date=date(2025, 7, 5), currency="EUR",
                                    disbursement_currency="JOD", exchange_rate=0.76,
                                    base_amount=1000.0, status="processed")
    db.add(grant_batch)
    db.flush()
    db.add(DisbursementItem(batch_id=grant_batch.id, business_id=biz.id, percentage=100.0,
                            amount=1000.0, amount_jod=760.0, is_included=True))
    db.commit()

    yield {"headers": headers, "db": db, "biz": biz, "case": case, "user": user}

    db.query(LoanRepayment).filter(LoanRepayment.business_id == biz.id).delete()
    db.query(RepaymentBatch).filter(RepaymentBatch.branch_id == 1,
                                    RepaymentBatch.title.like("%Ledger Test%")).delete()
    db.query(DisbursementItem).filter(DisbursementItem.business_id == biz.id).delete()
    db.query(DisbursementBatch).filter(DisbursementBatch.branch_id == 1).delete()
    db.query(InvestmentCase).filter(InvestmentCase.business_id == biz.id).delete()
    db.query(Business).filter(Business.id == biz.id).delete()
    db.commit()


class TestRepaymentBatches:

    def test_upload_creates_draft_batch_and_flags_unmatched(self, setup):
        rows = [
            ["C#2", "Ledger Test Startup", "1000001", "Bank record name", "20-Jul-2025",
             "Bank transfer", "Inward transfer", 487.75, "", "July 2025",
             "Wafaa's monthly report (bank extract), Jul 2025"],
            # EUR-only row, evidenced only by slip + Loandisk -> unverified
            ["C#2", "Ledger Test Startup", "1000001", "Someone", "04-Oct-2026",
             "Bank transfer", "EUR transfer", "", 597.02, "Months 14 & 15 paid together",
             "Hamza's slip; Loandisk"],
            # fee row is classified, not an installment
            ["C#2", "Ledger Test Startup", "1000007", "Someone", "02-Jul-2025",
             "Cash", "Cash deposit", 81.0, "", "Up-front fee (Qard Al Hasan)",
             "Wafaa's monthly report"],
            # unmatched startup must not be silently created
            ["C#2", "Ghost Startup", "1000099", "X", "21-Jul-2025",
             "Bank transfer", "Inward transfer", 100.0, "", "July 2025", "report"],
        ]
        res = client.post(
            "/api/repayments/1/batches/upload/",
            params={"title": "Repayments — Jul 2025 to Oct 2026", "source": "Register"},
            files={"file": ("batch.xlsx", _xlsx(rows),
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=setup["headers"],
        )
        assert res.status_code == 200, res.text
        data = res.json()
        batch = data["batch"]

        assert data["detail"].startswith("Batch created with 3 repayment rows")
        assert batch["status"] == "draft"
        assert batch["rows_count"] == 3
        assert [u["startup"] for u in data["unmatched"]] == ["Ghost Startup"]

        items = batch["repayments"]
        by_date = {r["payment_date"]: r for r in items}
        jod_row = by_date["2025-07-20"]
        assert jod_row["amount_jod"] == pytest.approx(487.75)
        assert jod_row["amount"] == pytest.approx(487.75 / 0.76, rel=1e-3)  # EUR derived
        assert jod_row["entry_type"] == "installment"
        assert jod_row["verified"] is True
        assert jod_row["loan_number"] == "1000001"

        eur_row = by_date["2026-10-04"]
        assert eur_row["amount"] == pytest.approx(597.02)
        assert eur_row["amount_jod"] == pytest.approx(597.02 * 0.76, rel=1e-3)
        assert eur_row["verified"] is False          # slip/Loandisk only

        fee_row = by_date["2025-07-02"]
        assert fee_row["entry_type"] == "fee"

        assert batch["total_jod"] == pytest.approx(487.75 + 81.0 + 597.02 * 0.76, rel=1e-3)

    def test_confirm_reopen_delete_lifecycle(self, setup):
        rows = [["C#2", "Ledger Test Startup", "1000001", "P", "20-Jul-2025",
                 "Bank transfer", "Inward transfer", 480.0, "", "July 2025", "report"]]
        res = client.post("/api/repayments/1/batches/upload/", files={
            "file": ("b.xlsx", _xlsx(rows), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=setup["headers"])
        batch_id = res.json()["batch"]["id"]

        # list shows the draft
        res = client.get("/api/repayments/1/batches/", headers=setup["headers"])
        assert res.status_code == 200
        assert any(b["id"] == batch_id for b in res.json()["results"])

        res = client.post(f"/api/repayments/1/batches/{batch_id}/confirm/", headers=setup["headers"])
        assert res.status_code == 200
        assert res.json()["batch"]["status"] == "processed"

        # delete of a processed batch is refused
        res = client.delete(f"/api/repayments/1/batches/{batch_id}/", headers=setup["headers"])
        assert res.status_code == 400

        res = client.post(f"/api/repayments/1/batches/{batch_id}/reopen/", headers=setup["headers"])
        assert res.status_code == 200
        assert res.json()["batch"]["status"] == "draft"

        res = client.delete(f"/api/repayments/1/batches/{batch_id}/", headers=setup["headers"])
        assert res.status_code == 200
        res = client.get(f"/api/repayments/1/batches/{batch_id}/", headers=setup["headers"])
        assert res.status_code == 404

    def test_ledger_merges_disbursements_and_repayments_with_running_balance(self, setup):
        rows = [
            ["C#2", "Ledger Test Startup", "1000001", "P", "20-Jul-2025",
             "Bank transfer", "Inward transfer", 760.0, "", "July 2025", "report"],      # 1000 EUR
            ["C#2", "Ledger Test Startup", "1000001", "P", "20-Aug-2025",
             "Bank transfer", "Inward transfer", 380.0, "", "August 2025", "report"],    # 500 EUR
        ]
        client.post("/api/repayments/1/batches/upload/", files={
            "file": ("b.xlsx", _xlsx(rows), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=setup["headers"])
        # confirm so rows are locked, ledger must still count them
        bid = client.get("/api/repayments/1/batches/", headers=setup["headers"]).json()["results"][0]["id"]
        client.post(f"/api/repayments/1/batches/{bid}/confirm/", headers=setup["headers"])

        res = client.get(f"/api/repayments/1/startup/{setup['biz'].id}/ledger/", headers=setup["headers"])
        assert res.status_code == 200, res.text
        data = res.json()

        # 10,000 loan + 1,000 grant disbursed; grants never enter the balance
        assert data["disbursed_loan_eur"] == pytest.approx(10000.0)
        assert data["disbursed_grant_eur"] == pytest.approx(1000.0)
        assert data["total_repaid_eur"] == pytest.approx(1500.0)
        assert data["outstanding_eur"] == pytest.approx(8500.0)     # 10000 - 1500
        assert data["outstanding_vs_approved_eur"] == pytest.approx(8500.0)

        lines = data["lines"]
        assert [l["source"] for l in lines] == ["disbursement", "disbursement", "repayment", "repayment"]
        assert lines[0]["kind"] == "loan" and lines[0]["track"] == "II"
        assert lines[1]["kind"] == "grant" and lines[1]["track"] == "I"

        monthly = {m["month"]: m for m in data["monthly"]}
        assert monthly["2025-07"]["closing_outstanding_eur"] == pytest.approx(9000.0)
        assert monthly["2025-08"]["closing_outstanding_eur"] == pytest.approx(8500.0)
        assert monthly["2025-07"]["grant_in_eur"] == pytest.approx(1000.0)
        assert monthly["2025-08"]["repaid_eur"] == pytest.approx(500.0)

    def test_refinanced_row_counts_toward_balance_fee_does_not(self, setup):
        rows = [
            ["C#2", "Ledger Test Startup", "1000008", "P", "28-Jun-2026",
             "Non-cash (refinanced)", "Balance rolled into new loan", 760.0, "",
             "Refinanced - no cash received", "Loandisk; email"],
            ["C#2", "Ledger Test Startup", "1000013", "P", "14-Jul-2026",
             "Bank transfer", "Inward transfer", 325.72, "", "One-off processing fee", "report"],
        ]
        res = client.post("/api/repayments/1/batches/upload/", files={
            "file": ("b.xlsx", _xlsx(rows), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=setup["headers"])
        bid = res.json()["batch"]["id"]

        # a draft batch is visible but holds no money — mirroring disbursements
        res = client.get(f"/api/repayments/1/startup/{setup['biz'].id}/ledger/", headers=setup["headers"])
        assert res.json()["total_repaid_eur"] == pytest.approx(0.0)
        assert res.json()["outstanding_eur"] == pytest.approx(10000.0)

        client.post(f"/api/repayments/1/batches/{bid}/confirm/", headers=setup["headers"])
        res = client.get(f"/api/repayments/1/startup/{setup['biz'].id}/ledger/", headers=setup["headers"])
        data = res.json()
        # refinanced counts as settling 1000 EUR; the fee does not
        assert data["total_repaid_eur"] == pytest.approx(1000.0)
        assert data["outstanding_eur"] == pytest.approx(9000.0)
        kinds = {l["kind"] for l in data["lines"] if l["source"] == "repayment"}
        assert kinds == {"refinanced", "fee"}
