"""Production database sync for TalentBeacon.

This command keeps the current Flask app safe: it syncs the active uploaded
employee file into MySQL without removing the file-backed fallback.
"""
import json
from pathlib import Path

import pymysql

import config
from src.services.workspace_service import get_active_dataset, load_active_employee_df
from src.db.repository import ensure_upload_schema, create_dataset_upload, upsert_employee_from_upload


def ensure_database_exists():
    conn = pymysql.connect(
        host=config.MYSQL_HOST,
        port=config.MYSQL_PORT,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASSWORD,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{config.MYSQL_DATABASE}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        conn.close()


def sync_active_dataset(user_id=1):
    ensure_database_exists()
    ensure_upload_schema()
    active = get_active_dataset(user_id=user_id)
    if not active:
        raise RuntimeError("No active uploaded employee file found for this user.")
    df = load_active_employee_df(user_id=user_id)
    if df.empty:
        raise RuntimeError("Active employee file is empty or unreadable.")

    dataset_upload_id = create_dataset_upload(
        filename=active.get("filename") or Path(active.get("file_path", "active_dataset")).name,
        file_type=active.get("file_type") or "excel",
        row_count=len(df),
        uploaded_by=user_id,
        stored_filename=active.get("stored_filename"),
        file_path=active.get("file_path"),
    )

    synced = 0
    for _, row in df.iterrows():
        skills = row.get("Parsed_Skills") or []
        certs = row.get("Parsed_Certifications") or []
        employee_code = f"{active['id']}:{row.get('Employee_Code') or row.get('Display_Employee_ID')}"
        upsert_employee_from_upload(
            {
                "employee_code": employee_code,
                "name": row.get("Name"),
                "email": row.get("Email"),
                "department": row.get("Department") or "Uploaded",
                "designation": row.get("Job_Title") or "Employee",
                "years_of_experience": int(row.get("Years_of_Experience") or 0),
                "education_level": row.get("Education_Level") or "Unknown",
                "performance_score": int(row.get("Performance_Score") or 3),
                "projects_handled": int(row.get("Projects_Handled") or 0),
                "satisfaction_score": float(row.get("Employee_Satisfaction_Score") or 3.0),
                "skills": list(skills),
                "certifications": list(certs),
            },
            dataset_upload_id,
        )
        synced += 1

    result = {
        "database": config.MYSQL_DATABASE,
        "dataset_upload_id": dataset_upload_id,
        "active_dataset_id": active["id"],
        "employees_synced": synced,
    }
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    sync_active_dataset()
