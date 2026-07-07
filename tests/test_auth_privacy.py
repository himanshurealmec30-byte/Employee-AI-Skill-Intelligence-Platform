import unittest
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from run import create_app, _authenticate_user


class EmployeePrivacyTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def _login_employee(self):
        with self.client.session_transaction() as session:
            session["user"] = {
                "id": 999001,
                "username": "employee privacy test",
                "role": "employee",
                "employee_id": "TB999001",
                "source_employee_code": "1",
            }

    def test_employee_dashboard_redirects_to_profile(self):
        self._login_employee()
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/career")

    def test_employee_cannot_access_other_employee_api(self):
        self._login_employee()
        response = self.client.get("/api/career/2")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "Unauthorized")

    def test_employee_nav_hides_dashboard_and_career_links(self):
        self._login_employee()
        response = self.client.get("/career")
        html = response.data
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"My Profile", html)
        self.assertNotIn(b">Dashboard</a>", html)
        self.assertNotIn(b">Career</a>", html)

    def test_first_login_password_change_returns_to_login(self):
        user = {
            "id": 777001,
            "username": "first login test",
            "role": "employee",
            "employee_id": "TB777001",
            "source_employee_code": "1",
            "first_login": True,
        }
        with self.client.session_transaction() as session:
            session["user"] = {
                "id": user["id"],
                "username": user["username"],
                "role": user["role"],
                "employee_id": user.get("employee_id"),
                "source_employee_code": user.get("source_employee_code"),
            }
            session["first_login_user_id"] = user["id"]
            session["first_login_demo_otp"] = "123456"
        with patch("run._get_registered_user_by_id", return_value=user), \
             patch("run._verify_otp", return_value=True), \
             patch("run._change_user_password", return_value={**user, "first_login": False}):
            response = self.client.post(
                "/first-login",
                data={
                    "otp": "123456",
                    "password": "NewPass123!",
                    "confirm_password": "NewPass123!",
                },
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")
        with self.client.session_transaction() as session:
            self.assertNotIn("user", session)

    def test_admin_can_request_password_reset_by_username(self):
        admin = {
            "id": 1,
            "username": "admin",
            "role": "admin",
            "email": "admin@talentbeacon.local",
            "company_email": "admin@talentbeacon.local",
        }
        with patch("run._find_password_reset_user", return_value=admin), \
             patch("run._issue_otp", return_value="654321") as issue_otp:
            response = self.client.post("/forgot-password", data={"identity": "admin"})
        self.assertEqual(response.status_code, 200)
        issue_otp.assert_called_once_with(admin, "password_reset")
        self.assertIn(b"654321", response.data)
        self.assertIn(b"otpTimer", response.data)
        self.assertIn(b"data-toggle-password=\"resetPassword\"", response.data)

    def test_admin_password_reset_returns_to_login(self):
        admin = {
            "id": 1,
            "username": "admin",
            "role": "admin",
            "email": "admin@talentbeacon.local",
            "company_email": "admin@talentbeacon.local",
        }
        with patch("run._find_password_reset_user", return_value=admin), \
             patch("run._verify_otp", return_value=True), \
             patch("run._change_user_password", return_value=admin) as change_password:
            response = self.client.post(
                "/reset-password",
                data={
                    "identity": "admin",
                    "otp": "654321",
                    "password": "AdminNew123!",
                    "confirm_password": "AdminNew123!",
                },
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")
        change_password.assert_called_once()

    def test_login_page_has_password_show_toggle(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"data-toggle-password=\"loginPassword\"", response.data)

    def test_reset_admin_password_overrides_old_demo_password(self):
        admin = {
            "id": 1,
            "username": "admin",
            "role": "admin",
            "email": "admin@talentbeacon.local",
            "company_email": "admin@talentbeacon.local",
            "password_hash": generate_password_hash("AdminNew123!"),
            "first_login": False,
            "failed_attempts": 0,
            "locked_until": None,
        }
        with patch("run._get_registered_user", return_value=admin), \
             patch("run._save_registered_user"):
            user, error = _authenticate_user("admin", "AdminNew123!")
            self.assertIsNotNone(user)
            self.assertIsNone(error)

            user, error = _authenticate_user("admin", "admin123")
            self.assertIsNone(user)
            self.assertEqual(error, "Incorrect password.")


if __name__ == "__main__":
    unittest.main()
