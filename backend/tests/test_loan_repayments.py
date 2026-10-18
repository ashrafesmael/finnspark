import pytest
from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.database import get_db, engine, Base
from app.models import (
    Branch, Business, InvestmentCase, LoanRepayment, PaymentScheduleEntry, User, Role, UserRole,
)

client = TestClient(app)


@pytest.fixture
def test_setup():
    Base.metadata.create_all(bind=engine)
    db = next(get_db())

    # Get admin token via login
    res = client.post("/auth/login/", json={"email": "admin@finnpact.jo", "password": "Admin123!"})
    if res.status_code != 200:
        pytest.fail(f"Login failed for test_setup: {res.text}")
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    user = db.query(User).filter_by(email="admin@finnpact.jo").first()

    # Business
    biz = db.query(Business).filter_by(name="Repayment Startup test").first()
    if not biz:
        biz = Business(
            name="Repayment Startup test",
            branch_id=1,
        )
        db.add(biz)
        db.commit()

    # Investment Case
    case = db.query(InvestmentCase).filter_by(business_id=biz.id).first()
    if not case:
        case = InvestmentCase(
            branch_id=1,
            business_id=biz.id,
            company_name=biz.name,
            investment_amount=20000.0,
            co_financing_amount=5000.0,
            forex_rate=0.76,
            currency="EUR",
        )
        db.add(case)
        db.commit()

        # Payment schedule entry
        sch = PaymentScheduleEntry(
            case_id=case.id,
            due_date=date(2026, 6, 1),
            amount=20000.0 * 0.76,   # full repayable in the loan currency (JOD)
            principal_amount=20000.0 * 0.76,
            loan_number="TEST-LOAN",
            currency="JOD",
            paid=False,
        )
        db.add(sch)
        db.commit()

    yield {"db": db, "headers": headers, "branch_id": 1, "biz_id": biz.id, "case_id": case.id, "user_id": user.id}


def test_01_create_loan_repayment(test_setup):
    headers = test_setup["headers"]
    branch_id = test_setup["branch_id"]
    biz_id = test_setup["biz_id"]

    payload = {
        "business_id": biz_id,
        "payment_date": "2026-06-15",
        "amount": 2500.0,
        "currency": "EUR",
        "disbursement_currency": "JOD",
        "exchange_rate": 0.76,
        "payment_method": "Bank Transfer",
        "reference_number": "TRX-TEST-001",
        "notes": "First tranche loan repayment",
        "status": "completed",
    }

    resp = client.post(f"/api/repayments/{branch_id}/", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["amount_eur"] == 2500.0
    assert data["amount_jod"] == 1900.0
    assert data["reference_number"] == "TRX-TEST-001"
    assert data["business_id"] == biz_id


def test_02_repayments_summary_kpi(test_setup):
    headers = test_setup["headers"]
    branch_id = test_setup["branch_id"]

    resp = client.get(f"/api/repayments/{branch_id}/summary/", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total_approved_eur"] >= 20000.0
    assert data["total_repaid_eur"] >= 2500.0
    assert data["total_repaid_jod"] >= 1900.0
    assert "outstanding_eur" in data
    assert "recovery_rate_pct" in data


def test_03_loans_overview(test_setup):
    headers = test_setup["headers"]
    branch_id = test_setup["branch_id"]

    resp = client.get(f"/api/repayments/{branch_id}/loans-overview/", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "results" in data
    assert data["count"] > 0
    item = next((r for r in data["results"] if r["business_id"] == test_setup["biz_id"]), None)
    assert item is not None
    assert item["loan_approved_eur"] == 20000.0
    assert item["total_repaid_eur"] == 2500.0
    assert item["outstanding_principal_eur"] == 17500.0


def test_04_list_repayments_ledger(test_setup):
    headers = test_setup["headers"]
    branch_id = test_setup["branch_id"]

    resp = client.get(f"/api/repayments/{branch_id}/?search=TRX-TEST-001", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["count"] >= 1
    assert data["results"][0]["reference_number"] == "TRX-TEST-001"


def test_05_startup_statement(test_setup):
    headers = test_setup["headers"]
    branch_id = test_setup["branch_id"]
    biz_id = test_setup["biz_id"]

    resp = client.get(f"/api/repayments/{branch_id}/startup/{biz_id}/statement/", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["business_id"] == biz_id
    assert data["loan_approved_eur"] == 20000.0
    assert data["total_repaid_eur"] == 2500.0
    assert len(data["repayments"]) >= 1


def test_06_export_excel_and_csv(test_setup):
    headers = test_setup["headers"]
    branch_id = test_setup["branch_id"]

    resp_xlsx = client.get(f"/api/repayments/{branch_id}/export/?format=excel", headers=headers)
    assert resp_xlsx.status_code == 200
    assert "application/vnd.openxmlformats-officedocument" in resp_xlsx.headers["content-type"]

    resp_csv = client.get(f"/api/repayments/{branch_id}/export/?format=csv", headers=headers)
    assert resp_csv.status_code == 200
    assert "text/csv" in resp_csv.headers["content-type"]
    assert "TRX-TEST-001" in resp_csv.text


def test_07_update_and_delete_repayment(test_setup):
    headers = test_setup["headers"]
    branch_id = test_setup["branch_id"]

    # Search repayment
    r_list = client.get(f"/api/repayments/{branch_id}/?search=TRX-TEST-001", headers=headers).json()
    repay_id = r_list["results"][0]["id"]

    # Update
    update_payload = {"amount": 3000.0, "reference_number": "TRX-TEST-UPDATED"}
    resp_up = client.put(f"/api/repayments/{branch_id}/{repay_id}/", json=update_payload, headers=headers)
    assert resp_up.status_code == 200
    assert resp_up.json()["amount_eur"] == 3000.0
    assert resp_up.json()["amount_jod"] == 2280.0

    # Delete
    resp_del = client.delete(f"/api/repayments/{branch_id}/{repay_id}/", headers=headers)
    assert resp_del.status_code == 200
    assert resp_del.json()["detail"] == "Repayment record deleted successfully."


def test_08_download_import_template(test_setup):
    headers = test_setup["headers"]
    branch_id = test_setup["branch_id"]

    resp = client.get(f"/api/repayments/{branch_id}/import-template/", headers=headers)
    assert resp.status_code == 200
    assert "application/vnd.openxmlformats-officedocument" in resp.headers["content-type"]
    assert len(resp.content) > 1000


def test_09_import_repayments_excel_and_csv(test_setup):
    import io
    from openpyxl import Workbook
    headers = test_setup["headers"]
    branch_id = test_setup["branch_id"]

    # 1. Test CSV Import
    csv_content = (
        "Startup / Business Name,Payment Date,Amount (EUR),FX Rate,Payment Method,Reference Number,Notes\n"
        "Repayment Startup test,2026-07-01,1500.00,0.76,Bank Transfer,TRX-CSV-101,First CSV tranche\n"
        "Repayment Startup test,2026-07-15,1000.00,0.76,Bank Transfer,TRX-CSV-102,Second CSV tranche\n"
    )
    files = {"file": ("repayments.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    resp_csv = client.post(f"/api/repayments/{branch_id}/import/", files=files, headers=headers)
    assert resp_csv.status_code == 200, resp_csv.text
    data_csv = resp_csv.json()
    assert data_csv["success"] is True
    assert data_csv["imported_count"] == 2
    assert data_csv["total_amount_eur"] == 2500.0
    assert data_csv["total_amount_jod"] == 1900.0

    # 2. Test Excel Import (with upsert)
    wb = Workbook()
    ws = wb.active
    ws.title = "Repayments"
    ws.append(["Startup / Business Name", "Payment Date", "Amount (EUR)", "FX Rate", "Payment Method", "Reference Number", "Notes"])
    ws.append(["Repayment Startup test", "2026-07-01", 1750.00, 0.76, "Bank Transfer", "TRX-CSV-101", "Updated via Excel"])
    ws.append(["Repayment Startup test", "2026-08-01", 3000.00, 0.76, "Cheque", "TRX-XLS-201", "New Excel tranche"])

    excel_buf = io.BytesIO()
    wb.save(excel_buf)
    excel_buf.seek(0)

    files_excel = {"file": ("repayments.xlsx", excel_buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    resp_excel = client.post(f"/api/repayments/{branch_id}/import/", files=files_excel, headers=headers)
    assert resp_excel.status_code == 200, resp_excel.text
    data_excel = resp_excel.json()
    assert data_excel["success"] is True
    assert data_excel["updated_count"] == 1  # TRX-CSV-101 was updated
    assert data_excel["imported_count"] == 1 # TRX-XLS-201 was created
    assert data_excel["total_amount_eur"] == 4750.0
