"""Tests for User Management, Profile Editing, Role Assignment, and Branch Unlinking."""
import os
import sys
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.database import Base, engine

client = TestClient(app)


class TestUsersRoles:
    admin_token = ""
    regular_token = ""
    branch_id = 1
    admin_user_id = None
    created_user_id = None
    available_roles = []
    available_statuses = []

    @classmethod
    def setup_class(cls):
        Base.metadata.create_all(bind=engine)
        from app.database import SessionLocal
        from app.models import User, UserRole
        with SessionLocal() as db:
            old_users = db.query(User).filter(
                User.email.in_(["test.staff.member@finnpact.jo", "alex.stafford@finnpact.jo"])
            ).all()
            for u in old_users:
                db.query(UserRole).filter(UserRole.user_id == u.id).delete()
                db.delete(u)
            db.commit()

        # Admin login
        res = client.post("/auth/login/", json={"email": "admin@finnpact.jo", "password": "Admin123!"})
        assert res.status_code == 200
        data = res.json()
        cls.admin_token = data["access_token"]
        cls.branch_id = data["user"]["branches"][0]["id"]
        cls.admin_user_id = data["user"]["id"]

        # Mentor login (non-admin)
        res = client.post("/auth/login/", json={"email": "mentor1@finnpact.jo", "password": "Admin123!"})
        if res.status_code == 200:
            cls.regular_token = res.json()["access_token"]

    def test_01_list_roles_and_statuses(self):
        headers = {"Authorization": f"Bearer {TestUsersRoles.admin_token}"}
        res = client.get(f"/api/roles/{TestUsersRoles.branch_id}/", headers=headers)
        assert res.status_code == 200
        TestUsersRoles.available_roles = res.json()
        assert len(TestUsersRoles.available_roles) >= 2

        res = client.get("/api/user-statuses/", headers=headers)
        assert res.status_code == 200
        TestUsersRoles.available_statuses = res.json()
        assert len(TestUsersRoles.available_statuses) >= 2

    def test_02_invite_user_with_multi_roles(self):
        headers = {"Authorization": f"Bearer {TestUsersRoles.admin_token}"}
        role_ids = [r["id"] for r in TestUsersRoles.available_roles[:2]]

        payload = {
            "email": "test.staff.member@finnpact.jo",
            "first_name": "Test",
            "last_name": "Staff",
            "position": "Junior Program Lead",
            "company": "finnpact Jo",
            "password": "StaffPassword123!",
            "role_ids": role_ids,
        }
        res = client.post(f"/api/users/{TestUsersRoles.branch_id}/invite/", json=payload, headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "id" in data
        TestUsersRoles.created_user_id = data["id"]
        assert data["first_name"] == "Test"
        assert len(data["roles"]) == len(role_ids)

    def test_03_update_user_profile(self):
        headers = {"Authorization": f"Bearer {TestUsersRoles.admin_token}"}
        uid = TestUsersRoles.created_user_id

        payload = {
            "first_name": "Alexander",
            "last_name": "Stafford",
            "position": "Senior Acceleration Manager",
            "company": "Global Venture Labs",
            "email": "alex.stafford@finnpact.jo",
        }
        res = client.patch(f"/api/users/{TestUsersRoles.branch_id}/{uid}/", json=payload, headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["first_name"] == "Alexander"
        assert data["last_name"] == "Stafford"
        assert data["position"] == "Senior Acceleration Manager"
        assert data["company"] == "Global Venture Labs"
        assert data["email"] == "alex.stafford@finnpact.jo"

    def test_04_assign_and_change_roles(self):
        headers = {"Authorization": f"Bearer {TestUsersRoles.admin_token}"}
        uid = TestUsersRoles.created_user_id
        single_role_id = TestUsersRoles.available_roles[0]["id"]

        # 1. Update to single role
        res = client.patch(
            f"/api/users/{TestUsersRoles.branch_id}/{uid}/",
            json={"role_ids": [single_role_id]},
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert len(data["roles"]) == 1
        assert data["roles"][0]["id"] == single_role_id

        # 2. Update to multiple roles
        all_role_ids = [r["id"] for r in TestUsersRoles.available_roles]
        res = client.patch(
            f"/api/users/{TestUsersRoles.branch_id}/{uid}/",
            json={"role_ids": all_role_ids},
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert len(data["roles"]) == len(all_role_ids)

    def test_05_update_user_status(self):
        headers = {"Authorization": f"Bearer {TestUsersRoles.admin_token}"}
        uid = TestUsersRoles.created_user_id

        # Change status to suspended
        res = client.patch(
            f"/api/users/{TestUsersRoles.branch_id}/{uid}/",
            json={"status": "suspended"},
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"]["code_name"] == "suspended"

        # Change status back to active
        res = client.patch(
            f"/api/users/{TestUsersRoles.branch_id}/{uid}/",
            json={"status": "active"},
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"]["code_name"] == "active"

    def test_06_admin_reset_user_password(self):
        headers = {"Authorization": f"Bearer {TestUsersRoles.admin_token}"}
        uid = TestUsersRoles.created_user_id
        new_pw = "NewSecretPass456!"

        res = client.patch(
            f"/api/users/{TestUsersRoles.branch_id}/{uid}/",
            json={"password": new_pw},
            headers=headers,
        )
        assert res.status_code == 200

        # Login with new password
        login_res = client.post("/auth/login/", json={"email": "alex.stafford@finnpact.jo", "password": new_pw})
        assert login_res.status_code == 200
        assert "access_token" in login_res.json()

    def test_07_prevent_self_deletion(self):
        headers = {"Authorization": f"Bearer {TestUsersRoles.admin_token}"}
        res = client.delete(f"/api/users/{TestUsersRoles.branch_id}/{TestUsersRoles.admin_user_id}/", headers=headers)
        assert res.status_code == 400
        assert "cannot remove" in res.json()["detail"].lower()

    def test_08_delete_user_from_branch(self):
        headers = {"Authorization": f"Bearer {TestUsersRoles.admin_token}"}
        uid = TestUsersRoles.created_user_id

        res = client.delete(f"/api/users/{TestUsersRoles.branch_id}/{uid}/", headers=headers)
        assert res.status_code == 200
        assert "removed from branch" in res.json()["detail"].lower()

        # Verify user no longer in branch users list
        list_res = client.get(f"/api/v2/users/{TestUsersRoles.branch_id}/?search=alex.stafford", headers=headers)
        assert list_res.status_code == 200
        assert list_res.json()["count"] == 0

    def test_09_non_admin_forbidden(self):
        if not TestUsersRoles.regular_token:
            pytest.skip("No mentor token available")
        headers = {"Authorization": f"Bearer {TestUsersRoles.regular_token}"}

        # Try to invite
        res = client.post(
            f"/api/users/{TestUsersRoles.branch_id}/invite/",
            json={"email": "unauthorized@test.com", "role_id": 1},
            headers=headers,
        )
        assert res.status_code == 403

        # Try to patch
        res = client.patch(
            f"/api/users/{TestUsersRoles.branch_id}/1/",
            json={"first_name": "Hacked"},
            headers=headers,
        )
        assert res.status_code == 403

        # Try to delete
        res = client.delete(f"/api/users/{TestUsersRoles.branch_id}/1/", headers=headers)
        assert res.status_code == 403
