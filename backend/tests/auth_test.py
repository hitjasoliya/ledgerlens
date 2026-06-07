from __future__ import annotations

import sys
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app
from app.database import engine, Base, SessionLocal
from app.models import User
from app.auth import get_password_hash


class TestAuthAndAuthorization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create all tables (e.g. users)
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)
        cls.db = SessionLocal()

        # Clean up database for clean test
        cls.db.query(User).delete()
        cls.db.commit()

        # Seed default admin
        cls.admin_password = "admin123"
        cls.admin_user = User(
            username="admin",
            hashed_password=get_password_hash(cls.admin_password),
            role="admin",
        )
        cls.db.add(cls.admin_user)
        cls.db.commit()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_01_login_success(self):
        # Try to log in with admin
        response = self.client.post(
            "/api/auth/login",
            json={
                "username": "admin",
                "password": self.admin_password,
                "role": "admin",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["user"]["username"], "admin")
        self.assertEqual(data["user"]["role"], "admin")
        self.__class__.admin_token = data["access_token"]

    def test_02_login_invalid_password(self):
        response = self.client.post(
            "/api/auth/login",
            json={
                "username": "admin",
                "password": "wrongpassword",
                "role": "admin",
            },
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn("detail", response.json())

    def test_03_login_invalid_role(self):
        response = self.client.post(
            "/api/auth/login",
            json={
                "username": "admin",
                "password": self.admin_password,
                "role": "employee",
            },
        )
        self.assertEqual(response.status_code, 401)

    def test_04_get_profile_me(self):
        # Access with token
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        response = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["username"], "admin")
        self.assertEqual(data["role"], "admin")

    def test_05_create_user_by_admin(self):
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        response = self.client.post(
            "/api/users",
            json={
                "username": "employee1",
                "password": "employee123",
                "role": "employee",
            },
            headers=headers,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["username"], "employee1")
        self.assertEqual(data["role"], "employee")
        self.__class__.employee_id = data["id"]

    def test_06_employee_login_and_restricted_access(self):
        # Log in with newly created employee
        response = self.client.post(
            "/api/auth/login",
            json={
                "username": "employee1",
                "password": "employee123",
                "role": "employee",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        emp_token = data["access_token"]

        # Employees should not be allowed to list users (admin only)
        headers = {"Authorization": f"Bearer {emp_token}"}
        response = self.client.get("/api/users", headers=headers)
        self.assertEqual(response.status_code, 403)

    def test_07_delete_user_by_admin(self):
        # Admin deletes employee1
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        response = self.client.delete(f"/api/users/{self.employee_id}", headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])

        # Verify employee1 cannot login anymore
        response = self.client.post(
            "/api/auth/login",
            json={
                "username": "employee1",
                "password": "employee123",
                "role": "employee",
            },
        )
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
