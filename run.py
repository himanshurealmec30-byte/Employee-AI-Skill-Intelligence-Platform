"""Flask application factory and routes for TalentBeacon."""
import json
import math
import os
import re
import secrets
import string
from functools import wraps
from io import BytesIO
from pathlib import Path
from datetime import datetime, timedelta, timezone

import bcrypt
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

import config
from src.services.email_service import sendOtpEmail
from src.services.talent_service import get_service, reload_service
from src.services.workspace_service import (
    activate_dataset,
    dashboard_upload_summary,
    delete_dataset,
    get_active_dataset,
    get_jd_matches,
    get_project_matches,
    list_dataset_uploads,
    list_projects,
    load_active_employee_df,
    match_project,
    process_dataset_upload,
    process_jd_upload,
    project_requirements_from_document,
    project_detail,
    refresh_project_from_source,
    remove_project,
    save_project_from_form,
)
from src.utils.skills import contains_all_skills, split_skills


def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = config.SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = int(getattr(config, "MAX_UPLOAD_MB", 50)) * 1024 * 1024
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = bool(getattr(config, "IS_PRODUCTION", False))
    app.config["PREFERRED_URL_SCHEME"] = "https" if getattr(config, "IS_PRODUCTION", False) else "http"
    app.config["WTF_CSRF_ENABLED"] = bool(getattr(config, "CSRF_ENABLED", False))
    app.config.setdefault("rate_limit_buckets", {})

    def csrf_token():
        token = session.get("_csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["_csrf_token"] = token
        return token

    @app.context_processor
    def inject_security_helpers():
        return {"csrf_token": csrf_token}

    @app.before_request
    def load_service():
        if "user" not in session:
            app.config["service"] = None
            return
        session_user = session["user"]
        if session_user.get("role") in {"admin", "hr", "manager"}:
            # Privileged demo/login users can share numeric ids with uploaded
            # employee accounts. Never refresh admin/HR/manager sessions by id
            # unless the username itself resolves to that privileged account.
            registered_user = _get_registered_user(session_user.get("username"))
        else:
            registered_user = _get_registered_user_by_id(session_user.get("id")) or _get_registered_user(session_user.get("username"))
        if registered_user:
            session["user"].update({
                "id": registered_user["id"],
                "username": registered_user["username"],
                "role": registered_user["role"],
                "employee_id": registered_user.get("employee_id"),
                "source_employee_code": registered_user.get("source_employee_code"),
            })
            if registered_user.get("first_login") and request.endpoint not in {"first_login_page", "resend_first_login_otp_page", "logout", "static"}:
                return redirect(url_for("first_login_page"))
        service_owner_id = _current_data_owner_id()
        user_key = str(service_owner_id)
        services = app.config.setdefault("services_by_user", {})
        try:
            if user_key not in services:
                services[user_key] = get_service(service_owner_id)
            app.config["service"] = services[user_key]
        except Exception:
            app.config["service"] = None

    @app.before_request
    def protect_mutating_requests():
        if not app.config.get("WTF_CSRF_ENABLED"):
            return
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        expected = session.get("_csrf_token")
        if not expected or not sent or not secrets.compare_digest(str(expected), str(sent)):
            if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
                return jsonify({"error": "Invalid security token. Refresh the page and try again."}), 400
            flash("Invalid security token. Refresh the page and try again.", "danger")
            return redirect(request.referrer or url_for("login"))

    def login_required(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "user" not in session:
                return redirect(url_for("login"))
            return f(*args, **kwargs)
        return decorated

    def role_required(*roles):
        def decorator(f):
            @wraps(f)
            def decorated(*args, **kwargs):
                if "user" not in session:
                    return redirect(url_for("login"))
                user_role = session["user"].get("role")
                allowed_roles = set(roles)
                if user_role not in allowed_roles:
                    return render_template("unauthorized.html", user=session["user"]), 403
                return f(*args, **kwargs)
            return decorated
        return decorator

    @app.route("/")
    def index():
        if "user" in session:
            return redirect(url_for("dashboard"))
        return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            limited = _rate_limit("login", limit=8, minutes=15)
            if limited:
                flash(limited, "danger")
                return render_template("login.html"), 429
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            user, error = _authenticate_user(username, password)
            if user:
                if user.get("first_login"):
                    if user.get("temp_password_used"):
                        flash("Temporary password already used. Please reset your password.", "danger")
                        return redirect(url_for("forgot_password_page"))
                    user["temp_password_used"] = True
                    _save_registered_user(user)
                    demo_otp = _issue_otp(user, "first_login")
                    session["first_login_user_id"] = user["id"]
                    session["first_login_demo_otp"] = demo_otp
                    session["user"] = {
                        "id": user["id"],
                        "username": user["username"],
                        "role": user["role"],
                        "employee_id": user.get("employee_id"),
                        "source_employee_code": user.get("source_employee_code"),
                    }
                    return redirect(url_for("first_login_page"))
                session["user"] = {
                    "id": user["id"],
                    "username": user["username"],
                    "role": user["role"],
                    "employee_id": user.get("employee_id"),
                    "source_employee_code": user.get("source_employee_code"),
                }
                flash(f"Welcome, {user['username']}!", "success")
                return redirect(url_for("dashboard"))
            flash(error, "danger")
        return render_template("login.html")

    @app.route("/register", methods=["POST"])
    def register():
        flash("Public self-registration is disabled. Admin/HR must create accounts.", "warning")
        return redirect(url_for("login"))

    @app.route("/first-login", methods=["GET", "POST"])
    def first_login_page():
        user_id = session.get("first_login_user_id") or _current_user_id()
        user = _get_registered_user_by_id(user_id)
        if not user:
            flash("First-login session expired. Please sign in again.", "warning")
            return redirect(url_for("login"))
        if not user.get("first_login"):
            session.pop("first_login_user_id", None)
            session.pop("first_login_demo_otp", None)
            flash("Your account is already active.", "info")
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            limited = _rate_limit("first_login", limit=8, minutes=15)
            if limited:
                flash(limited, "danger")
                return redirect(url_for("first_login_page"))
            otp = request.form.get("otp", "").strip()
            password = request.form.get("password", "")
            confirm = request.form.get("confirm_password", "")
            try:
                if password != confirm:
                    raise ValueError("Passwords do not match.")
                if not _verify_otp(user, otp, "first_login"):
                    raise ValueError("Invalid or expired OTP.")
                _change_user_password(user, password)
                session.clear()
                flash("Password created successfully. Please sign in with your new password.", "success")
                return redirect(url_for("login"))
            except Exception as exc:
                flash(str(exc), "danger")
        return render_template(
            "first_login.html",
            user=user,
            demo_otp=session.get("first_login_demo_otp"),
            otp_expires_at=user.get("otp_expires_at"),
            is_demo=_is_development(),
        )

    @app.route("/first-login/resend-otp", methods=["GET", "POST"])
    @login_required
    def resend_first_login_otp_page():
        if request.method == "GET":
            return redirect(url_for("first_login_page"))
        limited = _rate_limit("first_login_otp", limit=5, minutes=15)
        if limited:
            flash(limited, "danger")
            return redirect(url_for("first_login_page"))
        user_id = session.get("first_login_user_id") or _current_user_id()
        user = _get_registered_user_by_id(user_id)
        if not user or not user.get("first_login"):
            session.pop("first_login_user_id", None)
            session.pop("first_login_demo_otp", None)
            flash("First-login session expired. Please sign in again.", "warning")
            return redirect(url_for("login"))
        try:
            demo_otp = _issue_otp(user, "first_login")
            session["first_login_demo_otp"] = demo_otp
            flash("New OTP generated. It is valid for 5 minutes.", "success")
        except Exception as exc:
            _audit("otp_resend_failed", target_id=user.get("id"), status="failed", details={"error": str(exc)})
            flash("Could not generate OTP. Please sign in again or ask Admin/HR to reset the account.", "danger")
        return redirect(url_for("first_login_page"))

    @app.route("/forgot-password", methods=["GET", "POST"])
    def forgot_password_page():
        demo_otp = None
        otp_expires_at = None
        if request.method == "POST":
            limited = _rate_limit("forgot_password", limit=5, minutes=15)
            if limited:
                flash(limited, "danger")
                return render_template(
                    "forgot_password.html",
                    demo_otp=None,
                    otp_expires_at=None,
                    is_demo=_is_development(),
                ), 429
            identity = request.form.get("identity", "").strip().lower()
            user = _find_password_reset_user(identity)
            if user:
                demo_otp = _issue_otp(user, "password_reset")
                otp_expires_at = user.get("otp_expires_at")
                _audit("password_reset_requested", target_id=user.get("id"))
            flash("If the company email exists, a reset OTP has been generated.", "info")
        return render_template(
            "forgot_password.html",
            demo_otp=demo_otp,
            otp_expires_at=otp_expires_at,
            is_demo=_is_development(),
        )

    @app.route("/reset-password", methods=["POST"])
    def reset_password_page():
        limited = _rate_limit("reset_password", limit=8, minutes=15)
        if limited:
            flash(limited, "danger")
            return redirect(url_for("forgot_password_page"))
        identity = request.form.get("identity", "").strip().lower()
        otp = request.form.get("otp", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        user = _find_password_reset_user(identity)
        try:
            if not user:
                raise ValueError("Invalid reset request.")
            if password != confirm:
                raise ValueError("Passwords do not match.")
            if not _verify_otp(user, otp, "password_reset"):
                raise ValueError("Invalid or expired OTP.")
            _change_user_password(user, password)
            flash("Password reset successfully. Please sign in.", "success")
            return redirect(url_for("login"))
        except Exception as exc:
            flash(str(exc), "danger")
            return redirect(url_for("forgot_password_page"))

    @app.route("/unauthorized")
    @login_required
    def unauthorized_page():
        return render_template("unauthorized.html", user=session["user"]), 403

    @app.route("/logout")
    def logout():
        session.clear()
        flash("Logged out successfully.", "info")
        return redirect(url_for("login"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        if session["user"].get("role") == "employee":
            return redirect(url_for("career_page"))
        svc = app.config.get("service")
        analytics = svc.get_analytics() if svc else {}
        upload_summary, recent_datasets, recent_jds = _safe_upload_dashboard()
        return render_template(
            "dashboard.html",
            analytics=analytics,
            upload_summary=upload_summary,
            recent_datasets=recent_datasets,
            recent_jds=recent_jds,
            projects=_safe_projects(),
            user=session["user"],
        )

    @app.route("/recommendations")
    @login_required
    @role_required("admin", "hr", "manager")
    def recommendations():
        svc = app.config.get("service")
        roles = svc.get_analytics()["roles_available"] if svc else []
        return render_template("recommendations.html", roles=roles, user=session["user"])

    @app.route("/skill-gap")
    @login_required
    def skill_gap_page():
        return redirect(url_for("search_page"))

    @app.route("/career")
    @login_required
    def career_page():
        upload_summary, _, _ = _safe_upload_dashboard()
        return render_template(
            "career.html",
            upload_summary=upload_summary,
            own_employee_id=_current_employee_dataset_id(),
            user=session["user"],
        )

    @app.route("/analytics")
    @login_required
    @role_required("admin", "hr")
    def analytics_page():
        svc = app.config.get("service")
        analytics = svc.get_analytics() if svc else {}
        return render_template("analytics.html", analytics=analytics, user=session["user"])

    @app.route("/analytics/export/excel")
    @login_required
    @role_required("admin", "hr")
    def analytics_export_excel():
        svc = app.config.get("service")
        analytics = svc.get_analytics() if svc else {}
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            pd.DataFrame([{
                "Total Employees": analytics.get("total_employees", 0),
                "Average Performance": analytics.get("avg_performance", 0),
                "Average Experience": analytics.get("avg_experience", 0),
            }]).to_excel(writer, sheet_name="Summary", index=False)
            pd.DataFrame(analytics.get("department_rows", [])).to_excel(writer, sheet_name="Departments", index=False)
            pd.DataFrame(analytics.get("top_skills", [])).to_excel(writer, sheet_name="Skills", index=False)
            pd.DataFrame(analytics.get("experience_rows", [])).to_excel(writer, sheet_name="Experience", index=False)
        output.seek(0)
        return send_file(
            output,
            as_attachment=True,
            download_name="talentbeacon_analytics.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @app.route("/analytics/export/pdf")
    @login_required
    @role_required("admin", "hr")
    def analytics_export_pdf():
        from matplotlib.backends.backend_pdf import PdfPages
        from matplotlib.figure import Figure

        svc = app.config.get("service")
        analytics = svc.get_analytics() if svc else {}
        output = BytesIO()
        with PdfPages(output) as pdf:
            fig = Figure(figsize=(8.27, 11.69))
            ax = fig.subplots()
            ax.axis("off")
            lines = [
                "TalentBeacon Workforce Analytics Report",
                "",
                f"Total Employees: {analytics.get('total_employees', 0)}",
                f"Average Performance: {analytics.get('avg_performance', 0)}/5",
                f"Average Experience: {analytics.get('avg_experience', 0)} years",
                "",
                "Department Distribution:",
            ]
            lines.extend(
                f"- {row.get('name')}: {row.get('count')} employees ({row.get('percentage')}%)"
                for row in analytics.get("department_rows", [])[:20]
            )
            lines.append("")
            lines.append("Top Skills:")
            lines.extend(
                f"- {row.get('skill')}: {row.get('count')} employees ({row.get('percentage')}%)"
                for row in analytics.get("top_skills", [])[:20]
            )
            lines.append("")
            lines.append("Experience Distribution:")
            lines.extend(
                f"- {row.get('name')}: {row.get('count')} employees ({row.get('percentage')}%)"
                for row in analytics.get("experience_rows", [])
            )
            ax.text(0.05, 0.95, "\n".join(lines), va="top", ha="left", fontsize=10, family="monospace")
            pdf.savefig(fig, bbox_inches="tight")
        output.seek(0)
        return send_file(output, as_attachment=True, download_name="talentbeacon_analytics.pdf", mimetype="application/pdf")

    @app.route("/nlp-analysis")
    @login_required
    @role_required("admin", "hr", "manager")
    def nlp_page():
        return redirect(url_for("search_page"))

    @app.route("/ml-training")
    @login_required
    @role_required("admin")
    def ml_training_page():
        metrics = {}
        registry = []
        if config.TRAINING_METRICS_PATH.exists():
            metrics = json.loads(config.TRAINING_METRICS_PATH.read_text(encoding="utf-8"))
        if getattr(config, "MODEL_REGISTRY_PATH", None) and config.MODEL_REGISTRY_PATH.exists():
            registry = json.loads(config.MODEL_REGISTRY_PATH.read_text(encoding="utf-8"))
        return render_template("ml_training.html", metrics=metrics, registry=registry, user=session["user"])

    @app.route("/admin/datasets", methods=["GET", "POST"])
    @login_required
    @role_required("admin", "hr")
    def admin_datasets_page():
        owner_id = _current_data_owner_id()
        if request.method == "POST":
            is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
            upload = request.files.get("dataset")
            if not upload or not upload.filename:
                if is_ajax:
                    return jsonify({"ok": False, "message": "Please choose a CSV or Excel dataset."}), 400
                flash("Please choose a CSV or Excel dataset.", "warning")
                return redirect(url_for("admin_datasets_page"))
            safe_name = secure_filename(upload.filename)
            upload.filename = safe_name
            try:
                result = process_dataset_upload(upload, uploaded_by=owner_id)
                account_result = _create_accounts_from_active_dataset(actor_id=owner_id)
                if account_result["accounts"]:
                    _store_generated_credentials(owner_id, account_result["accounts"])
                _refresh_talent_service(app)
                account_message = f" Created {account_result['created']} employee login accounts. Open Users to view temporary passwords."
                if is_ajax:
                    return jsonify({
                        "ok": True,
                        "message": f"Uploaded and activated {result['row_count']} employees from {safe_name}.{account_message}",
                        "redirect": url_for("admin_datasets_page"),
                    })
                flash(f"Uploaded and activated {result['row_count']} employees from {safe_name}.{account_message}", "success")
            except Exception as exc:
                if is_ajax:
                    return jsonify({"ok": False, "message": str(exc)}), 400
                flash(str(exc), "danger")
            return redirect(url_for("admin_datasets_page"))

        upload_summary, recent_datasets, _ = _safe_upload_dashboard()
        return render_template(
            "admin_datasets.html",
            upload_summary=upload_summary,
            recent_datasets=_safe_dataset_uploads(),
            user=session["user"],
        )

    @app.route("/admin/users", methods=["GET", "POST"])
    @login_required
    @role_required("admin", "hr")
    def admin_users_page():
        owner_id = _current_data_owner_id()
        page = max(_safe_int(request.args.get("page") or 1, 1), 1)
        per_page = min(max(_safe_int(request.args.get("per_page") or 100, 100), 25), 500)
        created_user = None
        generated_accounts = _consume_generated_credentials(owner_id)
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            role = request.form.get("role", "employee").strip().lower()
            try:
                created_user = _create_user_account(name, role=role, actor_id=owner_id)
                flash(f"Created {created_user['role'].upper()} account for {created_user['username']}.", "success")
            except Exception as exc:
                flash(str(exc), "danger")
        all_managed_users = _managed_users_for_actor(owner_id)
        if not all_managed_users and _active_dataset_id_for_actor(owner_id):
            try:
                account_result = _create_accounts_from_active_dataset(actor_id=owner_id)
                if account_result["accounts"]:
                    _store_generated_credentials(owner_id, account_result["accounts"])
                    generated_accounts.extend(account_result["accounts"])
                    flash(f"Prepared {account_result['created']} employee login credentials from the active uploaded file.", "success")
                    all_managed_users = _managed_users_for_actor(owner_id)
            except Exception as exc:
                flash(str(exc), "danger")
        total_managed_users = len(all_managed_users)
        start = (page - 1) * per_page
        managed_users = all_managed_users[start:start + per_page]
        return render_template(
            "admin_users.html",
            managed_users=managed_users,
            total_managed_users=total_managed_users,
            page=page,
            per_page=per_page,
            page_count=max(1, math.ceil(total_managed_users / per_page)),
            created_user=created_user,
            generated_accounts=generated_accounts,
            generated_passwords={
                str(account.get("employee_id") or ""): account.get("temporary_password")
                for account in generated_accounts
                if account.get("temporary_password")
            },
            generated_passwords_by_email={
                str(account.get("company_email") or "").lower(): account.get("temporary_password")
                for account in generated_accounts
                if account.get("temporary_password") and account.get("company_email")
            },
            user=session["user"],
            is_demo=_is_development(),
        )

    @app.route("/admin/users/from-active-dataset", methods=["POST"])
    @login_required
    @role_required("admin", "hr")
    def admin_users_from_dataset_page():
        owner_id = _current_data_owner_id()
        try:
            page = max(_safe_int(request.args.get("page") or 1, 1), 1)
            per_page = min(max(_safe_int(request.args.get("per_page") or 100, 100), 25), 500)
            result = _create_accounts_from_active_dataset(actor_id=owner_id)
            if not result["accounts"]:
                result = _reset_visible_pending_accounts(owner_id, page=page, per_page=per_page)
                flash(f"Prepared {result.get('reset', 0)} fresh pending employee login credentials for this page. {result['skipped']} completed accounts were kept.", "success")
            else:
                flash(f"Prepared {result.get('created', 0)} new and {result.get('reset', 0)} reset employee login credentials from the active uploaded file.", "success")
            if result["accounts"]:
                _store_generated_credentials(owner_id, result["accounts"])
        except Exception as exc:
            flash(str(exc), "danger")
        return redirect(url_for("admin_users_page", page=request.args.get("page", 1), per_page=request.args.get("per_page", 100)))

    @app.route("/admin/users/<int:user_id>/role", methods=["POST"])
    @login_required
    @role_required("admin", "hr")
    def admin_user_role_page(user_id):
        try:
            _change_user_role(user_id, request.form.get("role", ""), actor_id=_current_user_id())
            flash("User role updated.", "success")
        except Exception as exc:
            flash(str(exc), "danger")
        return redirect(url_for("admin_users_page"))

    @app.route("/admin/datasets/<upload_id>/activate", methods=["POST"])
    @login_required
    @role_required("admin", "hr")
    def activate_dataset_page(upload_id):
        try:
            upload = activate_dataset(upload_id, user_id=_current_data_owner_id())
            _refresh_talent_service(app)
            flash(f"{upload['filename']} is now the active dataset.", "success")
        except Exception as exc:
            flash(str(exc), "danger")
        return redirect(url_for("admin_datasets_page"))

    @app.route("/admin/datasets/<upload_id>/delete", methods=["POST"])
    @login_required
    @role_required("admin", "hr")
    def delete_dataset_page(upload_id):
        try:
            upload = delete_dataset(upload_id, user_id=_current_data_owner_id())
            _refresh_talent_service(app)
            flash(f"Deleted {upload['filename']} from uploads and database metadata.", "info")
        except Exception as exc:
            flash(str(exc), "danger")
        return redirect(url_for("admin_datasets_page"))

    @app.route("/manager/jd-matching", methods=["GET", "POST"])
    @login_required
    @role_required("admin", "manager")
    def jd_matching_page():
        if request.method == "POST" and request.files.get("jd_pdf"):
            upload = request.files.get("jd_pdf")
            if not upload or not upload.filename:
                flash("Please choose a JD PDF.", "warning")
                return redirect(url_for("jd_matching_page"))
            safe_name = secure_filename(upload.filename)
            upload.filename = safe_name
            try:
                latest_result = process_jd_upload(upload, uploaded_by=session["user"]["id"])
                flash(f"Processed {safe_name} and generated candidate matches.", "success")
                return redirect(url_for("jd_results_page", jd_upload_id=latest_result["jd_upload_id"]))
            except Exception as exc:
                flash(str(exc), "danger")
                return redirect(url_for("jd_matching_page"))

        upload_summary, _, recent_jds = _safe_upload_dashboard()
        return render_template(
            "projects.html",
            upload_summary=upload_summary,
            recent_jds=recent_jds,
            edit_project=None,
            projects=list_projects(user_id=_current_user_id()),
            user=session["user"],
        )

    @app.route("/manager/projects", methods=["GET", "POST"])
    @login_required
    @role_required("admin", "manager")
    def projects_page():
        if request.method == "POST":
            try:
                project_id = save_project_from_form(request.form, created_by=session["user"]["id"])
                flash("Project saved. You can now run matching.", "success")
                return redirect(url_for("project_matches_page", project_id=project_id))
            except Exception as exc:
                flash(str(exc), "danger")
        upload_summary, _, _ = _safe_upload_dashboard()
        return render_template(
            "projects.html",
            projects=list_projects(user_id=_current_user_id()),
            upload_summary=upload_summary,
            edit_project=None,
            user=session["user"],
        )

    @app.route("/manager/projects/from-document", methods=["POST"])
    @login_required
    @role_required("admin", "manager")
    def project_from_document_page():
        upload = request.files.get("project_doc")
        if not upload or not upload.filename:
            flash("Please choose a project PDF, DOC, DOCX, or TXT file.", "warning")
            return redirect(url_for("projects_page"))
        safe_name = secure_filename(upload.filename)
        upload.filename = safe_name
        try:
            extracted = project_requirements_from_document(upload, user_id=_current_user_id())
            form_data = {
                "name": request.form.get("name") or extracted.get("suggested_name") or safe_name,
                "description": extracted.get("description", ""),
                "required_skills": "; ".join(extracted.get("skills", [])),
                "min_experience": extracted.get("min_experience", 0),
                "source_filename": extracted.get("source_filename", safe_name),
                "source_path": extracted.get("source_path", ""),
                "source_hash": extracted.get("source_hash", ""),
            }
            project_id = save_project_from_form(form_data, created_by=session["user"]["id"])
            matches = match_project(project_id, user_id=_current_user_id())
            extracted_skills = ", ".join(extracted.get("skills", [])) or "no named skills"
            flash(
                f"Extracted {extracted_skills} from {safe_name} and found {len(matches)} matching employees.",
                "success",
            )
            return redirect(url_for("project_matches_page", project_id=project_id))
        except Exception as exc:
            flash(str(exc), "danger")
            return redirect(url_for("projects_page"))

    @app.route("/manager/projects/<project_id>/edit", methods=["GET", "POST"])
    @login_required
    @role_required("admin", "manager")
    def project_edit_page(project_id):
        if request.method == "POST":
            try:
                save_project_from_form(request.form, project_id=project_id, created_by=_current_user_id())
                flash("Project updated.", "success")
                return redirect(url_for("projects_page"))
            except Exception as exc:
                flash(str(exc), "danger")
        upload_summary, _, _ = _safe_upload_dashboard()
        return render_template(
            "projects.html",
            projects=list_projects(user_id=_current_user_id()),
            upload_summary=upload_summary,
            edit_project=project_detail(project_id, user_id=_current_user_id()),
            user=session["user"],
        )

    @app.route("/manager/projects/<project_id>/delete", methods=["POST"])
    @login_required
    @role_required("admin", "manager")
    def project_delete(project_id):
        try:
            remove_project(project_id, user_id=_current_user_id())
            flash("Project deleted.", "info")
        except Exception as exc:
            flash(str(exc), "danger")
        return redirect(url_for("projects_page"))

    @app.route("/manager/projects/<project_id>/match", methods=["GET", "POST"])
    @login_required
    @role_required("admin", "manager")
    def project_matches_page(project_id):
        if request.method == "POST":
            try:
                project = project_detail(project_id, user_id=_current_user_id())
                if project and project.get("source_path"):
                    extracted = refresh_project_from_source(project_id, user_id=_current_user_id())
                    extracted_skills = ", ".join(extracted.get("skills", [])) or "no named skills"
                    flash(f"Re-analyzed source document and extracted {extracted_skills}.", "info")
                match_project(project_id, user_id=_current_user_id())
                flash("Project matching completed using uploaded employee data.", "success")
            except Exception as exc:
                flash(str(exc), "danger")
        return render_template(
            "project_results.html",
            project=project_detail(project_id, user_id=_current_user_id()),
            project_id=project_id,
            matches=get_project_matches(project_id, user_id=_current_user_id()),
            user=session["user"],
        )

    @app.route("/manager/jd-matching/<int:jd_upload_id>")
    @login_required
    @role_required("admin", "manager")
    def jd_results_page(jd_upload_id):
        try:
            matches = get_jd_matches(jd_upload_id)
        except Exception as exc:
            flash(f"Unable to load matches: {exc}", "danger")
            matches = []
        return render_template(
            "jd_results.html",
            jd_upload_id=jd_upload_id,
            matches=matches,
            user=session["user"],
        )

    @app.route("/search")
    @login_required
    @role_required("admin", "hr", "manager")
    def search_page():
        svc = _get_talent_service(app)
        depts = list(svc.df["Department"].unique()) if svc else []
        roles = svc.get_analytics()["roles_available"] if svc else []
        return render_template(
            "search.html",
            departments=depts,
            roles=roles,
            projects=list_projects(user_id=_current_user_id()),
            user=session["user"],
        )

    # ---- API Routes ----

    @app.route("/api/match/role/<role_name>")
    @login_required
    @role_required("admin", "manager")
    def api_match_role(role_name):
        svc = app.config.get("service")
        limit = request.args.get("limit", 10, type=int)
        results = svc.match_employees_to_role(role_name.replace("-", " "), limit=limit)
        return jsonify({"role": role_name, "recommendations": results})

    @app.route("/api/match/project", methods=["POST"])
    @login_required
    @role_required("admin", "manager")
    def api_match_project():
        svc = app.config.get("service")
        data = request.get_json() or {}
        skills = data.get("skills", [])
        min_exp = data.get("min_experience", 0)
        results = svc.match_employees_to_project(skills, min_experience=min_exp)
        return jsonify({"recommendations": results})

    @app.route("/api/nlp/parse", methods=["POST"])
    @login_required
    @role_required("admin", "hr", "manager")
    def api_nlp_parse():
        svc = _get_talent_service(app)
        if not svc:
            return jsonify({"error": "Upload and activate an employee file first."}), 400
        text = (request.get_json() or {}).get("text", "")
        parsed = svc.parse_requirements_nlp(text)
        matches = []
        if parsed.get("skills"):
            matches = svc.match_employees_to_project(
                parsed.get("skills", []),
                min_experience=parsed.get("min_experience", 0),
                certifications=parsed.get("certifications", []),
                limit=5,
            )
        parsed["matches"] = matches
        return jsonify(parsed)

    @app.route("/api/skill-gap/<int:employee_id>/<role_name>")
    @login_required
    def api_skill_gap(employee_id, role_name):
        if not _can_access_employee_record(employee_id):
            return jsonify({"error": "Unauthorized"}), 403
        svc = app.config.get("service")
        gap = svc.get_skill_gap(employee_id, role_name.replace("-", " "))
        return jsonify(gap or {"error": "Not found"})

    @app.route("/api/readiness/<int:employee_id>/<role_name>")
    @login_required
    def api_readiness(employee_id, role_name):
        if not _can_access_employee_record(employee_id):
            return jsonify({"error": "Unauthorized"}), 403
        svc = app.config.get("service")
        result = svc.get_readiness_score(employee_id, role_name.replace("-", " "))
        return jsonify(result or {"error": "Not found"})

    @app.route("/api/career/<int:employee_id>")
    @login_required
    def api_career(employee_id):
        if not _can_access_employee_record(employee_id):
            return jsonify({"error": "Unauthorized"}), 403
        svc = app.config.get("service")
        paths = svc.get_career_paths(employee_id)
        return jsonify({"career_paths": paths})

    @app.route("/api/search")
    @login_required
    @role_required("admin", "hr", "manager")
    def api_search():
        svc = _get_talent_service(app)
        if not svc:
            return jsonify({"error": "Upload and activate an employee file first."}), 400
        skill = request.args.get("skill")
        dept = request.args.get("department")
        min_perf = request.args.get("min_performance", 0, type=int)
        role_name = request.args.get("role_name")
        project_id = request.args.get("project_id")
        combined_skills = split_skills(skill)
        role_required = _role_required_skills(role_name)
        combined_skills.extend(role_required)
        project = project_detail(project_id, user_id=_current_user_id()) if project_id else None
        if project:
            combined_skills.extend(split_skills(project.get("required_skills", "")))
        skill_query = ", ".join(dict.fromkeys([s for s in combined_skills if str(s).strip()]))
        results = svc.search_employees(skill=skill, department=dept, min_performance=min_perf)
        if skill_query != (skill or ""):
            results = svc.search_employees(skill=skill_query, department=dept, min_performance=min_perf)
        return jsonify({
            "results": results[:30],
            "required_skills": split_skills(skill_query),
            "role_required_skills": role_required,
            "project_required_skills": split_skills(project.get("required_skills", "")) if project else [],
        })

    @app.route("/api/employee/<int:employee_id>/intelligence")
    @login_required
    def api_employee_intelligence(employee_id):
        role = session["user"].get("role")
        if not _can_access_employee_record(employee_id):
            return jsonify({"error": "Unauthorized"}), 403
        if role not in {"admin", "hr", "manager", "employee"}:
            return jsonify({"error": "Unauthorized"}), 403
        svc = app.config.get("service")
        role_name = request.args.get("role_name")
        project_id = request.args.get("project_id")
        project = project_detail(project_id, user_id=_current_user_id()) if project_id else None
        detail = svc.get_employee_intelligence(
            employee_id,
            role_name=role_name,
            project_skills=split_skills(project.get("required_skills", "")) if project else [],
            project_min_experience=project.get("min_experience", 0) if project else 0,
            query_skills=request.args.get("skill"),
        )
        if not detail:
            return jsonify({"error": "Employee not found in the active uploaded file."}), 404
        if project:
            project_matches = get_project_matches(project_id, user_id=_current_user_id())
            selected_match = next(
                (item for item in project_matches if str(item.get("employee_id")) == str(employee_id)),
                {},
            )
            detail["project"] = {
                "id": project.get("id"),
                "name": project.get("name"),
                "required_skills": split_skills(project.get("required_skills", "")),
                "min_experience": int(project.get("min_experience") or 0),
            }
            detail["project_match_breakdown"] = selected_match.get("score_breakdown", {})
        return jsonify(detail)

    @app.route("/api/analytics")
    @login_required
    @role_required("admin", "hr")
    def api_analytics():
        svc = app.config.get("service")
        return jsonify(svc.get_analytics())

    @app.route("/api/admin/datasets")
    @login_required
    @role_required("admin", "hr")
    def api_admin_datasets():
        try:
            upload_summary, _, _ = _safe_upload_dashboard()
            return jsonify({
                "summary": upload_summary,
                "files": list_dataset_uploads(user_id=_current_user_id()),
            })
        except Exception as exc:
            return jsonify({"error": str(exc), "files": []}), 500

    @app.route("/api/jd-matches/<int:jd_upload_id>")
    @login_required
    @role_required("admin", "manager")
    def api_jd_matches(jd_upload_id):
        try:
            matches = get_jd_matches(jd_upload_id)
        except Exception as exc:
            return jsonify({"matches": [], "error": str(exc)}), 500
        search = (request.args.get("search") or "").lower().strip()
        min_score = request.args.get("min_score", 0, type=float)
        skill = (request.args.get("skill") or "").lower().strip()
        sort_by = request.args.get("sort_by", "match_score")
        direction = request.args.get("direction", "desc")

        if search:
            matches = [
                m for m in matches
                if search in " ".join([
                    str(m.get("name") or ""),
                    str(m.get("email") or ""),
                    str(m.get("education_level") or ""),
                    str(m.get("skills") or ""),
                ]).lower()
            ]
        if skill:
            matches = [m for m in matches if _skill_filter_match(m.get("skills"), skill)]
        if min_score:
            matches = [m for m in matches if float(m.get("match_score") or 0) >= min_score]

        reverse = direction != "asc"
        allowed_sort = {"match_score", "name", "years_of_experience", "education_level"}
        sort_key = sort_by if sort_by in allowed_sort else "match_score"
        matches = sorted(matches, key=lambda item: item.get(sort_key) or 0, reverse=reverse)
        return jsonify({"matches": matches})

    @app.route("/api/project-matches/<project_id>")
    @login_required
    @role_required("admin", "manager")
    def api_project_matches(project_id):
        try:
            matches = get_project_matches(project_id, user_id=_current_user_id())
        except Exception as exc:
            return jsonify({"matches": [], "error": str(exc)}), 500
        search = (request.args.get("search") or "").lower().strip()
        min_score = request.args.get("min_score", 0, type=float)
        skill = (request.args.get("skill") or "").lower().strip()
        sort_by = request.args.get("sort_by", "match_score")
        page = max(request.args.get("page", 1, type=int), 1)
        page_size = min(max(request.args.get("page_size", 50, type=int), 10), 100)
        if search:
            matches = [
                m for m in matches
                if search in " ".join([
                    str(m.get("name") or ""),
                    str(m.get("email") or ""),
                    str(m.get("education_level") or ""),
                    str(m.get("skills") or ""),
                ]).lower()
            ]
        if skill:
            matches = [m for m in matches if _skill_filter_match(m.get("skills"), skill)]
        if min_score:
            matches = [m for m in matches if float(m.get("match_score") or 0) >= min_score]
        allowed_sort = {"match_score", "name", "years_of_experience", "education_level"}
        sort_key = sort_by if sort_by in allowed_sort else "match_score"
        matches = sorted(matches, key=lambda item: item.get(sort_key) or 0, reverse=True)
        total = len(matches)
        start = (page - 1) * page_size
        return jsonify({
            "matches": matches[start:start + page_size],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size),
        })

    return app


def _safe_upload_dashboard():
    try:
        return dashboard_upload_summary(user_id=_current_data_owner_id())
    except Exception:
        return {}, [], []


def _safe_projects():
    try:
        return list_projects(user_id=_current_user_id())
    except Exception:
        return []


def _safe_dataset_uploads():
    try:
        return list_dataset_uploads(user_id=_current_data_owner_id())
    except Exception:
        return []


def _active_dataset_id_for_actor(actor_id):
    try:
        active = get_active_dataset(user_id=actor_id)
        return active.get("id") if active else None
    except Exception:
        return None


def _refresh_talent_service(app):
    user_id = _current_data_owner_id()
    user_key = str(user_id)
    services = app.config.setdefault("services_by_user", {})
    try:
        services[user_key] = reload_service(user_id)
        app.config["service"] = services[user_key]
    except Exception:
        services.pop(user_key, None)
        app.config.pop("service", None)


def _get_talent_service(app):
    svc = app.config.get("service")
    df = getattr(svc, "df", None)
    if svc is None or getattr(df, "empty", True):
        _refresh_talent_service(app)
        svc = app.config.get("service")
    return svc


def _current_user_id():
    return session.get("user", {}).get("id") if "user" in session else None


def _current_data_owner_id():
    if "user" not in session:
        return None
    role = session["user"].get("role")
    if role == "hr":
        return 1
    if role in {"employee", "hr"}:
        registered_user = _get_registered_user_by_id(session["user"].get("id"))
        if registered_user and registered_user.get("created_by"):
            return registered_user.get("created_by")
        return (registered_user or {}).get("created_by") or session["user"].get("id")
    return session["user"].get("id")


def _current_employee_dataset_id():
    user = session.get("user", {}) if "user" in session else {}
    registered_user = _get_registered_user_by_id(user.get("id"))
    for value in (
        user.get("source_employee_code"),
        (registered_user or {}).get("source_employee_code"),
        user.get("source_employee_key"),
        (registered_user or {}).get("source_employee_key"),
    ):
        row_id = _dataset_row_id_from_source(value)
        if row_id is not None:
            return row_id
    employee_id = str(user.get("employee_id") or "").strip()
    if employee_id.isdigit():
        return int(employee_id)
    return None


def _dataset_row_id_from_source(value):
    text = str(value or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    for pattern in (r":row:(\d+)$", r":(\d+)$"):
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    return None


def _can_access_employee_record(employee_id):
    role = session.get("user", {}).get("role") if "user" in session else None
    if role in {"admin", "hr", "manager"}:
        return True
    if role != "employee":
        return False
    return _current_employee_dataset_id() == int(employee_id)


def _skill_filter_match(skills_text, query):
    return contains_all_skills(split_skills(skills_text), split_skills(query))


def _role_required_skills(role_name):
    if not role_name:
        return []
    try:
        from database.seed import ROLE_DEFINITIONS
        spec = ROLE_DEFINITIONS.get(role_name)
        return list(spec.get("required", [])) if spec else []
    except Exception:
        return []


REGISTERED_USERS_PATH = config.BASE_DIR / "workspace_data" / "registered_users.json"
AUDIT_LOG_PATH = config.BASE_DIR / "workspace_data" / "audit_logs.jsonl"
GENERATED_CREDENTIALS_PATH = config.BASE_DIR / "workspace_data" / "generated_employee_credentials.json"
APP_ENV = os.environ.get("APP_ENV") or os.environ.get("NODE_ENV") or "development"
ALLOWED_ACCOUNT_ROLES = {"admin", "hr", "manager", "employee"}
LOCK_AFTER_ATTEMPTS = 5
LOCK_MINUTES = 15
OTP_MINUTES = 5
TEMP_PASSWORD_HOURS = 36


def _now():
    return datetime.now(timezone.utc)


def _to_iso(value):
    return value.astimezone(timezone.utc).isoformat()


def _from_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _safe_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        match = re.search(r"\d+", str(value or ""))
        return int(match.group()) if match else default


def _is_development():
    return APP_ENV.lower() in {"development", "dev", "local", "demo"}


def _rate_limit(bucket, limit=10, minutes=15):
    if not getattr(config, "RATE_LIMIT_ENABLED", True):
        return None
    try:
        app = create_app.__globals__.get("current_app")
    except Exception:
        app = None
    # Import here to keep test imports simple and avoid circular Flask globals.
    try:
        from flask import current_app
        store = current_app.config.setdefault("rate_limit_buckets", {})
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "local").split(",")[0].strip()
        key = f"{bucket}:{ip}"
        now = _now()
        window_start = now - timedelta(minutes=minutes)
        hits = [
            stamp for stamp in store.get(key, [])
            if _from_iso(stamp) and _from_iso(stamp) > window_start
        ]
        if len(hits) >= limit:
            return "Too many attempts. Please wait a few minutes and try again."
        hits.append(_to_iso(now))
        store[key] = hits
    except Exception:
        return None
    return None


def _hash_secret(value, rounds=8):
    return bcrypt.hashpw(str(value).encode("utf-8"), bcrypt.gensalt(rounds=rounds)).decode("utf-8")


def _check_secret(value, hashed):
    if not hashed:
        return False
    if str(hashed).startswith("$2"):
        return bcrypt.checkpw(str(value).encode("utf-8"), str(hashed).encode("utf-8"))
    return check_password_hash(hashed, value)


def _random_password(length=14):
    # Avoid characters such as "*" and "\" because they are easy to misread or
    # get escaped when users copy passwords through chat, docs, or Markdown.
    alphabet = string.ascii_letters + string.digits + "!@#$%&"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if _strong_password(password):
            return password


def _random_otp():
    return f"{secrets.randbelow(1000000):06d}"


def _strong_password(password):
    return (
        len(password or "") >= 8
        and re.search(r"[A-Z]", password or "")
        and re.search(r"[a-z]", password or "")
        and re.search(r"\d", password or "")
        and re.search(r"[^A-Za-z0-9]", password or "")
    )


def _audit(action, actor_id=None, target_id=None, status="ok", details=None):
    record = {
        "timestamp": _to_iso(_now()),
        "action": action,
        "actor_id": actor_id,
        "target_id": target_id,
        "status": status,
        "details": details or {},
    }
    try:
        from src.db.repository import write_audit_log
        write_audit_log(action, actor_id=actor_id, target_id=target_id, status=status, details=details or {})
    except Exception:
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")


def _save_registered_user(updated_user):
    if _sync_user_account_to_mysql(updated_user):
        return updated_user
    users = _load_registered_users_from_json()
    for index, user in enumerate(users):
        if int(user.get("id")) == int(updated_user.get("id")):
            users[index] = updated_user
            if _is_development():
                _write_registered_users_json(users)
            return updated_user
    users.append(updated_user)
    if _is_development():
        _write_registered_users_json(users)
    return updated_user


def _get_registered_user_by_id(user_id):
    privileged_json_user = _get_json_user_by_id(user_id, privileged_only=True)
    if privileged_json_user:
        return privileged_json_user
    try:
        from src.db.repository import get_user_account_by_id
        user = get_user_account_by_id(user_id)
        if user:
            return _normalize_user_record(user)
    except Exception:
        pass
    for user in _load_registered_users():
        if str(user.get("id")) == str(user_id):
            return user
    return None


def _authenticate_registered_user(local_user, password):
    locked_until = _from_iso(local_user.get("locked_until"))
    if locked_until and locked_until > _now():
        _audit("login_failed", target_id=local_user.get("id"), status="locked", details={"reason": "account_locked"})
        return None, "Account locked. Please try again later or reset your password."
    if _check_secret(password, local_user["password_hash"]):
        temp_expires = _from_iso(local_user.get("temp_password_expires_at"))
        if temp_expires and temp_expires < _now() and local_user.get("first_login"):
            local_user["temp_password_expires_at"] = _to_iso(_now() + timedelta(minutes=OTP_MINUTES))
            _audit("temp_password_grace_login", target_id=local_user.get("id"), details={"reason": "correct_expired_temp_password"})
        local_user["failed_attempts"] = 0
        local_user["locked_until"] = None
        _save_registered_user(local_user)
        _audit("login_success", target_id=local_user.get("id"))
        return local_user, None
    failed = int(local_user.get("failed_attempts") or 0) + 1
    local_user["failed_attempts"] = failed
    if failed >= LOCK_AFTER_ATTEMPTS:
        local_user["locked_until"] = _to_iso(_now() + timedelta(minutes=LOCK_MINUTES))
        _audit("account_locked", target_id=local_user.get("id"), status="locked", details={"failed_attempts": failed})
    _save_registered_user(local_user)
    _audit("login_failed", target_id=local_user.get("id"), status="failed", details={"failed_attempts": failed})
    return None, "Incorrect password."


def _authenticate_user(username, password):
    """Try reset/created local users first, then DB auth, then demo credentials."""
    if not username:
        return None, "Incorrect username."
    identity = str(username or "").strip().lower()
    privileged_json_user = _get_json_user_by_identity(identity, privileged_only=True)
    if privileged_json_user and _check_secret(password, privileged_json_user.get("password_hash")):
        return _authenticate_registered_user(privileged_json_user, password)

    local_user = _get_registered_user(username)
    if local_user:
        authenticated_user, error = _authenticate_registered_user(local_user, password)
        if authenticated_user:
            return authenticated_user, None
        if privileged_json_user and privileged_json_user.get("id") != local_user.get("id"):
            return _authenticate_registered_user(privileged_json_user, password)
        return None, error

    found_user = None
    try:
        from src.db.repository import get_user_by_username
        found_user = get_user_by_username(username)
    except Exception:
        pass
    if found_user:
        if _check_secret(password, found_user["password_hash"]):
            return found_user, None
        return None, "Incorrect password."

    demo_users = _demo_user_definitions()
    user = demo_users.get(username)
    if user:
        if user["password"] == password:
            _audit("login_success", target_id=user.get("id"), details={"demo": True})
            return user, None
        _audit("login_failed", target_id=user.get("id"), status="failed", details={"demo": True})
        return None, "Incorrect password."
    _audit("login_failed", status="failed", details={"identity": username})
    return None, "Incorrect username."


def _normalize_user_record(user):
    if not user:
        return user
    user = dict(user)
    if "company_email" not in user or not user.get("company_email"):
        user["company_email"] = user.get("email")
    if "employee_id" not in user or not user.get("employee_id"):
        user["employee_id"] = user.get("employee_login_id")
    for key in (
        "first_login",
        "temp_password_used",
        "created_from_upload",
        "created_from_demo",
        "account_created",
        "otp_used",
        "name_from_file",
    ):
        user[key] = bool(user.get(key))
    user["failed_attempts"] = int(user.get("failed_attempts") or 0)
    if "account_created" not in user:
        user["account_created"] = not bool(user.get("first_login"))
    user["account_status"] = user.get("account_status") or ("created" if user.get("account_created") else "pending_setup")
    return user


def _load_registered_users_from_mysql():
    try:
        from src.db.repository import get_user_accounts
        return [_normalize_user_record(user) for user in get_user_accounts()]
    except Exception:
        return []


def _load_registered_users_from_json():
    try:
        if REGISTERED_USERS_PATH.exists():
            users = json.loads(REGISTERED_USERS_PATH.read_text(encoding="utf-8-sig"))
            if isinstance(users, dict):
                users = [users]
            changed = False
            for user in users:
                if "company_email" not in user:
                    user["company_email"] = user.get("email")
                    changed = True
                if "first_login" not in user:
                    user["first_login"] = False
                    changed = True
                if "failed_attempts" not in user:
                    user["failed_attempts"] = 0
                    changed = True
                if "locked_until" not in user:
                    user["locked_until"] = None
                    changed = True
                if user.get("created_from_upload") and "source_employee_key" not in user:
                    key = _user_employee_identity_key(user)
                    if key:
                        user["source_employee_key"] = key
                        changed = True
                expected_created = not bool(user.get("first_login"))
                if user.get("account_created") != expected_created:
                    user["account_created"] = expected_created
                    changed = True
                expected_status = "created" if expected_created else "pending_setup"
                if user.get("account_status") != expected_status:
                    user["account_status"] = expected_status
                    changed = True
            if changed:
                _save_registered_users(users)
            return users
    except Exception:
        pass
    return []


def _read_registered_users_json_raw():
    try:
        if REGISTERED_USERS_PATH.exists():
            users = json.loads(REGISTERED_USERS_PATH.read_text(encoding="utf-8-sig"))
            return users if isinstance(users, list) else [users]
    except Exception:
        pass
    return []


def _get_json_user_by_id(user_id, privileged_only=False):
    for user in _read_registered_users_json_raw():
        if str(user.get("id")) != str(user_id):
            continue
        normalized = _normalize_user_record(user)
        if privileged_only and str(normalized.get("role") or "").lower() not in {"admin", "hr", "manager"}:
            continue
        return normalized
    return None


def _get_json_user_by_identity(identity, privileged_only=False):
    identity = str(identity or "").strip().lower()
    if not identity:
        return None
    matches = []
    for user in _read_registered_users_json_raw():
        normalized = _normalize_user_record(user)
        if privileged_only and str(normalized.get("role") or "").lower() not in {"admin", "hr", "manager"}:
            continue
        if (
            str(normalized.get("username") or "").lower() == identity
            or str(normalized.get("email") or "").lower() == identity
            or str(normalized.get("company_email") or "").lower() == identity
            or str(normalized.get("employee_login_id") or "").lower() == identity
            or str(normalized.get("employee_id") or "").lower() == identity
        ):
            matches.append(normalized)
    if not matches:
        return None
    matches.sort(
        key=lambda user: (
            0 if str(user.get("username") or "").lower() == identity else 1,
            0 if str(user.get("role") or "").lower() in {"admin", "hr", "manager"} else 1,
            bool(user.get("first_login")),
            str(user.get("created_at") or ""),
        )
    )
    return matches[0]


def _load_registered_users():
    mysql_users = _load_registered_users_from_mysql()
    json_users = _load_registered_users_from_json()
    merged = {}

    def keys_for(user):
        keys = []
        for key in ("id", "username", "email", "company_email", "employee_login_id", "employee_id"):
            value = str(user.get(key) or "").strip().lower()
            if value:
                keys.append(f"{key}:{value}")
        return keys

    for user in mysql_users:
        normalized = _normalize_user_record(user)
        primary = f"id:{normalized.get('id')}"
        merged[primary] = normalized
        for key in keys_for(normalized):
            merged.setdefault(key, normalized)
    for user in json_users:
        normalized = _normalize_user_record(user)
        role = str(normalized.get("role") or "").lower()
        is_privileged = role in {"admin", "hr", "manager"} or str(normalized.get("username") or "").lower() in {"admin", "hr", "manager"}
        primary = f"id:{normalized.get('id')}"
        existing = merged.get(primary)
        if existing is None or is_privileged:
            merged[primary] = normalized
        for key in keys_for(normalized):
            existing = merged.get(key)
            if existing is None or is_privileged:
                merged[key] = normalized

    seen = set()
    users = []
    for user in merged.values():
        unique = str(user.get("id") or user.get("email") or user.get("username"))
        if unique in seen:
            continue
        seen.add(unique)
        users.append(user)
    return users


def _save_registered_users(users):
    synced = _sync_user_accounts_to_mysql(users)
    if _is_development() and not synced:
        _write_registered_users_json(users)


def _write_registered_users_json(users):
    try:
        REGISTERED_USERS_PATH.parent.mkdir(parents=True, exist_ok=True)
        REGISTERED_USERS_PATH.write_text(json.dumps(users, indent=2, default=str), encoding="utf-8")
        return True
    except OSError as exc:
        _audit(
            "registered_user_json_write_failed",
            status="failed",
            details={"error": str(exc), "path": str(REGISTERED_USERS_PATH)},
        )
        return False


def _sync_user_account_to_mysql(user):
    try:
        from src.db.repository import upsert_user_account

        upsert_user_account(user)
        return True
    except Exception:
        return False


def _sync_user_accounts_to_mysql(users):
    try:
        from src.db.repository import upsert_user_accounts

        upsert_user_accounts(users)
        return True
    except Exception:
        return False


def _credential_bucket_key(actor_id):
    return str(actor_id or "global")


def _load_generated_credentials():
    try:
        if GENERATED_CREDENTIALS_PATH.exists():
            data = json.loads(GENERATED_CREDENTIALS_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _save_generated_credentials(data):
    GENERATED_CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    GENERATED_CREDENTIALS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _store_generated_credentials(actor_id, accounts):
    data = _load_generated_credentials()
    data[_credential_bucket_key(actor_id)] = {
        "created_at": _to_iso(_now()),
        "accounts": accounts,
    }
    _save_generated_credentials(data)


def _consume_generated_credentials(actor_id):
    data = _load_generated_credentials()
    bucket = data.pop(_credential_bucket_key(actor_id), None)
    if bucket is None and actor_id is None:
        bucket = data.pop("global", None)
    if bucket is not None:
        _save_generated_credentials(data)
    return (bucket or {}).get("accounts", [])


def _get_registered_user(identity):
    identity = str(identity or "").strip().lower()
    try:
        from src.db.repository import get_user_by_username
        user = get_user_by_username(identity)
        if user:
            normalized = _normalize_user_record(user)
            if str(normalized.get("role") or "").lower() in {"admin", "hr", "manager"}:
                return normalized
            db_user = normalized
        else:
            db_user = None
    except Exception:
        db_user = None
    privileged_json_user = _get_json_user_by_identity(identity, privileged_only=True)
    if privileged_json_user:
        _sync_user_account_to_mysql(privileged_json_user)
        return privileged_json_user
    return db_user or _get_json_user_by_identity(identity)


def _demo_user_definitions():
    return {
        "admin": {"id": 1, "username": "admin", "role": "admin", "employee_id": None, "password": "admin123", "email": "admin@talentbeacon.local"},
        "manager": {"id": -102, "username": "manager", "role": "manager", "employee_id": None, "password": "manager123", "email": "manager@talentbeacon.local"},
        "hr": {"id": -104, "username": "hr", "role": "hr", "employee_id": None, "password": "hr123", "email": "hr@talentbeacon.local"},
        "employee": {"id": -103, "username": "employee", "role": "employee", "employee_id": 1, "password": "employee123", "email": "employee@talentbeacon.local"},
    }


def _ensure_resettable_demo_user(identity):
    identity = str(identity or "").strip().lower()
    demo = next(
        (
            item for item in _demo_user_definitions().values()
            if identity in {item["username"], item["email"]}
        ),
        None,
    )
    if not demo:
        return None
    existing = _get_registered_user(demo["username"]) or _get_registered_user(demo["email"])
    if existing:
        return existing
    user = {
        "id": demo["id"],
        "employee_id": demo.get("employee_id"),
        "username": demo["username"],
        "email": demo["email"],
        "company_email": demo["email"],
        "password_hash": _hash_secret(demo["password"]),
        "role": demo["role"],
        "first_login": False,
        "temp_password_used": True,
        "temp_password_expires_at": None,
        "failed_attempts": 0,
        "locked_until": None,
        "created_by": None,
        "created_at": _to_iso(_now()),
        "created_from_demo": True,
    }
    _save_registered_user(user)
    return user


def _find_password_reset_user(identity):
    return _get_registered_user(identity) or _ensure_resettable_demo_user(identity)


def _managed_users_for_actor(actor_id):
    active_dataset_id = _active_dataset_id_for_actor(actor_id)
    active_file_hash = _active_dataset_hash_for_actor(actor_id)
    if not active_dataset_id and not active_file_hash:
        return []
    users = _load_registered_users()
    upload_users = [
        user for user in users
        if user.get("created_from_upload")
    ]
    active_dataset_users = [
        user for user in upload_users
        if (
            active_dataset_id
            and str(user.get("source_dataset_id") or "") == str(active_dataset_id)
        )
        or (
            active_file_hash
            and str(user.get("source_file_hash") or "") == str(active_file_hash)
        )
    ]
    owned_users = [
        user for user in active_dataset_users
        if str(user.get("created_by")) == str(actor_id)
    ]
    if not owned_users:
        owned_users = active_dataset_users
    if not owned_users and active_file_hash:
        owned_users = [
            user for user in upload_users
            if str(user.get("created_by")) == str(actor_id)
            and str(user.get("source_file_hash") or "") == str(active_file_hash)
        ]
    owned_users.sort(key=lambda user: (_employee_number_sort_key(user.get("employee_id")), str(user.get("created_at") or "")))
    return owned_users


def _reset_visible_pending_accounts(actor_id, page=1, per_page=100):
    users = _managed_users_for_actor(actor_id)
    start = (max(page, 1) - 1) * per_page
    visible_users = users[start:start + per_page]
    reset_accounts = []
    skipped = 0
    for user in visible_users:
        if not user.get("first_login"):
            skipped += 1
            continue
        temporary_password = _random_password()
        user["password_hash"] = _hash_secret(temporary_password, rounds=5)
        user["temp_password_used"] = False
        user["temp_password_expires_at"] = _to_iso(_now() + timedelta(hours=TEMP_PASSWORD_HOURS))
        user["failed_attempts"] = 0
        user["locked_until"] = None
        user["account_created"] = False
        user["account_status"] = "pending_setup"
        _sync_user_account_to_mysql(user)
        reset_accounts.append(_display_generated_account(user, temporary_password, action="reset"))
    if reset_accounts:
        _audit("visible_temp_password_reset", actor_id=actor_id, status="ok", details={"count": len(reset_accounts), "page": page, "per_page": per_page})
    return {"created": 0, "reset": len(reset_accounts), "skipped": skipped, "accounts": reset_accounts}


def _employee_number_sort_key(value):
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else 0


def _create_user_account(name, role="employee", actor_id=None):
    username = re.sub(r"\s+", " ", name).strip()
    role = str(role or "employee").strip().lower()
    if not username:
        raise ValueError("Name is required.")
    if role not in ALLOWED_ACCOUNT_ROLES:
        raise ValueError("Please choose a valid account role.")

    try:
        from src.db.repository import get_user_by_username
        if get_user_by_username(username):
            raise ValueError("Account already exists with this name.")
    except ValueError:
        raise
    except Exception:
        pass

    users = _load_registered_users()
    employee_id = _next_employee_id(users)
    company_email = _generate_company_email(username, employee_id, users)
    if _get_registered_user(username) or _get_registered_user(company_email):
        raise ValueError("Account already exists with this name or company email.")
    temporary_password = _random_password()
    user = {
        "id": _next_registered_user_id(users),
        "employee_id": employee_id,
        "username": username,
        "email": company_email,
        "company_email": company_email,
        "password_hash": _hash_secret(temporary_password),
        "role": role,
        "first_login": True,
        "temp_password_used": False,
        "temp_password_expires_at": _to_iso(_now() + timedelta(hours=TEMP_PASSWORD_HOURS)),
        "failed_attempts": 0,
        "locked_until": None,
        "created_by": actor_id,
        "created_at": _to_iso(_now()),
        "account_created": False,
        "account_status": "pending_setup",
    }
    users.append(user)
    _save_registered_users(users)
    _sync_user_account_to_mysql(user)
    _audit("account_created", actor_id=actor_id, target_id=user["id"], details={"role": role, "company_email": company_email})
    user["temporary_password"] = temporary_password
    return user


def _employee_number_start(users):
    existing = []
    for user in users:
        match = re.search(r"\d+", str(user.get("employee_id") or ""))
        if match:
            existing.append(int(match.group()))
    return max(existing or [1000]) + 1


def _batch_company_email(name, employee_id, used_emails):
    slug = re.sub(r"[^a-z0-9]+", ".", str(name or "").lower()).strip(".") or "employee"
    base = f"{slug}.{str(employee_id).lower()}@talentbeacon.local"
    if base.lower() not in used_emails:
        return base
    suffix = 2
    while True:
        email = f"{slug}.{str(employee_id).lower()}.{suffix}@talentbeacon.local"
        if email.lower() not in used_emails:
            return email
        suffix += 1


def _display_generated_account(user, temporary_password, action="created"):
    return {
        "employee_id": user["employee_id"],
        "name": user["username"],
        "company_email": user["company_email"],
        "temporary_password": temporary_password,
        "role": user["role"],
        "action": action,
    }


def _valid_employee_name(value):
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    if not value:
        return ""
    if re.fullmatch(r"employee\s+\d+", value, flags=re.IGNORECASE):
        return ""
    return value


def _stable_source_code(value):
    code = str(value or "").strip()
    if ":" in code:
        code = code.rsplit(":", 1)[-1].strip()
    return code


def _name_identity_key(value):
    name = _valid_employee_name(value)
    if not name:
        return ""
    normalized = re.sub(r"[^a-z0-9]+", ".", name.lower()).strip(".")
    return f"name:{normalized}" if normalized else ""


def _active_dataset_hash_for_actor(actor_id):
    try:
        active = get_active_dataset(actor_id)
        return str(active.get("file_hash") or "").strip() if active else ""
    except Exception:
        return ""


def _employee_identity_key(row, file_hash=""):
    email = str(row.get("Email") or "").strip().lower()
    if email and re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return f"email:{email}"
    name_key = _name_identity_key(row.get("Name"))
    if name_key:
        return name_key
    display_id = str(row.get("Display_Employee_ID") or "").strip()
    if display_id:
        return f"file:{file_hash}:row:{display_id}" if file_hash else ""
    code = _stable_source_code(row.get("Employee_Code"))
    if code:
        return f"file:{file_hash}:row:{code}" if file_hash else ""
    return ""


def _user_employee_identity_key(user):
    key = str(user.get("source_employee_key") or "").strip()
    if key and not key.startswith("row:"):
        return key
    email = str(user.get("source_email") or "").strip().lower()
    if email and re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return f"email:{email}"
    name_key = _name_identity_key(user.get("username") if user.get("name_from_file") else "")
    if name_key:
        return name_key
    file_hash = str(user.get("source_file_hash") or "").strip()
    code = _stable_source_code(user.get("source_employee_code"))
    if file_hash and code:
        return f"file:{file_hash}:row:{code}"
    return ""


def _create_accounts_from_active_dataset(actor_id=None, reset_existing_passwords=False):
    active_dataset_id = _active_dataset_id_for_actor(actor_id)
    active_file_hash = _active_dataset_hash_for_actor(actor_id)
    df = load_active_employee_df(user_id=actor_id)
    if df.empty:
        raise ValueError("Upload and activate an employee file first.")
    users = _load_registered_users()
    used_emails = {
        str(user.get("email") or "").strip().lower()
        for user in users
        if user.get("email")
    } | {
        str(user.get("company_email") or "").strip().lower()
        for user in users
        if user.get("company_email")
    }
    def prefer_existing_account(current, candidate):
        if current is None:
            return candidate
        current_ready = not bool(current.get("first_login"))
        candidate_ready = not bool(candidate.get("first_login"))
        if candidate_ready != current_ready:
            return candidate if candidate_ready else current
        if not candidate_ready:
            current_expires = _from_iso(current.get("temp_password_expires_at")) or datetime.min.replace(tzinfo=timezone.utc)
            candidate_expires = _from_iso(candidate.get("temp_password_expires_at")) or datetime.min.replace(tzinfo=timezone.utc)
            if candidate_expires > current_expires:
                return candidate
        return current

    users_by_email = {}
    users_by_source_key = {}
    for user in users:
        if str(user.get("created_by")) != str(actor_id) or not user.get("created_from_upload"):
            continue
        for email in {
            str(user.get("email") or "").strip().lower(),
            str(user.get("company_email") or "").strip().lower(),
        }:
            if email:
                users_by_email[email] = prefer_existing_account(users_by_email.get(email), user)
        key = _user_employee_identity_key(user)
        if key:
            users_by_source_key[key] = prefer_existing_account(users_by_source_key.get(key), user)
    next_user_id = _next_registered_user_id(users)
    next_employee_number = _employee_number_start(users)
    created_accounts = []
    reset_accounts = []
    skipped = 0
    changed = False

    for _, row in df.iterrows():
        row = row.to_dict()
        file_name = _valid_employee_name(row.get("Name"))
        name = file_name or f"Employee {row.get('Display_Employee_ID') or ''}".strip()
        has_file_name = bool(file_name)
        source_email = str(row.get("Email") or "").strip().lower()
        source_employee_code = str(row.get("Employee_Code") or row.get("Display_Employee_ID") or "").strip()
        source_employee_key = _employee_identity_key(row, active_file_hash)
        if not name:
            skipped += 1
            continue

        existing_user = None
        if source_email:
            existing_user = users_by_email.get(source_email)
        if existing_user is None and source_employee_key:
            existing_user = users_by_source_key.get(source_employee_key)

        if existing_user is not None:
            if existing_user.get("created_from_upload"):
                if existing_user.get("source_dataset_id") != active_dataset_id:
                    existing_user["source_dataset_id"] = active_dataset_id
                    changed = True
                if existing_user.get("source_employee_code") != source_employee_code:
                    existing_user["source_employee_code"] = source_employee_code
                    changed = True
                if source_employee_key and existing_user.get("source_employee_key") != source_employee_key:
                    existing_user["source_employee_key"] = source_employee_key
                    changed = True
                if source_email and existing_user.get("source_email") != source_email:
                    existing_user["source_email"] = source_email
                    changed = True
                if active_file_hash and existing_user.get("source_file_hash") != active_file_hash:
                    existing_user["source_file_hash"] = active_file_hash
                    changed = True
                if existing_user.get("username") != name:
                    existing_user["username"] = name
                    changed = True
                if bool(existing_user.get("name_from_file")) != has_file_name:
                    existing_user["name_from_file"] = has_file_name
                    changed = True
            if (
                reset_existing_passwords
                and existing_user.get("created_from_upload")
                and existing_user.get("first_login")
            ):
                temporary_password = _random_password()
                existing_user["password_hash"] = _hash_secret(temporary_password, rounds=5)
                existing_user["temp_password_used"] = False
                existing_user["temp_password_expires_at"] = _to_iso(_now() + timedelta(hours=TEMP_PASSWORD_HOURS))
                existing_user["failed_attempts"] = 0
                existing_user["locked_until"] = None
                _sync_user_account_to_mysql(existing_user)
                reset_accounts.append(_display_generated_account(existing_user, temporary_password, action="reset"))
                changed = True
            else:
                skipped += 1
            continue

        employee_id = f"TB{next_employee_number}"
        next_employee_number += 1
        company_email = ""
        if source_email and re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", source_email) and source_email not in used_emails:
            company_email = source_email
        else:
            company_email = _batch_company_email(name, employee_id, used_emails)
        company_email = company_email.lower()
        temporary_password = _random_password()
        user = {
            "id": next_user_id,
            "employee_id": employee_id,
            "source_dataset_id": active_dataset_id,
            "source_employee_code": source_employee_code,
            "source_employee_key": source_employee_key,
            "source_file_hash": active_file_hash,
            "source_email": source_email,
            "username": name,
            "name_from_file": has_file_name,
            "email": company_email,
            "company_email": company_email,
            "password_hash": _hash_secret(temporary_password, rounds=5),
            "role": "employee",
            "first_login": True,
            "temp_password_used": False,
            "temp_password_expires_at": _to_iso(_now() + timedelta(hours=TEMP_PASSWORD_HOURS)),
            "failed_attempts": 0,
            "locked_until": None,
            "created_by": actor_id,
            "created_at": _to_iso(_now()),
            "created_from_upload": True,
            "account_created": False,
            "account_status": "pending_setup",
        }
        next_user_id += 1
        users.append(user)
        _sync_user_account_to_mysql(user)
        used_emails.add(company_email)
        users_by_email[company_email] = user
        if source_employee_key:
            users_by_source_key[source_employee_key] = user
        created_accounts.append(_display_generated_account(user, temporary_password))
        changed = True

    if changed:
        _save_registered_users(users)
        changed_uploaded_users = [
            user for user in users
            if str(user.get("created_by")) == str(actor_id)
            and str(user.get("source_dataset_id") or "") == str(active_dataset_id)
            and user.get("created_from_upload")
        ]
        for user in changed_uploaded_users:
            user["account_created"] = not bool(user.get("first_login"))
            user["account_status"] = "created" if user["account_created"] else "pending_setup"
        _sync_user_accounts_to_mysql(changed_uploaded_users)
        for account in created_accounts:
            _audit("account_created", actor_id=actor_id, status="ok", details={"role": "employee", "company_email": account["company_email"], "source": "employee_upload"})
        if reset_accounts:
            _audit("bulk_temp_password_reset", actor_id=actor_id, status="ok", details={"count": len(reset_accounts), "source": "employee_upload"})

    accounts = created_accounts + reset_accounts
    return {
        "created": len(created_accounts),
        "reset": len(reset_accounts),
        "skipped": skipped,
        "accounts": accounts,
    }


def _next_employee_id(users):
    existing = []
    for user in users:
        match = re.search(r"\d+", str(user.get("employee_id") or ""))
        if match:
            existing.append(int(match.group()))
    return f"TB{max(existing or [1000]) + 1}"


def _generate_company_email(name, employee_id, users):
    slug = re.sub(r"[^a-z0-9]+", ".", name.lower()).strip(".") or "employee"
    base = f"{slug}.{str(employee_id).lower()}@talentbeacon.local"
    used = {str(user.get("email") or "").lower() for user in users} | {str(user.get("company_email") or "").lower() for user in users}
    if base.lower() not in used:
        return base
    return f"{slug}.{secrets.token_hex(3)}@talentbeacon.local"


def _issue_otp(user, purpose):
    otp = _random_otp()
    user["otp_hash"] = _hash_secret(otp)
    user["otp_expires_at"] = _to_iso(_now() + timedelta(minutes=OTP_MINUTES))
    user["otp_used"] = False
    user["otp_purpose"] = purpose
    _save_registered_user(user)
    sendOtpEmail(user.get("company_email") or user.get("email"), otp)
    print(f"[TalentBeacon Demo OTP] {otp} for {user.get('company_email') or user.get('email')} ({purpose})")
    return otp if _is_development() else None


def _verify_otp(user, otp, purpose):
    expires = _from_iso(user.get("otp_expires_at"))
    if user.get("otp_used") or user.get("otp_purpose") != purpose:
        return False
    if not expires or expires < _now():
        return False
    if not _check_secret(otp, user.get("otp_hash")):
        return False
    user["otp_used"] = True
    user["otp_hash"] = None
    user["otp_expires_at"] = None
    user["otp_purpose"] = None
    _save_registered_user(user)
    return True


def _change_user_password(user, password):
    if not _strong_password(password):
        raise ValueError("Password must be 8+ chars and include uppercase, lowercase, number, and symbol.")
    user["password_hash"] = _hash_secret(password)
    user["first_login"] = False
    user["temp_password_used"] = True
    user["temp_password_expires_at"] = None
    user["failed_attempts"] = 0
    user["locked_until"] = None
    user["account_created"] = True
    user["account_status"] = "created"
    _save_registered_user(user)
    _sync_user_account_to_mysql(user)
    _audit("password_changed", target_id=user.get("id"))
    return user


def _change_user_role(user_id, role, actor_id=None):
    role = str(role or "").strip().lower()
    if role not in ALLOWED_ACCOUNT_ROLES:
        raise ValueError("Please choose a valid account role.")
    user = _get_registered_user_by_id(user_id)
    if not user:
        raise ValueError("User not found.")
    old_role = user.get("role")
    user["role"] = role
    _save_registered_user(user)
    _audit("role_changed", actor_id=actor_id, target_id=user.get("id"), details={"old_role": old_role, "new_role": role})
    return user


def _next_registered_user_id(users):
    used_ids = {int(user.get("id") or 0) for user in users}
    try:
        state = json.loads((config.BASE_DIR / "workspace_data" / "state.json").read_text(encoding="utf-8"))
        for dataset in state.get("datasets", []):
            if dataset.get("uploaded_by") is not None:
                used_ids.add(int(dataset["uploaded_by"]))
        for project in state.get("projects", []):
            if project.get("created_by") is not None:
                used_ids.add(int(project["created_by"]))
        for key in state.get("active_dataset_ids", {}):
            if str(key).isdigit():
                used_ids.add(int(key))
    except Exception:
        pass
    return max([10000, *used_ids]) + 1


if __name__ == "__main__":
    app = create_app()
    app.run(debug=False, host="0.0.0.0", port=5001)
