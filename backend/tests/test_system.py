"""Comprehensive system test suite for FinnSpark (Finncubate) platform."""
import os
import sys
import time
import pytest
from fastapi.testclient import TestClient

# Ensure backend directory is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.config import config

client = TestClient(app)


class TestSystem:
    access_token = ""
    branch_id = 1
    applicant_id = None
    invite_token = ""
    created_founder_email = ""
    form_id = None

    def test_01_health_and_config(self):
        # Health check
        res = client.get("/api/health/")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
        assert res.json()["app"] == "FinnSpark"

        # Public config
        res = client.get("/api/config/")
        assert res.status_code == 200
        data = res.json()
        assert "app_name" in data
        assert "supported_languages" in data

    def test_02_auth_failures_and_success(self):
        # Invalid login
        res = client.post("/auth/login/", json={"email": "wrong@example.com", "password": "wrong"})
        assert res.status_code == 401

        # Valid login with admin
        res = client.post("/auth/login/", json={"email": "admin@finnpact.jo", "password": "Admin123!"})
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert "user" in data
        assert data["user"]["email"] == "admin@finnpact.jo"
        assert len(data["user"]["branches"]) > 0

        TestSystem.access_token = data["access_token"]
        TestSystem.branch_id = data["user"]["branches"][0]["id"]
        headers = {"Authorization": f"Bearer {TestSystem.access_token}"}

        # Auth Me endpoint
        res = client.get("/api/auth/me/", headers=headers)
        assert res.status_code == 200
        assert res.json()["email"] == "admin@finnpact.jo"

    def test_03_references_and_tenancy(self):
        headers = {"Authorization": f"Bearer {TestSystem.access_token}"}

        # References
        res = client.get("/api/countries/", headers=headers)
        assert res.status_code == 200
        assert isinstance(res.json(), list)

        res = client.get("/api/applicant-statuses/", headers=headers)
        assert res.status_code == 200
        assert len(res.json()) > 0

        res = client.get("/api/investment-statuses/", headers=headers)
        assert res.status_code == 200
        assert len(res.json()) > 0

        # Branches & stages
        res = client.get("/api/branches/", headers=headers)
        assert res.status_code == 200

        res = client.get(f"/api/stages/{TestSystem.branch_id}/", headers=headers)
        assert res.status_code == 200
        assert len(res.json()) > 0

    def test_04_forms_and_public_application(self):
        headers = {"Authorization": f"Bearer {TestSystem.access_token}"}

        # Get application forms for branch
        res = client.get(f"/api/application-forms/{TestSystem.branch_id}/", headers=headers)
        assert res.status_code == 200
        forms_data = res.json()
        forms_list = forms_data.get("results", forms_data if isinstance(forms_data, list) else [])
        assert len(forms_list) > 0
        TestSystem.form_id = forms_list[0]["id"]

        # Public form schema
        res = client.get(f"/api/public/forms/{TestSystem.form_id}/")
        assert res.status_code == 200
        form_data = res.json()
        assert form_data["id"] == TestSystem.form_id
        assert "fields" in form_data

        # Submit public application
        unique_email = f"tester_{int(time.time())}@autotest.io"
        TestSystem.created_founder_email = unique_email

        payload = {
            "answers": {
                "field_email": unique_email,
                "field_first_name": "Automated",
                "field_last_name": "Founder",
                "field_business_name": "AutoTest Robotics",
                "field_pitch": "Building advanced AI automation tools",
            },
            "labels": {
                "field_email": "Email Address",
                "field_first_name": "First Name",
                "field_last_name": "Last Name",
                "field_business_name": "Business Name",
                "field_pitch": "Elevator Pitch",
            },
        }
        res = client.post(f"/api/public/forms/{TestSystem.form_id}/submit/", json=payload)
        assert res.status_code == 200
        submitted = res.json()
        assert "applicant_id" in submitted
        TestSystem.applicant_id = submitted["applicant_id"]

    def test_05_selection_board_and_scoring(self):
        headers = {"Authorization": f"Bearer {TestSystem.access_token}"}

        # List applicants
        res = client.get(f"/api/v2/applicants/{TestSystem.branch_id}/", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "results" in data
        assert any(a["id"] == TestSystem.applicant_id for a in data["results"])

        # Applicant detail
        res = client.get(f"/api/applicants/{TestSystem.branch_id}/{TestSystem.applicant_id}/", headers=headers)
        assert res.status_code == 200
        app_data = res.json()
        assert app_data["email"] == TestSystem.created_founder_email
        assert app_data["business_name"] == "AutoTest Robotics"
        assert "scoring_forms" in app_data

        # Score applicant if scoring forms exist
        if app_data["scoring_forms"]:
            scoring_form = app_data["scoring_forms"][0]
            # Fetch full form to get questions
            f_res = client.get(f"/api/scoring-forms/{TestSystem.branch_id}/{scoring_form['id']}/", headers=headers)
            assert f_res.status_code == 200
            q_list = f_res.json().get("questions", [])
            answers = [{"question_id": q["id"], "score": 8.5} for q in q_list]
            score_res = client.post(
                f"/api/applicants/{TestSystem.branch_id}/{TestSystem.applicant_id}/score/",
                headers=headers,
                json={"scoring_form_id": scoring_form["id"], "answers": answers},
            )
            assert score_res.status_code == 200
            assert "average_score" in score_res.json()

    def test_06_founder_invitation_and_registration(self):
        headers = {"Authorization": f"Bearer {TestSystem.access_token}"}

        # 1. Staff generates invitation for applicant
        res = client.post(
            f"/api/applicants/{TestSystem.branch_id}/{TestSystem.applicant_id}/invite/",
            headers=headers,
        )
        assert res.status_code == 200
        invite_data = res.json()
        assert "invite_url" in invite_data
        assert "token=" in invite_data["invite_url"]
        assert invite_data["email"] == TestSystem.created_founder_email
        assert invite_data["invited_at"] is not None

        token = invite_data["invite_url"].split("token=")[1]
        TestSystem.invite_token = token

        # 2. Public /invite-info endpoint verifies token
        info_res = client.get(f"/api/auth/invite-info?token={token}")
        assert info_res.status_code == 200
        info = info_res.json()
        assert info["email"] == TestSystem.created_founder_email
        assert info["business_name"] == "AutoTest Robotics"

        # 3. Public /register endpoint completes registration
        reg_res = client.post(
            "/api/auth/register",
            json={
                "token": token,
                "password": "SecurePassword123!",
                "first_name": "Automated",
                "last_name": "Founder",
            },
        )
        assert reg_res.status_code == 200
        reg_data = reg_res.json()
        assert "access_token" in reg_data
        assert reg_data["user"]["email"] == TestSystem.created_founder_email

        # 4. Verify applicant record is now registered
        app_res = client.get(f"/api/applicants/{TestSystem.branch_id}/{TestSystem.applicant_id}/", headers=headers)
        assert app_res.status_code == 200
        assert app_res.json()["registered"] is True

        # 5. Founder logs in with new credentials
        founder_login = client.post(
            "/auth/login/",
            json={"email": TestSystem.created_founder_email, "password": "SecurePassword123!"},
        )
        assert founder_login.status_code == 200
        founder_roles = founder_login.json()["user"]["branches"][0]["roles"]
        assert "entrepreneur" in founder_roles

    def test_07_programs_and_courses(self):
        headers = {"Authorization": f"Bearer {TestSystem.access_token}"}

        # Programs
        res = client.get(f"/api/programs/{TestSystem.branch_id}/", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "results" in data or isinstance(data, list)

        # Courses
        res = client.get(f"/api/courses/{TestSystem.branch_id}/", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "results" in data or isinstance(data, list)

    def test_08_dealflow_and_investments(self):
        headers = {"Authorization": f"Bearer {TestSystem.access_token}"}

        # Dealflow
        res = client.get(f"/api/dealflow/{TestSystem.branch_id}/", headers=headers)
        assert res.status_code == 200

        # Investments
        res = client.get(f"/api/investments/{TestSystem.branch_id}/", headers=headers)
        assert res.status_code == 200

    def test_09_collaboration_features(self):
        headers = {"Authorization": f"Bearer {TestSystem.access_token}"}

        # Announcements
        res = client.get(f"/api/announcements/{TestSystem.branch_id}/", headers=headers)
        assert res.status_code == 200

        # Calendar events
        res = client.get(f"/api/calendar/{TestSystem.branch_id}/", headers=headers)
        assert res.status_code == 200

        # Chat conversations
        res = client.get("/api/chat/conversations/", headers=headers)
        assert res.status_code == 200

    def test_10_reports_and_dashboards(self):
        headers = {"Authorization": f"Bearer {TestSystem.access_token}"}

        # Detailed info reports
        for section in ["overview", "financial-timeline", "investment-metrics"]:
            res = client.get(f"/api/branch/{TestSystem.branch_id}/reports/detailed-info/{section}/", headers=headers)
            assert res.status_code == 200
            assert "headers" in res.json()
            assert "results" in res.json()

        # Portfolio snapshot report
        res = client.get(f"/api/branch/{TestSystem.branch_id}/reports/portfolio-snapshot/", headers=headers)
        assert res.status_code == 200

        # Dashboard programs
        res = client.get(f"/api/dashboard-program/?branch_id={TestSystem.branch_id}", headers=headers)
        assert res.status_code == 200
