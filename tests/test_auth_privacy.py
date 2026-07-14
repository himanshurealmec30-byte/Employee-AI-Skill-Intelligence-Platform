import unittest
from unittest.mock import patch

import pandas as pd
from werkzeug.security import generate_password_hash

from run import create_app, _authenticate_user, _create_accounts_from_active_dataset


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

    def test_employee_profile_uses_dataset_row_from_generated_account(self):
        generated_user = {
            "id": 999002,
            "username": "Employee 7",
            "role": "employee",
            "employee_id": "TB30999",
            "source_employee_code": "dataset-abc:7",
            "source_employee_key": "file:file-hash:row:7",
            "created_by": 1,
            "first_login": False,
        }
        with self.client.session_transaction() as session:
            session["user"] = {
                "id": generated_user["id"],
                "username": generated_user["username"],
                "role": generated_user["role"],
                "employee_id": generated_user["employee_id"],
                "source_employee_code": generated_user["source_employee_code"],
            }
        with patch("run._get_registered_user", return_value=generated_user), \
             patch("run._get_registered_user_by_id", return_value=generated_user):
            response = self.client.get("/career")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"const id = 7;", response.data)

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

    def test_active_duplicate_employee_name_does_not_redirect_to_first_login(self):
        pending_same_name = {
            "id": 777010,
            "username": "Employee 1",
            "role": "employee",
            "employee_id": "TB1001",
            "source_employee_code": "old-dataset:1",
            "first_login": True,
        }
        active_user = {
            "id": 777011,
            "username": "Employee 1",
            "role": "employee",
            "employee_id": "TB2001",
            "source_employee_code": "active-dataset:1",
            "first_login": False,
        }
        with self.client.session_transaction() as session:
            session["user"] = {
                "id": active_user["id"],
                "username": active_user["username"],
                "role": active_user["role"],
                "employee_id": active_user["employee_id"],
                "source_employee_code": active_user["source_employee_code"],
            }
        with patch("run._get_registered_user_by_id", return_value=active_user), \
             patch("run._get_registered_user", return_value=pending_same_name):
            response = self.client.get("/career")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"const id = 1;", response.data)

    def test_active_account_visiting_first_login_redirects_to_dashboard(self):
        active_user = {
            "id": 777012,
            "username": "active user",
            "role": "admin",
            "employee_id": None,
            "first_login": False,
        }
        with self.client.session_transaction() as session:
            session["user"] = {
                "id": active_user["id"],
                "username": active_user["username"],
                "role": active_user["role"],
                "employee_id": None,
            }
            session["first_login_user_id"] = active_user["id"]
        with patch("run._get_registered_user_by_id", return_value=active_user), \
             patch("run._get_registered_user", return_value=active_user):
            response = self.client.get("/first-login")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/dashboard")

    def test_admin_session_refresh_does_not_become_employee_with_same_id(self):
        admin_user = {
            "id": 1,
            "username": "admin",
            "role": "admin",
            "employee_id": None,
            "first_login": False,
        }
        mysql_employee_same_id = {
            "id": 1,
            "username": "Employee 1",
            "role": "employee",
            "employee_id": "TB1001",
            "first_login": False,
        }
        with self.client.session_transaction() as session:
            session["user"] = {
                "id": 1,
                "username": "admin",
                "role": "admin",
                "employee_id": None,
            }
        with patch("run._get_registered_user", return_value=admin_user), \
             patch("run._get_registered_user_by_id", return_value=mysql_employee_same_id):
            response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as session:
            self.assertEqual(session["user"]["role"], "admin")
            self.assertEqual(session["user"]["username"], "admin")

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

    def test_reuploaded_employee_file_reuses_completed_account(self):
        users = [{
            "id": 5001,
            "employee_id": "TB1001",
            "username": "Employee 1",
            "email": "employee.1.tb1001@talentbeacon.local",
            "company_email": "employee.1.tb1001@talentbeacon.local",
            "password_hash": generate_password_hash("OldPass123!"),
            "role": "employee",
            "first_login": False,
            "created_by": 10,
            "created_from_upload": True,
            "source_dataset_id": "old-dataset",
            "source_employee_code": "old-dataset:1",
            "source_employee_key": "file:same-file-hash:row:1",
            "source_file_hash": "same-file-hash",
            "created_at": "2026-01-01T00:00:00+00:00",
        }]
        df = pd.DataFrame([{
            "Employee_ID": 999,
            "Display_Employee_ID": 1,
            "Employee_Code": "new-dataset:1",
            "Name": "Employee 1",
            "Email": "",
        }])
        with patch("run._active_dataset_id_for_actor", return_value="new-dataset"), \
             patch("run._active_dataset_hash_for_actor", return_value="same-file-hash"), \
             patch("run.load_active_employee_df", return_value=df), \
             patch("run._load_registered_users", return_value=users), \
             patch("run._save_registered_users"), \
             patch("run._sync_user_accounts_to_mysql"), \
             patch("run._audit"):
            result = _create_accounts_from_active_dataset(actor_id=10, reset_existing_passwords=True)
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["reset"], 0)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(users[0]["source_dataset_id"], "new-dataset")
        self.assertEqual(users[0]["source_employee_code"], "new-dataset:1")
        self.assertEqual(users[0]["company_email"], "employee.1.tb1001@talentbeacon.local")
        self.assertFalse(users[0]["first_login"])

    def test_different_employee_file_does_not_reuse_same_row_account(self):
        users = [{
            "id": 5001,
            "employee_id": "TB1001",
            "username": "Employee 1",
            "email": "employee.1.tb1001@talentbeacon.local",
            "company_email": "employee.1.tb1001@talentbeacon.local",
            "password_hash": generate_password_hash("OldPass123!"),
            "role": "employee",
            "first_login": False,
            "created_by": 10,
            "created_from_upload": True,
            "source_dataset_id": "old-dataset",
            "source_employee_code": "old-dataset:1",
            "source_employee_key": "file:first-file-hash:row:1",
            "source_file_hash": "first-file-hash",
            "created_at": "2026-01-01T00:00:00+00:00",
        }]
        df = pd.DataFrame([{
            "Employee_ID": 999,
            "Display_Employee_ID": 1,
            "Employee_Code": "new-dataset:1",
            "Name": "Employee 1",
            "Email": "",
        }])
        with patch("run._active_dataset_id_for_actor", return_value="new-dataset"), \
             patch("run._active_dataset_hash_for_actor", return_value="second-file-hash"), \
             patch("run.load_active_employee_df", return_value=df), \
             patch("run._load_registered_users", return_value=users), \
             patch("run._save_registered_users"), \
             patch("run._sync_user_accounts_to_mysql"), \
             patch("run._audit"):
            result = _create_accounts_from_active_dataset(actor_id=10, reset_existing_passwords=True)
        self.assertEqual(result["created"], 1)
        self.assertEqual(result["reset"], 0)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(len(users), 2)
        self.assertEqual(users[0]["source_dataset_id"], "old-dataset")
        self.assertEqual(users[1]["source_dataset_id"], "new-dataset")
        self.assertTrue(users[1]["first_login"])

    def test_pending_employee_reset_prefers_newest_temp_password(self):
        users = [
            {
                "id": 6001,
                "employee_id": "TB1001",
                "username": "Employee 1",
                "email": "employee.1.tb1001@talentbeacon.local",
                "company_email": "employee.1.tb1001@talentbeacon.local",
                "password_hash": generate_password_hash("ExpiredPass123!"),
                "role": "employee",
                "first_login": True,
                "created_by": 10,
                "created_from_upload": True,
                "source_dataset_id": "active-dataset",
                "source_employee_code": "active-dataset:1",
                "source_employee_key": "file:file-hash:row:1",
                "source_file_hash": "file-hash",
                "temp_password_expires_at": "2026-01-01T00:00:00+00:00",
            },
            {
                "id": 6002,
                "employee_id": "TB1001",
                "username": "Employee 1",
                "email": "employee.1.tb1001@talentbeacon.local",
                "company_email": "employee.1.tb1001@talentbeacon.local",
                "password_hash": generate_password_hash("FreshPass123!"),
                "role": "employee",
                "first_login": True,
                "created_by": 10,
                "created_from_upload": True,
                "source_dataset_id": "active-dataset",
                "source_employee_code": "active-dataset:1",
                "source_employee_key": "file:file-hash:row:1",
                "source_file_hash": "file-hash",
                "temp_password_expires_at": "2099-01-01T00:00:00+00:00",
            },
        ]
        df = pd.DataFrame([{
            "Employee_ID": 1,
            "Display_Employee_ID": 1,
            "Employee_Code": "active-dataset:1",
            "Name": "Employee 1",
            "Email": "",
        }])
        with patch("run._active_dataset_id_for_actor", return_value="active-dataset"), \
             patch("run._active_dataset_hash_for_actor", return_value="file-hash"), \
             patch("run.load_active_employee_df", return_value=df), \
             patch("run._load_registered_users", return_value=users), \
             patch("run._save_registered_users"), \
             patch("run._sync_user_accounts_to_mysql"), \
             patch("run._audit"):
            result = _create_accounts_from_active_dataset(actor_id=10, reset_existing_passwords=False)
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(users[1]["temp_password_expires_at"], "2099-01-01T00:00:00+00:00")

    def test_correct_expired_temporary_password_gets_grace_login(self):
        user = {
            "id": 7001,
            "username": "Employee Expired",
            "role": "employee",
            "employee_id": "TB7001",
            "password_hash": generate_password_hash("ExpiredPass123!"),
            "first_login": True,
            "temp_password_expires_at": "2026-01-01T00:00:00+00:00",
            "failed_attempts": 0,
            "locked_until": None,
        }
        with patch("run._save_registered_user") as save_user, patch("run._audit"):
            authed, error = _authenticate_user.__globals__["_authenticate_registered_user"](user, "ExpiredPass123!")
        self.assertIsNotNone(authed)
        self.assertIsNone(error)
        self.assertNotEqual(user["temp_password_expires_at"], "2026-01-01T00:00:00+00:00")
        save_user.assert_called_once()


if __name__ == "__main__":
    unittest.main()
