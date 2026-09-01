"""Tests for System Maintenance and Entrepreneur Data Reset."""
import os
import sys
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.database import Base, engine

client = TestClient(app)


class TestSystemReset:
    admin_token = ""
    regular_token = ""
    branch_id = 1

    @classmethod
    def setup_class(cls):
        Base.metadata.create_all(bind=engine)
        # Admin login
        res = client.post("/auth/login/", json={"email": "admin@finnpact.jo", "password": "Admin123!"})
        assert res.status_code == 200
        cls.admin_token = res.json()["access_token"]
        cls.branch_id = res.json()["user"]["branches"][0]["id"]

        # Mentor login (non-admin)
        res = client.post("/auth/login/", json={"email": "mentor1@finnpact.jo", "password": "Admin123!"})
        if res.status_code == 200:
            cls.regular_token = res.json()["access_token"]

    def test_01_get_data_stats(self):
        headers = {"Authorization": f"Bearer {TestSystemReset.admin_token}"}
        res = client.get(f"/api/system/entrepreneur-data-stats/{TestSystemReset.branch_id}/", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "applicants_count" in data
        assert "businesses_count" in data
        assert "disbursements_count" in data

    def test_02_non_admin_cannot_access(self):
        if not TestSystemReset.regular_token:
            pytest.skip("No non-admin token")
        headers = {"Authorization": f"Bearer {TestSystemReset.regular_token}"}
        res = client.get(f"/api/system/entrepreneur-data-stats/{TestSystemReset.branch_id}/", headers=headers)
        assert res.status_code == 403

    def test_03_invalid_confirmation_rejected(self):
        headers = {"Authorization": f"Bearer {TestSystemReset.admin_token}"}
        res = client.post(
            f"/api/system/reset-entrepreneur-data/{TestSystemReset.branch_id}/",
            json={"mode": "wipe", "confirmation": "WRONG"},
            headers=headers
        )
        assert res.status_code == 400

    def test_04_reset_and_reseed_success(self):
        headers = {"Authorization": f"Bearer {TestSystemReset.admin_token}"}
        res = client.post(
            f"/api/system/reset-entrepreneur-data/{TestSystemReset.branch_id}/",
            json={"mode": "reseed", "confirmation": "RESET"},
            headers=headers
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["reseeded"] is True

        # Check stats afterwards
        res = client.get(f"/api/system/entrepreneur-data-stats/{TestSystemReset.branch_id}/", headers=headers)
        assert res.status_code == 200
        stats = res.json()
        assert stats["applicants_count"] == 40
        assert stats["businesses_count"] == 40
        assert stats["disbursements_count"] == 10
