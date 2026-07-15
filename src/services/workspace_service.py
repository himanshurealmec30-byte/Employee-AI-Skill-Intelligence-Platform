"""Reliable file-backed employee upload and project matching workspace."""
import hashlib
import json
import math
import re
import time
import uuid
from pandas.errors import EmptyDataError
from io import BytesIO
from pathlib import Path

import pandas as pd
from docx import Document
from pypdf import PdfReader

import config
from src.nlp.extractor import parse_project_requirements
from src.utils.skills import normalize_skill_key, split_skills


WORKSPACE_DIR = config.BASE_DIR / "workspace_data"
STATE_PATH = WORKSPACE_DIR / "state.json"
PROJECT_DOC_DIR = config.UPLOADS_DIR / "project_docs"

DATASET_COLUMN_ALIASES = {
    "employee_code": ["employee_id", "employee code", "id", "candidate_id", "candidate id"],
    "name": [
        "name",
        "full_name",
        "full name",
        "employee_name",
        "employee name",
        "employee_full_name",
        "employee full name",
        "candidate_name",
        "candidate name",
        "candidate_full_name",
        "candidate full name",
        "user_name",
        "user name",
    ],
    "email": ["email", "email_id", "email id", "mail"],
    "department": ["department", "dept"],
    "designation": ["designation", "job_title", "job title", "title", "role"],
    "years_of_experience": ["years_of_experience", "years of experience", "experience", "exp", "total_experience"],
    "education_level": ["education_level", "education level", "education", "degree", "qualification"],
    "skills": ["skills", "skill", "technical_skills", "technical skills", "primary_skills"],
    "certifications": ["certifications", "certification", "certificates", "certs"],
    "performance_score": ["performance_score", "performance score", "performance", "rating"],
    "projects_handled": ["projects_handled", "projects handled", "projects", "project_count"],
}

ALLOWED_DATASET_EXTENSIONS = {".csv", ".xlsx", ".xls"}
ALLOWED_PROJECT_DOC_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt"}


def _ensure_dirs():
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    config.DATASET_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    PROJECT_DOC_DIR.mkdir(parents=True, exist_ok=True)


def _default_state():
    return {"active_dataset_id": None, "active_dataset_ids": {}, "datasets": [], "projects": [], "matches": {}}


def _load_state():
    _ensure_dirs()
    if not STATE_PATH.exists():
        return _default_state()
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        state.setdefault("active_dataset_ids", {})
        state.setdefault("datasets", [])
        state.setdefault("projects", [])
        state.setdefault("matches", {})
        return state
    except json.JSONDecodeError:
        return _default_state()


def _save_state(state):
    _ensure_dirs()
    STATE_PATH.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def _prune_missing_datasets(state):
    datasets = state.get("datasets", [])
    kept = []
    changed = False
    for dataset in datasets:
        path = Path(dataset.get("file_path", ""))
        if path.exists():
            kept.append(dataset)
        else:
            changed = True
    if changed:
        state["datasets"] = kept
        active_id = state.get("active_dataset_id")
        if active_id not in {dataset["id"] for dataset in kept}:
            state["active_dataset_id"] = kept[0]["id"] if kept else None
            for index, dataset in enumerate(kept):
                dataset["is_active"] = index == 0
        state["matches"] = {}
        _save_state(state)
    return state


def _owner_key(user_id):
    return str(user_id) if user_id is not None else None


def _belongs_to_user(item, user_id, owner_field="uploaded_by"):
    key = _owner_key(user_id)
    if key is None:
        return True
    owner = item.get(owner_field)
    return str(owner) == key


def _user_datasets(state, user_id):
    return [dataset for dataset in state.get("datasets", []) if _belongs_to_user(dataset, user_id)]


def _active_dataset_id_for_user(state, user_id):
    key = _owner_key(user_id)
    if key is None:
        return state.get("active_dataset_id")
    return state.get("active_dataset_ids", {}).get(key)


def _safe_filename(filename):
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(filename).stem).strip("_") or "upload"
    return f"{stem}_{int(time.time())}_{uuid.uuid4().hex[:8]}{Path(filename).suffix.lower()}"


def _validate_dataset(filename):
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_DATASET_EXTENSIONS:
        raise ValueError("Upload a valid employee file: CSV, XLSX, or XLS.")
    return suffix


def _read_dataset(path):
    suffix = Path(path).suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path)


def _file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_duplicate_dataset(state, uploaded_by, file_hash, filename):
    original_name = str(filename or "").strip().lower()
    changed = False
    for dataset in _user_datasets(state, uploaded_by):
        if file_hash and dataset.get("file_hash") == file_hash:
            return dataset, changed
        existing_path = Path(dataset.get("file_path", ""))
        if file_hash and existing_path.exists() and not dataset.get("file_hash"):
            try:
                dataset["file_hash"] = _file_sha256(existing_path)
                changed = True
                if dataset["file_hash"] == file_hash:
                    return dataset, changed
            except OSError:
                pass
        if original_name and str(dataset.get("filename") or "").strip().lower() == original_name:
            return dataset, changed
    return None, changed


def _find_duplicate_project_document(state, user_id, file_hash, filename):
    original_name = str(filename or "").strip().lower()
    changed = False
    for project in state.get("projects", []):
        if not _belongs_to_user(project, user_id, owner_field="created_by"):
            continue
        if file_hash and project.get("source_hash") == file_hash:
            return project, changed
        source_path = Path(project.get("source_path", ""))
        if file_hash and source_path.exists() and not project.get("source_hash"):
            try:
                project["source_hash"] = _file_sha256(source_path)
                changed = True
                if project["source_hash"] == file_hash:
                    return project, changed
            except OSError:
                pass
        if original_name and str(project.get("source_filename") or "").strip().lower() == original_name:
            return project, changed
    return None, changed


def _normalize_col(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _get_row_value(values, target, default=""):
    for alias in DATASET_COLUMN_ALIASES[target]:
        key = _normalize_col(alias)
        if key in values and pd.notna(values[key]):
            return values[key]
    return default


def _to_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        match = re.search(r"\d+", str(value))
        return int(match.group()) if match else default


def _split_list(value):
    if pd.isna(value):
        return []
    return split_skills(value)


def _skill_key(skill):
    return normalize_skill_key(skill)


def _normalize_employee_df(df):
    rows = []
    for index, (_, row) in enumerate(df.iterrows(), start=1):
        values = {_normalize_col(col): row[col] for col in row.index}
        source_code = str(_get_row_value(values, "employee_code", index)).strip()
        skills = _split_list(_get_row_value(values, "skills", ""))
        rows.append({
            "Employee_ID": index,
            "Employee_Code": source_code,
            "Display_Employee_ID": index,
            "Name": str(_get_row_value(values, "name", f"Employee {index}")).strip(),
            "Email": str(_get_row_value(values, "email", "")).strip(),
            "Department": str(_get_row_value(values, "department", "Uploaded")).strip() or "Uploaded",
            "Job_Title": str(_get_row_value(values, "designation", "Employee")).strip() or "Employee",
            "Years_of_Experience": _to_int(_get_row_value(values, "years_of_experience", 0)),
            "Education_Level": str(_get_row_value(values, "education_level", "Unknown")).strip() or "Unknown",
            "Performance_Score": _to_int(_get_row_value(values, "performance_score", 3), default=3),
            "Projects_Handled": _to_int(_get_row_value(values, "projects_handled", 0)),
            "Employee_Satisfaction_Score": 3.0,
            "Certifications": ";".join(_split_list(_get_row_value(values, "certifications", ""))),
            "Skills": ";".join(skills),
            "Parsed_Skills": skills,
            "Parsed_Certifications": _split_list(_get_row_value(values, "certifications", "")),
        })
    return pd.DataFrame(rows)


def _display_employee_code(raw_code, fallback):
    code = str(raw_code or fallback).strip()
    if ":" in code:
        code = code.rsplit(":", 1)[-1].strip()
    return code or str(fallback)


def _mysql_employee_df(user_id=None):
    if not getattr(config, "MYSQL_READS_ENABLED", False):
        return pd.DataFrame()
    try:
        from src.db.repository import get_active_dataset_employees

        employees = get_active_dataset_employees(uploaded_by=user_id)
    except Exception:
        return pd.DataFrame()
    if not employees:
        return pd.DataFrame()

    rows = []
    for index, employee in enumerate(employees, start=1):
        display_code = _display_employee_code(employee.get("employee_code"), index)
        skills = split_skills(employee.get("skills") or "")
        certifications = split_skills(employee.get("certifications") or "")
        rows.append({
            "Employee_ID": _to_int(employee.get("id"), index),
            "Employee_Code": str(employee.get("employee_code") or display_code),
            "Display_Employee_ID": _to_int(display_code, index),
            "Name": str(employee.get("name") or f"Employee {display_code}").strip(),
            "Email": str(employee.get("email") or "").strip(),
            "Department": str(employee.get("department") or "Uploaded").strip() or "Uploaded",
            "Job_Title": str(employee.get("designation") or "Employee").strip() or "Employee",
            "Years_of_Experience": _to_int(employee.get("years_of_experience"), 0),
            "Education_Level": str(employee.get("education_level") or "Unknown").strip() or "Unknown",
            "Performance_Score": _to_int(employee.get("performance_score"), default=3),
            "Projects_Handled": _to_int(employee.get("projects_handled"), 0),
            "Employee_Satisfaction_Score": float(employee.get("satisfaction_score") or 3.0),
            "Certifications": ";".join(certifications),
            "Skills": ";".join(skills),
            "Parsed_Skills": skills,
            "Parsed_Certifications": certifications,
            "Source": "mysql",
            "Dataset_Upload_ID": employee.get("dataset_upload_id"),
            "Dataset_Filename": employee.get("dataset_filename"),
        })
    return pd.DataFrame(rows)


def _sync_dataset_to_mysql(dataset_meta, employee_df, uploaded_by=None):
    if not getattr(config, "MYSQL_READS_ENABLED", False):
        return None
    try:
        from src.db.repository import (
            create_dataset_upload,
            ensure_upload_schema,
            update_dataset_row_count,
            upsert_employees_from_upload,
        )

        ensure_upload_schema()
        mysql_upload_id = create_dataset_upload(
            dataset_meta["filename"],
            dataset_meta["file_type"],
            int(len(employee_df)),
            uploaded_by=uploaded_by,
            stored_filename=dataset_meta.get("stored_filename"),
            file_path=dataset_meta.get("file_path"),
        )
        candidates = []
        for _, employee in employee_df.iterrows():
            display_code = str(employee.get("Display_Employee_ID") or employee.get("Employee_Code") or "")
            candidate_code = f"{dataset_meta['id']}:{display_code}"
            candidates.append({
                "employee_code": candidate_code,
                "name": employee.get("Name"),
                "email": employee.get("Email"),
                "department": employee.get("Department", "Uploaded"),
                "designation": employee.get("Job_Title", "Employee"),
                "years_of_experience": _to_int(employee.get("Years_of_Experience"), 0),
                "education_level": employee.get("Education_Level", "Unknown"),
                "performance_score": _to_int(employee.get("Performance_Score"), default=3),
                "projects_handled": _to_int(employee.get("Projects_Handled"), 0),
                "satisfaction_score": employee.get("Employee_Satisfaction_Score", 3.0),
                "skills": list(employee.get("Parsed_Skills") or []),
                "certifications": list(employee.get("Parsed_Certifications") or []),
            })
        inserted = upsert_employees_from_upload(candidates, mysql_upload_id)
        update_dataset_row_count(mysql_upload_id, inserted)
        return mysql_upload_id
    except Exception as exc:
        return {"error": str(exc)}


def _requires_mysql_dataset_persistence():
    host = str(getattr(config, "MYSQL_HOST", "") or "").strip().lower()
    return (
        bool(getattr(config, "IS_PRODUCTION", False))
        or bool(getattr(config, "MYSQL_READS_REQUESTED", getattr(config, "MYSQL_READS_ENABLED", False)))
    ) and host not in {"", "localhost", "127.0.0.1", "::1"}


def process_dataset_upload(file_storage, uploaded_by=None):
    _ensure_dirs()
    suffix = _validate_dataset(file_storage.filename)
    stored_name = _safe_filename(file_storage.filename)
    stored_path = config.DATASET_UPLOAD_DIR / stored_name
    file_storage.save(stored_path)
    file_hash = _file_sha256(stored_path)
    state = _load_state()
    duplicate, state_changed = _find_duplicate_dataset(state, uploaded_by, file_hash, file_storage.filename)
    if state_changed:
        _save_state(state)
    if duplicate:
        stored_path.unlink(missing_ok=True)
        raise ValueError(
            f"Duplicate file detected. '{duplicate.get('filename', file_storage.filename)}' is already uploaded."
        )

    try:
        raw_df = _read_dataset(stored_path)
    except EmptyDataError:
        stored_path.unlink(missing_ok=True)
        raise ValueError("The uploaded file is empty")
    if raw_df.empty:
        stored_path.unlink(missing_ok=True)
        raise ValueError("The uploaded file is empty")
    employee_df = _normalize_employee_df(raw_df)
    if employee_df.empty:
        stored_path.unlink(missing_ok=True)
        raise ValueError("The uploaded file is empty")

    dataset_id = uuid.uuid4().hex
    for dataset in state["datasets"]:
        if _belongs_to_user(dataset, uploaded_by):
            dataset["is_active"] = False
    meta = {
        "id": dataset_id,
        "filename": file_storage.filename,
        "stored_filename": stored_name,
        "file_path": str(stored_path),
        "file_type": "csv" if suffix == ".csv" else "excel",
        "file_hash": file_hash,
        "row_count": int(len(employee_df)),
        "is_active": True,
        "uploaded_by": uploaded_by,
        "uploaded_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    sync_result = _sync_dataset_to_mysql(meta, employee_df, uploaded_by=uploaded_by)
    if isinstance(sync_result, int):
        meta["mysql_upload_id"] = sync_result
    elif isinstance(sync_result, dict) and sync_result.get("error"):
        if _requires_mysql_dataset_persistence():
            stored_path.unlink(missing_ok=True)
            raise ValueError(f"Could not save employee file to MySQL: {sync_result['error']}")
        meta["mysql_sync_error"] = sync_result["error"]
    state["datasets"].insert(0, meta)
    state.setdefault("active_dataset_ids", {})[_owner_key(uploaded_by) or "global"] = dataset_id
    state["active_dataset_id"] = dataset_id
    state["matches"] = {key: value for key, value in state.get("matches", {}).items() if not key.startswith(f"{_owner_key(uploaded_by)}:")}
    _save_state(state)
    return {"upload_id": dataset_id, "row_count": int(len(employee_df))}


def list_dataset_uploads(limit=100, user_id=None):
    state = _prune_missing_datasets(_load_state())
    return _user_datasets(state, user_id)[:limit]


def get_active_dataset(user_id=None):
    state = _prune_missing_datasets(_load_state())
    active_id = _active_dataset_id_for_user(state, user_id)
    for dataset in _user_datasets(state, user_id):
        if dataset["id"] == active_id:
            return dataset
    if getattr(config, "MYSQL_READS_ENABLED", False):
        try:
            from src.db.repository import get_active_dataset_upload

            active = get_active_dataset_upload(uploaded_by=user_id)
            if active:
                return {
                    "id": str(active.get("id")),
                    "mysql_upload_id": active.get("id"),
                    "filename": active.get("filename"),
                    "stored_filename": active.get("stored_filename"),
                    "file_path": active.get("file_path"),
                    "file_type": active.get("file_type"),
                    "row_count": int(active.get("row_count") or 0),
                    "uploaded_by": active.get("uploaded_by"),
                    "is_active": bool(active.get("is_active")),
                    "uploaded_at": str(active.get("uploaded_at") or ""),
                }
        except Exception:
            pass
    return None


def load_active_employee_df(user_id=None):
    mysql_df = _mysql_employee_df(user_id=user_id)
    if not mysql_df.empty:
        return mysql_df

    active = get_active_dataset(user_id=user_id)
    if not active:
        return pd.DataFrame()
    path = Path(active["file_path"])
    if not path.exists():
        return pd.DataFrame()
    return _normalize_employee_df(_read_dataset(path))


def activate_dataset(upload_id, user_id=None):
    state = _load_state()
    found = None
    for dataset in state["datasets"]:
        if _belongs_to_user(dataset, user_id):
            dataset["is_active"] = dataset["id"] == str(upload_id)
            if dataset["is_active"]:
                found = dataset
    if not found:
        raise ValueError("Uploaded employee file not found.")
    state.setdefault("active_dataset_ids", {})[_owner_key(user_id) or "global"] = found["id"]
    state["active_dataset_id"] = found["id"]
    if user_id is not None:
        state["matches"] = {key: value for key, value in state.get("matches", {}).items() if not key.startswith(f"{_owner_key(user_id)}:")}
    else:
        state["matches"] = {}
    mysql_upload_id = found.get("mysql_upload_id")
    if mysql_upload_id:
        try:
            from src.db.repository import activate_dataset_upload

            activate_dataset_upload(mysql_upload_id, uploaded_by=user_id)
        except Exception as exc:
            found["mysql_sync_error"] = str(exc)
    _save_state(state)
    return found


def delete_dataset(upload_id, user_id=None):
    state = _load_state()
    upload_id = str(upload_id)
    removed = None
    kept = []
    for dataset in state["datasets"]:
        if dataset["id"] == upload_id and _belongs_to_user(dataset, user_id):
            removed = dataset
        else:
            kept.append(dataset)
    if not removed:
        raise ValueError("Uploaded employee file not found.")
    Path(removed.get("file_path", "")).unlink(missing_ok=True)
    state["datasets"] = kept
    user_key = _owner_key(user_id) or "global"
    if state.get("active_dataset_ids", {}).get(user_key) == upload_id or state.get("active_dataset_id") == upload_id:
        user_kept = _user_datasets(state, user_id)
        next_active = user_kept[0]["id"] if user_kept else None
        state.setdefault("active_dataset_ids", {})[user_key] = next_active
        state["active_dataset_id"] = next_active
        for dataset in user_kept:
            dataset["is_active"] = dataset["id"] == next_active
    if user_id is not None:
        state["matches"] = {key: value for key, value in state.get("matches", {}).items() if not key.startswith(f"{_owner_key(user_id)}:")}
    else:
        state["matches"] = {}
    mysql_upload_id = removed.get("mysql_upload_id")
    if mysql_upload_id:
        try:
            from src.db.repository import delete_dataset_upload

            delete_dataset_upload(mysql_upload_id)
        except Exception as exc:
            removed["mysql_sync_error"] = str(exc)
    _save_state(state)
    return removed


def dashboard_upload_summary(user_id=None):
    state = _prune_missing_datasets(_load_state())
    active = get_active_dataset(user_id=user_id)
    user_datasets = _user_datasets(state, user_id)
    if not user_datasets and getattr(config, "MYSQL_READS_ENABLED", False):
        try:
            from src.db.repository import get_dataset_uploads

            user_datasets = [
                dataset for dataset in get_dataset_uploads(limit=100)
                if user_id is None
                or dataset.get("uploaded_by") == user_id
                or dataset.get("uploaded_by") is None
                or (active and dataset.get("id") == active.get("mysql_upload_id"))
            ]
        except Exception:
            user_datasets = []
    best = 0
    user_prefix = f"{_owner_key(user_id)}:" if user_id is not None else None
    for key, rows in state.get("matches", {}).items():
        if user_prefix is not None and not str(key).startswith(user_prefix):
            continue
        for row in rows:
            best = max(best, float(row.get("match_score", 0)))
    summary = {
        "uploaded_candidates": active["row_count"] if active else 0,
        "active_row_count": active["row_count"] if active else 0,
        "uploaded_datasets": len(user_datasets),
        "uploaded_jds": 0,
        "best_match_score": round(best, 1),
        "active_dataset": active["filename"] if active else None,
        "active_dataset_id": active["id"] if active else None,
    }
    return summary, user_datasets[:5], []


def list_projects(user_id=None):
    state = _load_state()
    projects = []
    for project in state["projects"]:
        if not _belongs_to_user(project, user_id, owner_field="created_by"):
            continue
        matches = state.get("matches", {}).get(_match_key(project["id"], user_id), state.get("matches", {}).get(project["id"], []))
        project_copy = project.copy()
        project_copy["match_count"] = len(matches)
        project_copy["top_match"] = max([m["match_score"] for m in matches], default=0)
        projects.append(project_copy)
    return projects


def project_detail(project_id, user_id=None):
    for project in _load_state()["projects"]:
        if project["id"] == str(project_id) and _belongs_to_user(project, user_id, owner_field="created_by"):
            return project
    return None


def _match_key(project_id, user_id=None):
    key = _owner_key(user_id)
    return f"{key}:{project_id}" if key is not None else str(project_id)


def save_project_from_form(form, created_by=None, project_id=None):
    state = _load_state()
    name = str(form.get("name") or "").strip()
    skills = str(form.get("required_skills") or "").strip()
    description = str(form.get("description") or "").strip()
    min_exp = _to_int(form.get("min_experience") or 0)
    source_filename = str(form.get("source_filename") or "").strip()
    source_path = str(form.get("source_path") or "").strip()
    source_hash = str(form.get("source_hash") or "").strip()
    if not name:
        raise ValueError("Project name is required.")
    if not skills:
        raise ValueError("Required skills are required.")
    if project_id:
        for project in state["projects"]:
            if project["id"] == str(project_id) and _belongs_to_user(project, created_by, owner_field="created_by"):
                project.update({
                    "name": name,
                    "required_skills": skills,
                    "description": description,
                    "min_experience": min_exp,
                })
                if source_filename:
                    project["source_filename"] = source_filename
                    project["source_path"] = source_path
                    project["source_hash"] = source_hash
                _save_state(state)
                return project["id"]
        raise ValueError("Project not found.")
    project_id = uuid.uuid4().hex
    state["projects"].insert(0, {
        "id": project_id,
        "name": name,
        "required_skills": skills,
        "description": description,
        "min_experience": min_exp,
        "created_by": created_by,
        "created_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_filename": source_filename,
        "source_path": source_path,
        "source_hash": source_hash,
    })
    _save_state(state)
    return project_id


def remove_project(project_id, user_id=None):
    state = _load_state()
    removed = next((p for p in state["projects"] if p["id"] == str(project_id) and _belongs_to_user(p, user_id, owner_field="created_by")), None)
    if removed and removed.get("source_path"):
        Path(removed["source_path"]).unlink(missing_ok=True)
    state["projects"] = [p for p in state["projects"] if not (p["id"] == str(project_id) and _belongs_to_user(p, user_id, owner_field="created_by"))]
    state.get("matches", {}).pop(_match_key(project_id, user_id), None)
    state.get("matches", {}).pop(str(project_id), None)
    _save_state(state)


def _project_requirements(project, user_id=None):
    manual_skills = _split_list(project.get("required_skills", ""))
    parsed = parse_project_requirements(project.get("description", ""), skill_vocab=_active_skill_vocab(user_id=user_id))
    # The skills explicitly reviewed by the manager are authoritative. Description
    # extraction is only a fallback for older projects without a skill list.
    selected_skills = manual_skills or parsed.get("skills", [])
    skills_by_key = {_skill_key(skill): skill.strip() for skill in selected_skills if str(skill).strip()}
    skills = list(skills_by_key.values())
    return {
        "skills": skills,
        "min_experience": int(project.get("min_experience") or parsed.get("min_experience") or 0),
        "keywords": extract_keywords(project.get("description", "") + " " + " ".join(skills)),
        "education": extract_education_requirements(project.get("description", "")),
    }


def match_project(project_id, user_id=None):
    state = _load_state()
    project = project_detail(project_id, user_id=user_id)
    if not project:
        raise ValueError("Project not found.")
    df = load_active_employee_df(user_id=user_id)
    if df.empty:
        raise ValueError("Upload and activate an employee file first.")
    requirements = _project_requirements(project, user_id=user_id)
    if not requirements.get("skills"):
        raise ValueError("No skills were extracted from this project. Upload a PDF, DOC, DOCX, or TXT project file with clear skill requirements.")
    matches = []
    for _, row in df.iterrows():
        score, breakdown = score_employee(row.to_dict(), requirements)
        if score is None:
            continue
        matches.append({
            "employee_id": int(row["Display_Employee_ID"]),
            "name": row.get("Name", f"Employee {row['Display_Employee_ID']}"),
            "email": row.get("Email", ""),
            "department": row.get("Department", ""),
            "designation": row.get("Job_Title", ""),
            "years_of_experience": int(row.get("Years_of_Experience", 0)),
            "education_level": row.get("Education_Level", "Unknown"),
            "skills": row.get("Skills", ""),
            "match_score": score,
            "skill_match_percentage": breakdown.get("skill_score", 0),
            "matched_skills": breakdown.get("matched_skills", []),
            "missing_skills": breakdown.get("missing_skills", []),
            "required_skills": requirements.get("skills", []),
            "score_breakdown": breakdown,
        })
    matches.sort(key=lambda item: (item.get("skill_match_percentage", 0), item["match_score"]), reverse=True)
    state["matches"][_match_key(project_id, user_id)] = matches
    _save_state(state)
    return matches


def refresh_project_from_source(project_id, user_id=None):
    state = _load_state()
    project = project_detail(project_id, user_id=user_id)
    if not project:
        raise ValueError("Project not found.")
    source_path = project.get("source_path")
    if not source_path:
        raise ValueError("No uploaded source document is attached to this project.")
    path = Path(source_path)
    if not path.exists():
        raise ValueError("The uploaded source document is missing. Please upload the project again.")
    suffix = path.suffix.lower()
    if suffix not in ALLOWED_PROJECT_DOC_EXTENSIONS:
        raise ValueError("Upload a project document as PDF, DOC, DOCX, or TXT.")
    text = extract_project_document_text(BytesIO(path.read_bytes()), suffix)
    if not text.strip():
        raise ValueError("No readable text found in this project document.")
    parsed = _parse_document_requirements(text, user_id=user_id)
    skills = parsed.get("skills", [])
    if not skills:
        raise ValueError("No skills were extracted from this project document.")
    for item in state["projects"]:
        if item["id"] == str(project_id) and _belongs_to_user(item, user_id, owner_field="created_by"):
            item["required_skills"] = "; ".join(skills)
            item["description"] = text[:5000]
            item["min_experience"] = int(parsed.get("min_experience") or 0)
            break
    state.get("matches", {}).pop(_match_key(project_id, user_id), None)
    _save_state(state)
    return parsed


def get_project_matches(project_id, user_id=None):
    state = _load_state()
    return state.get("matches", {}).get(_match_key(project_id, user_id), [])


def score_employee(employee, requirements):
    required_map = {
        _skill_key(skill): str(skill).strip()
        for skill in requirements.get("skills", [])
        if str(skill).strip()
    }
    required = set(required_map)
    emp_skills_raw = employee.get("Parsed_Skills") or _split_list(employee.get("Skills", ""))
    existing = {_skill_key(s) for s in emp_skills_raw}
    missing = required - existing
    matched = required & existing
    if len(required) > 10:
        minimum_matches = max(1, math.ceil(len(required) * 0.25))
    elif len(required) > 5:
        minimum_matches = max(1, math.ceil(len(required) * 0.40))
    else:
        minimum_matches = max(1, math.ceil(len(required) * 0.60)) if required else 0
    if len(matched) < minimum_matches:
        return None, {
            "missing_skills": sorted(required_map[key] for key in missing),
            "matched_skills": sorted(required_map[key] for key in matched),
        }

    exp_req = int(requirements.get("min_experience") or 0)
    exp = int(employee.get("Years_of_Experience") or employee.get("years_of_experience") or 0)
    exp_score = 1.0 if exp_req <= 0 else min(1.0, exp / max(exp_req, 1))
    keywords = set(requirements.get("keywords") or [])
    emp_text = " ".join(str(employee.get(k, "")) for k in ["Name", "Department", "Job_Title", "Education_Level", "Skills"]).lower()
    keyword_hits = sorted(k for k in keywords if k in emp_text)
    keyword_score = len(keyword_hits) / max(len(keywords), 1)
    skill_score = len(matched) / max(len(required), 1)
    performance = float(employee.get("Performance_Score") or 3)
    performance_score = min(max(performance / 5.0, 0), 1)
    score_factors = [
        {
            "label": "Skill coverage",
            "weight": 65,
            "score": round(skill_score * 100, 1),
            "contribution": round(65 * skill_score, 2),
        },
        {
            "label": "Experience fit",
            "weight": 15,
            "score": round(exp_score * 100, 1),
            "contribution": round(15 * exp_score, 2),
        },
        {
            "label": "Keyword relevance",
            "weight": 10,
            "score": round(keyword_score * 100, 1),
            "contribution": round(10 * keyword_score, 2),
        },
        {
            "label": "Performance",
            "weight": 10,
            "score": round(performance_score * 100, 1),
            "contribution": round(10 * performance_score, 2),
        },
    ]
    score = sum(item["contribution"] for item in score_factors)
    return round(min(score, 100), 2), {
        "skill_score": round(skill_score * 100, 1),
        "experience_score": round(exp_score * 100, 1),
        "keyword_score": round(keyword_score * 100, 1),
        "performance_score": round(performance_score * 100, 1),
        "score_factors": score_factors,
        "score_explanation": (
            f"{len(matched)}/{len(required)} required skills matched, "
            f"{exp}/{exp_req or 0} required years covered, "
            f"{len(keyword_hits)} keyword hits, and performance {performance}/5."
        ),
        "matched_skills": sorted(required_map[key] for key in matched),
        "missing_skills": sorted(required_map[key] for key in missing),
        "keyword_hits": keyword_hits,
        "experience_required": exp_req,
        "experience_actual": exp,
        "experience_gap": max(exp_req - exp, 0),
    }


def _active_skill_vocab(user_id=None):
    df = load_active_employee_df(user_id=user_id)
    vocab = set()
    if not df.empty:
        for skills in df["Parsed_Skills"]:
            vocab.update(skills)
    return sorted(vocab)


def project_requirements_from_document(file_storage, user_id=None):
    _ensure_dirs()
    original_name = Path(file_storage.filename).name
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_PROJECT_DOC_EXTENSIONS:
        raise ValueError("Upload a project document as PDF, DOC, DOCX, or TXT.")
    data = file_storage.read()
    if not data:
        raise ValueError("The selected project document is empty.")
    file_hash = hashlib.sha256(data).hexdigest()
    state = _load_state()
    duplicate, state_changed = _find_duplicate_project_document(state, user_id, file_hash, original_name)
    if state_changed:
        _save_state(state)
    if duplicate:
        raise ValueError(
            f"Duplicate project file detected. '{duplicate.get('source_filename') or duplicate.get('name')}' is already uploaded."
        )
    stored_name = _safe_filename(original_name)
    stored_path = PROJECT_DOC_DIR / stored_name
    stored_path.write_bytes(data)
    try:
        text = extract_project_document_text(BytesIO(data), suffix)
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise
    if not text.strip():
        stored_path.unlink(missing_ok=True)
        raise ValueError("No readable text found in this project document.")
    parsed = _parse_document_requirements(text, user_id=user_id)
    parsed["description"] = text[:5000]
    parsed["suggested_name"] = _suggest_project_name(text)
    parsed["source_filename"] = original_name
    parsed["source_path"] = str(stored_path)
    parsed["source_hash"] = file_hash
    return parsed


def _parse_document_requirements(text, user_id=None):
    """Extract requirements from the whole uploaded project document."""
    normalized = re.sub(r"[ \t]+", " ", str(text)).replace("\r", "")
    vocab = _active_skill_vocab(user_id=user_id)

    # SRS and project briefs commonly contain a dedicated requirements block. It
    # is more authoritative than examples and technology names elsewhere.
    section_patterns = [
        r"project requirements\s*(.*?)(?=\n\s*output\b|\n\s*module\s+\d+\b|\n\s*\d+\.\s+[A-Z]|\Z)",
        r"(?:technical\s+skills|skills\s+required|required\s+skills|skills|technology\s+stack|tech\s+stack|tools\s+and\s+technolog(?:y|ies)|required\s+technolog(?:y|ies))\s*:?\s*(.*?)(?=\n\s*(?:experience|education|responsibilities|deliverables|output|timeline|budget|module|non[- ]functional|functional|overview|description)\b|\Z)",
        r"required skills\s*(.*?)(?=\n\s*(?:desired skills|responsibilities|education|experience|output)\b|\Z)",
        r"must[- ]have skills?\s*(.*?)(?=\n\s*(?:preferred|nice to have|responsibilities|education|experience)\b|\Z)",
    ]
    focused_text = ""
    for pattern in section_patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE | re.DOTALL)
        if match:
            focused_text = match.group(1).strip()
            if focused_text:
                break

    full_parsed = parse_project_requirements(normalized, skill_vocab=vocab)
    focused_parsed = parse_project_requirements(focused_text, skill_vocab=vocab) if focused_text else {}

    # Analyze the entire uploaded document, but keep explicitly named
    # requirement-section skills first when present.
    parsed = dict(full_parsed)
    skills_by_key = {}
    for skill in list(focused_parsed.get("skills", [])) + list(full_parsed.get("skills", [])):
        key = _skill_key(skill)
        if key and key not in skills_by_key:
            skills_by_key[key] = str(skill).strip()
    parsed["skills"] = list(skills_by_key.values())
    if focused_parsed.get("domain") and focused_parsed.get("skills"):
        parsed["domain"] = focused_parsed["domain"]
    parsed["certifications"] = sorted(set(full_parsed.get("certifications", [])) | set(focused_parsed.get("certifications", [])))

    # Experience must be expressed in years. This avoids interpreting SRS phase
    # ranges such as "Weeks 1-3" as three years of employee experience.
    year_values = [
        int(value)
        for value in re.findall(
            r"(?:minimum|min\.?|at least)?\s*(\d{1,2})(?:\s*[-–]\s*\d{1,2})?\s*(?:\+\s*)?years?\b",
            normalized,
            flags=re.IGNORECASE,
        )
    ]
    parsed["min_experience"] = min(year_values) if year_values else 0
    parsed["extraction_scope"] = "full document"
    return parsed


def extract_project_document_text(file_stream, suffix):
    if suffix == ".pdf":
        reader = PdfReader(file_stream)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if suffix == ".docx":
        doc = Document(file_stream)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    if suffix == ".doc":
        return extract_legacy_doc_text(file_stream.read())
    return file_stream.read().decode("utf-8", errors="ignore")


def extract_legacy_doc_text(data):
    """Best-effort text extraction for old binary Word .doc files."""
    chunks = []
    for encoding in ("utf-16le", "latin-1"):
        decoded = data.decode(encoding, errors="ignore")
        decoded = decoded.replace("\x00", " ")
        decoded = re.sub(r"[\x01-\x08\x0b-\x1f]+", " ", decoded)
        for chunk in re.findall(r"[A-Za-z0-9][A-Za-z0-9\s,.;:()/_+#&@%'-]{8,}", decoded):
            cleaned = re.sub(r"\s+", " ", chunk).strip()
            if cleaned and cleaned not in chunks:
                chunks.append(cleaned)
    return clean_legacy_doc_text("\n".join(chunks))


def clean_legacy_doc_text(text):
    noisy_patterns = [
        r"\bToc\d+\b",
        r"\bPAGEREF\b",
        r"\bHYPERLINK\b",
        r"\bRoot Entry\b",
        r"\bWordDocument\b",
        r"\bSummaryInformation\b",
        r"\bDocumentSummaryInformation\b",
        r"\bMicrosoft Word(?: Document)?\b",
        r"\bMSWordDoc\b",
        r"\bWord\.Document\.\d+\b",
        r"\bNormal\b",
        r"\bHeading \d\b",
        r"\bDefault Paragraph Font\b",
        r"\bTable Normal\b",
        r"\bTable of Contents\b",
        r"\bSpring\s+\d{4}\b",
    ]
    cleaned = str(text)
    for pattern in noisy_patterns:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(?:\b[A-Za-z]\s){5,}[A-Za-z]\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def extract_keywords(text, limit=20):
    stop = {"and", "the", "with", "for", "from", "that", "this", "role", "project", "skills", "experience"}
    words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9+#.-]{2,}\b", str(text).lower())
    counts = {}
    for word in words:
        if word not in stop:
            counts[word] = counts.get(word, 0) + 1
    return [word for word, _ in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]]


def extract_education_requirements(text):
    levels = ["phd", "masters", "master", "mba", "bachelor", "bachelors", "b.tech", "m.tech", "diploma"]
    low = str(text).lower()
    return [level for level in levels if level in low]


def _suggest_project_name(text):
    lines = [re.sub(r"\s+", " ", line).strip() for line in str(text).splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if re.fullmatch(r"project title\s*:?\s*", line, flags=re.IGNORECASE) and index + 1 < len(lines):
            return lines[index + 1][:100]
    for line in lines:
        if re.match(r"(?:project|system|application)\s*(?:title|name)\s*:", line, flags=re.IGNORECASE):
            return line.split(":", 1)[-1].strip()[:100]
    for line in lines:
        if re.fullmatch(r"software requirements specification|\(?srs\)?", line, flags=re.IGNORECASE):
            continue
        line = line.strip()
        if line:
            return line[:80]
    return "Uploaded Project"


def process_jd_upload(file_storage, uploaded_by=None):
    result = project_requirements_from_document(file_storage)
    return {"jd_upload_id": "file", "requirements": result, "matches": []}


def get_jd_matches(jd_upload_id):
    return []
