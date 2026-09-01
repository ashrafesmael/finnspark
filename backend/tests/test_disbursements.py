"""Tests for the Disbursements module."""
import os
import sys
import pytest
from fastapi.testclient import TestClient

# Ensure backend directory is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.database import Base, engine

client = TestClient(app)


class TestDisbursements:
    admin_token = ""
    regular_token = ""
    branch_id = 1
    program_id = None
    batch_id = None

    @classmethod
    def setup_class(cls):
        Base.metadata.create_all(bind=engine)
        # Admin login
        res = client.post("/auth/login/", json={"email": "admin@finnpact.jo", "password": "Admin123!"})
        assert res.status_code == 200
        data = res.json()
        cls.admin_token = data["access_token"]
        cls.branch_id = data["user"]["branches"][0]["id"]

        # Investment Manager login (non-admin role)
        res = client.post("/auth/login/", json={"email": "investments@finnpact.jo", "password": "Admin123!"})
        if res.status_code == 200:
            cls.regular_token = res.json()["access_token"]

    def test_01_get_cohort_and_summary(self):
        headers = {"Authorization": f"Bearer {TestDisbursements.admin_token}"}
        
        # Get programs
        res = client.get(f"/api/programs/{TestDisbursements.branch_id}/", headers=headers)
        assert res.status_code == 200
        programs = res.json()["results"]
        assert len(programs) > 0
        TestDisbursements.program_id = programs[0]["id"]

        # Get initial summary
        res = client.get(f"/api/disbursements/{TestDisbursements.branch_id}/summary/", headers=headers)
        assert res.status_code == 200
        summary = res.json()
        assert "total_batches" in summary
        assert "totals_by_currency" in summary

    def test_02_create_disbursement_batch_auto_populate(self):
        headers = {"Authorization": f"Bearer {TestDisbursements.admin_token}"}
        payload = {
            "program_id": TestDisbursements.program_id,
            "title": "August 2026 Monthly Grant",
            "payment_date": "2026-08-31",
            "currency": "USD",
            "base_amount": 5000.0,
            "notes": "Regular monthly acceleration disbursement",
        }
        res = client.post(f"/api/disbursements/{TestDisbursements.branch_id}/", json=payload, headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["title"] == "August 2026 Monthly Grant"
        assert data["currency"] == "USD"
        assert data["base_amount"] == 5000.0
        assert data["status"] == "draft"
        assert len(data["items"]) > 0
        
        # Verify items default to 100% and 5000 amount
        for item in data["items"]:
            assert item["percentage"] == 100.0
            assert item["amount"] == 5000.0
            assert item["is_included"] is True

        expected_total = len(data["items"]) * 5000.0
        assert data["total_amount"] == expected_total

        TestDisbursements.batch_id = data["id"]

    def test_03_update_startup_percentages(self):
        headers = {"Authorization": f"Bearer {TestDisbursements.admin_token}"}
        
        # Get current batch
        res = client.get(f"/api/disbursements/{TestDisbursements.branch_id}/{TestDisbursements.batch_id}/", headers=headers)
        assert res.status_code == 200
        batch = res.json()
        items = batch["items"]
        assert len(items) >= 2

        # Change first item to 50%, second to 0%
        items[0]["percentage"] = 50.0
        items[0]["notes"] = "Milestone partially achieved (50%)"
        items[1]["percentage"] = 0.0
        items[1]["notes"] = "Pending milestone review"

        update_payload = {
            "title": "August 2026 Monthly Grant - Adjusted",
            "base_amount": 5000.0,
            "items": [
                {
                    "id": it["id"],
                    "business_id": it["business_id"],
                    "percentage": it["percentage"],
                    "is_included": it["is_included"],
                    "notes": it.get("notes", ""),
                }
                for it in items
            ],
        }
        res = client.put(f"/api/disbursements/{TestDisbursements.branch_id}/{TestDisbursements.batch_id}/", json=update_payload, headers=headers)
        assert res.status_code == 200
        updated = res.json()
        assert updated["title"] == "August 2026 Monthly Grant - Adjusted"
        
        updated_items = updated["items"]
        assert updated_items[0]["percentage"] == 50.0
        assert updated_items[0]["amount"] == 2500.0
        assert updated_items[1]["percentage"] == 0.0
        assert updated_items[1]["amount"] == 0.0

        expected_total = 2500.0 + 0.0 + sum(it["amount"] for it in updated_items[2:])
        assert updated["total_amount"] == expected_total

    def test_04_confirm_and_process_batch(self):
        headers = {"Authorization": f"Bearer {TestDisbursements.admin_token}"}
        res = client.post(f"/api/disbursements/{TestDisbursements.branch_id}/{TestDisbursements.batch_id}/confirm/", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["batch"]["status"] == "processed"
        assert data["batch"]["confirmed_by"] is not None
        assert data["batch"]["confirmed_at"] is not None

    def test_05_processed_batch_is_locked(self):
        headers = {"Authorization": f"Bearer {TestDisbursements.admin_token}"}
        
        # Editing should fail
        res = client.put(
            f"/api/disbursements/{TestDisbursements.branch_id}/{TestDisbursements.batch_id}/",
            json={"title": "Should Fail"},
            headers=headers,
        )
        assert res.status_code == 400
        assert "Cannot modify a processed disbursement batch" in res.json()["detail"]

        # Deleting should fail
        res = client.delete(
            f"/api/disbursements/{TestDisbursements.branch_id}/{TestDisbursements.batch_id}/",
            headers=headers,
        )
        assert res.status_code == 400
        assert "Cannot delete a processed disbursement batch" in res.json()["detail"]

    def test_06_non_admin_cannot_reopen(self):
        if not TestDisbursements.regular_token:
            pytest.skip("Regular token not available")
        headers = {"Authorization": f"Bearer {TestDisbursements.regular_token}"}
        res = client.post(
            f"/api/disbursements/{TestDisbursements.branch_id}/{TestDisbursements.batch_id}/reopen/",
            headers=headers,
        )
        assert res.status_code in (403, 401)

    def test_07_admin_reopen_and_reedit(self):
        headers = {"Authorization": f"Bearer {TestDisbursements.admin_token}"}
        res = client.post(
            f"/api/disbursements/{TestDisbursements.branch_id}/{TestDisbursements.batch_id}/reopen/",
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["batch"]["status"] == "draft"
        assert data["batch"]["confirmed_by"] is None

        # Re-edit is now allowed
        res = client.put(
            f"/api/disbursements/{TestDisbursements.branch_id}/{TestDisbursements.batch_id}/",
            json={"notes": "Reopened and reviewed by admin"},
            headers=headers,
        )
        assert res.status_code == 200
        assert res.json()["notes"] == "Reopened and reviewed by admin"

        # Re-confirm
        res = client.post(f"/api/disbursements/{TestDisbursements.branch_id}/{TestDisbursements.batch_id}/confirm/", headers=headers)
        assert res.status_code == 200
        assert res.json()["batch"]["status"] == "processed"

    def test_08_export_excel(self):
        headers = {"Authorization": f"Bearer {TestDisbursements.admin_token}"}
        res = client.get(
            f"/api/disbursements/{TestDisbursements.branch_id}/{TestDisbursements.batch_id}/export/",
            headers=headers,
        )
        assert res.status_code == 200
        assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in res.headers["content-type"]
        assert len(res.content) > 1000  # Valid Excel file bytes
