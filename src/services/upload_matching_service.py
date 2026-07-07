"""Dataset upload, JD extraction, and candidate matching service."""
import hashlib
import time
import re
from pathlib import Path

import pandas as pd
from docx import Document
from pypdf import PdfReader

import config
from src.db.repository import (
    activate_dataset_upload,
    clear_dataset_employees,
    clear_project_matches,
    create_dataset_upload,
    create_jd_upload,
    create_project,
    delete_project,
    delete_dataset_upload,
    ensure_upload_schema,
    get_active_dataset_upload,
    get_candidate_records,
    get_dataset_upload,
    get_dataset_uploads,
    get_jd_uploads,
    get_matches_for_jd,
    get_matches_for_project,
    get_project,
    get_projects,
    get_upload_summary,
    get_uploaded_candidate_count,
    save_jd_match,
    save_project_match,
    update_project,
    update_dataset_row_count,
    upsert_employees_from_upload,
)
from src.nlp.extractor import parse_project_requirements
from src.utils.skills import normalize_skill_key


ALLOWED_DATASET_EXTENSIONS = {".csv", ".xlsx", ".xls"}
ALLOWED_JD_EXTENSIONS = {".pdf"}
ALLOWED_PROJECT_DOC_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt"}

DATASET_COLUMN_ALIASES = {
    "employee_code": ["employee_id", "employee code", "id", "candidate_id", "candidate id"],
    "name": ["name", "candidate_name", "candidate name", "employee_name", "employee name"],
    "email": ["email", "email_id", "email id", "mail"],
    "department": ["department", "dept"],
    "designation": ["designation", "job_title", "job title", "title", "role"],
    "years_of_experience": ["years_of_experience", "years of experience", "experience", "exp", "total_experience"],
    "education_level": ["education_level", "education level", "education", "degree", "qualification"],
    "skills": ["skills", "skill", "technical_skills", "technical skills", "primary_skills"],
    "certifications": ["certifications", "certification", "certificates", "certs"],
}

EDUCATION_LEVELS = [
    "phd", "doctorate", "masters", "master", "m.tech", "mtech", "mba",
    "bachelors", "bachelor", "b.tech", "btech", "be", "bs", "msc", "bsc",
    "diploma",
]

STOPWORDS = {
    "and", "or", "the", "with", "for", "from", "this", "that", "will", "must",
    "have", "has", "are", "our", "you", "your", "years", "experience", "candidate",
    "skills", "work", "team", "role", "job", "description", "responsibilities",
}


def validate_dataset_file(filename):
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_DATASET_EXTENSIONS:
        raise ValueError("Upload a valid CSV or Excel file (.csv, .xlsx, .xls).")
    return suffix


def validate_jd_file(filename):
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_JD_EXTENSIONS:
        raise ValueError("Upload a valid PDF file.")
    return suffix


def validate_project_doc_file(filename):
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_PROJECT_DOC_EXTENSIONS:
        raise ValueError("Upload a valid project document (.pdf, .doc, .docx, .txt).")
    return suffix


def process_dataset_upload(file_storage, uploaded_by=None):
    ensure_upload_schema()
    suffix = validate_dataset_file(file_storage.filename)
    stored_path = _save_uploaded_dataset_file(file_storage, suffix)
    df, file_type = read_dataset_file(stored_path)

    if df.empty:
        stored_path.unlink(missing_ok=True)
        raise ValueError("Uploaded dataset is empty.")

    candidates = [_row_to_candidate(row, i) for i, row in df.iterrows()]
    upload_id = create_dataset_upload(
        file_storage.filename,
        file_type,
        len(candidates),
        uploaded_by=uploaded_by,
        stored_filename=stored_path.name,
        file_path=str(stored_path),
    )
    for index, candidate in enumerate(candidates, start=1):
        source_code = candidate["employee_code"]
        candidate["source_employee_code"] = source_code
        candidate["employee_code"] = f"UP{upload_id}-{index}"
    upsert_employees_from_upload(candidates, upload_id)
    return {"upload_id": upload_id, "row_count": len(candidates)}


def read_dataset_file(path):
    suffix = Path(path).suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path), "csv"
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path), "excel"
    raise ValueError("Unsupported employee file type.")


def activate_dataset(upload_id):
    ensure_upload_schema()
    _rebuild_dataset_records(upload_id)
    activate_dataset_upload(upload_id)
    return get_dataset_upload(upload_id)


def delete_dataset(upload_id):
    ensure_upload_schema()
    upload = delete_dataset_upload(upload_id)
    file_path = upload.get("file_path")
    if file_path:
        path = Path(file_path)
        try:
            resolved = path.resolve()
            upload_root = config.DATASET_UPLOAD_DIR.resolve()
            if upload_root in resolved.parents or resolved == upload_root:
                resolved.unlink(missing_ok=True)
        except FileNotFoundError:
            pass
    return upload


def process_jd_upload(file_storage, uploaded_by=None):
    ensure_upload_schema()
    validate_jd_file(file_storage.filename)
    text = extract_pdf_text(file_storage)
    if not text.strip():
        raise ValueError("No readable text found in the PDF. Please upload a text-based JD PDF.")

    skill_vocab = _candidate_skill_vocab()
    requirements = parse_project_requirements(text, skill_vocab=skill_vocab)
    requirements["education"] = extract_education_requirements(text)
    requirements["keywords"] = extract_keywords(text)

    jd_id = create_jd_upload(file_storage.filename, text[:50000], requirements, uploaded_by)
    matches = match_candidates(requirements)
    for match in matches:
        save_jd_match(jd_id, match["employee_id"], match["match_score"], match["breakdown"])
    return {"jd_upload_id": jd_id, "requirements": requirements, "matches": matches}


def extract_pdf_text(file_storage):
    reader = PdfReader(file_storage)
    chunks = []
    for page in reader.pages:
        chunks.append(page.extract_text() or "")
    return "\n".join(chunks)


def extract_project_document_text(file_storage):
    suffix = validate_project_doc_file(file_storage.filename)
    if suffix == ".pdf":
        return extract_pdf_text(file_storage)
    if suffix == ".docx":
        doc = Document(file_storage)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    if suffix == ".doc":
        return extract_legacy_doc_text(file_storage.read())
    return file_storage.read().decode("utf-8", errors="ignore")


def extract_legacy_doc_text(data):
    chunks = []
    for encoding in ("utf-16le", "latin-1"):
        decoded = data.decode(encoding, errors="ignore").replace("\x00", " ")
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


def project_requirements_from_document(file_storage):
    text = extract_project_document_text(file_storage)
    if not text.strip():
        raise ValueError("No readable text found in the uploaded project document.")
    requirements = parse_project_requirements(text, skill_vocab=_candidate_skill_vocab())
    requirements["education"] = extract_education_requirements(text)
    requirements["keywords"] = extract_keywords(text)
    requirements["description"] = text[:5000]
    requirements["suggested_name"] = _suggest_project_name(text)
    return requirements


def match_candidates(requirements):
    candidates = get_candidate_records(active_only=True)
    matches = []
    for candidate in candidates:
        score, breakdown = score_candidate(candidate, requirements)
        matches.append({
            "employee_id": candidate["id"],
            "employee_code": candidate.get("employee_code"),
            "name": candidate.get("name") or f"Candidate {candidate['id']}",
            "email": candidate.get("email") or "",
            "skills": candidate.get("skills") or "",
            "years_of_experience": int(candidate.get("years_of_experience") or 0),
            "education_level": candidate.get("education_level") or "Unknown",
            "designation": candidate.get("designation") or "",
            "department": candidate.get("department") or "",
            "match_score": score,
            "breakdown": breakdown,
        })
    return sorted(matches, key=lambda item: item["match_score"], reverse=True)


def list_projects():
    ensure_upload_schema()
    return get_projects()


def project_detail(project_id):
    ensure_upload_schema()
    return get_project(project_id)


def save_project_from_form(form, created_by=None, project_id=None):
    ensure_upload_schema()
    name = (form.get("name") or "").strip()
    description = (form.get("description") or "").strip()
    skills = (form.get("required_skills") or "").strip()
    min_experience = _to_int(form.get("min_experience") or 0)
    if not name:
        raise ValueError("Project name is required.")
    if not skills:
        raise ValueError("Required skills are required.")
    if project_id:
        update_project(project_id, name, description, skills, min_experience)
        return project_id
    return create_project(name, description, skills, min_experience, created_by)


def remove_project(project_id):
    ensure_upload_schema()
    return delete_project(project_id)


def match_project(project_id):
    ensure_upload_schema()
    project = get_project(project_id)
    if not project:
        raise ValueError("Project not found.")

    requirements = project_to_requirements(project)
    candidates = get_candidate_records(active_only=True)
    if not candidates:
        raise ValueError("No active uploaded employee file found. Upload and activate an employee file first.")

    clear_project_matches(project_id)
    matches = []
    for candidate in candidates:
        score, breakdown = score_candidate(candidate, requirements, strict_skills=True)
        if score is None:
            continue
        match = {
            "employee_id": candidate["id"],
            "employee_code": candidate.get("employee_code"),
            "name": candidate.get("name") or f"Candidate {candidate['id']}",
            "email": candidate.get("email") or "",
            "skills": candidate.get("skills") or "",
            "years_of_experience": int(candidate.get("years_of_experience") or 0),
            "education_level": candidate.get("education_level") or "Unknown",
            "designation": candidate.get("designation") or "",
            "department": candidate.get("department") or "",
            "match_score": score,
            "breakdown": breakdown,
        }
        matches.append(match)
        save_project_match(project_id, candidate["id"], score, breakdown)
    return sorted(matches, key=lambda item: item["match_score"], reverse=True)


def get_project_matches(project_id):
    ensure_upload_schema()
    return get_matches_for_project(project_id)


def project_to_requirements(project):
    description = project.get("description") or ""
    manual_skills = _split_list(project.get("required_skills") or "")
    parsed = parse_project_requirements(description, skill_vocab=_candidate_skill_vocab())
    skills = sorted(set(manual_skills + parsed.get("skills", [])))
    return {
        "skills": skills,
        "min_experience": int(project.get("min_experience") or parsed.get("min_experience") or 0),
        "education": extract_education_requirements(description),
        "keywords": extract_keywords(description + " " + " ".join(skills)),
    }


def score_candidate(candidate, requirements, strict_skills=False):
    required_skills = {_skill_key(s) for s in requirements.get("skills", [])}
    candidate_skills = {
        _skill_key(s)
        for s in str(candidate.get("skills") or "").split(";")
        if s.strip()
    }
    candidate_skill_names = {
        _skill_key(s): s.strip()
        for s in str(candidate.get("skills") or "").split(";")
        if s.strip()
    }
    required_skill_names = {
        _skill_key(s): str(s).strip()
        for s in requirements.get("skills", [])
        if str(s).strip()
    }
    matched_keys = required_skills & candidate_skills
    missing_keys = required_skills - candidate_skills
    matched_skills = sorted(candidate_skill_names.get(k, required_skill_names.get(k, k)) for k in matched_keys)
    missing_skills = sorted(required_skill_names.get(k, k) for k in missing_keys)
    if strict_skills and missing_skills:
        return None, {
            "skill_score": 0,
            "experience_score": 0,
            "education_score": 0,
            "keyword_score": 0,
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "keyword_hits": [],
        }
    skill_score = len(matched_skills) / max(len(required_skills), 1)

    min_exp = int(requirements.get("min_experience") or 0)
    candidate_exp = int(candidate.get("years_of_experience") or 0)
    experience_score = 1.0 if min_exp <= 0 else min(1.0, candidate_exp / max(min_exp, 1))

    required_education = requirements.get("education") or []
    education_text = str(candidate.get("education_level") or "").lower()
    if required_education:
        education_score = 1.0 if any(level in education_text for level in required_education) else 0.35
    else:
        education_score = 1.0

    keywords = set(requirements.get("keywords") or [])
    candidate_text = " ".join([
        str(candidate.get("name") or ""),
        str(candidate.get("designation") or ""),
        str(candidate.get("department") or ""),
        str(candidate.get("education_level") or ""),
        str(candidate.get("skills") or ""),
    ]).lower()
    keyword_hits = sorted(k for k in keywords if k in candidate_text)
    keyword_score = len(keyword_hits) / max(len(keywords), 1)

    weighted_score = (
        0.45 * skill_score +
        0.20 * experience_score +
        0.15 * education_score +
        0.20 * keyword_score
    )
    breakdown = {
        "skill_score": round(skill_score * 100, 1),
        "experience_score": round(experience_score * 100, 1),
        "education_score": round(education_score * 100, 1),
        "keyword_score": round(keyword_score * 100, 1),
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "keyword_hits": keyword_hits,
    }
    return round(weighted_score * 100, 2), breakdown


def dashboard_upload_summary():
    ensure_upload_schema()
    summary = get_upload_summary()
    uploaded = get_uploaded_candidate_count()
    if summary is not None and uploaded:
        summary["uploaded_candidates"] = uploaded["cnt"]
        active = get_active_dataset_upload()
        summary["active_dataset"] = active["filename"] if active else None
        summary["active_dataset_id"] = active["id"] if active else None
        summary["active_row_count"] = active["row_count"] if active else 0
    datasets = get_dataset_uploads(limit=5)
    jds = get_jd_uploads(limit=5)
    return summary, datasets, jds


def list_dataset_uploads(limit=100):
    ensure_upload_schema()
    return get_dataset_uploads(limit=limit)


def get_jd_matches(jd_upload_id):
    ensure_upload_schema()
    return get_matches_for_jd(jd_upload_id)


def _row_to_candidate(row, index):
    values = {_normalize_col(col): row[col] for col in row.index}

    def get_value(target, default=""):
        for alias in DATASET_COLUMN_ALIASES[target]:
            key = _normalize_col(alias)
            if key in values and pd.notna(values[key]):
                return values[key]
        return default

    email = str(get_value("email", "")).strip()
    raw_code = str(get_value("employee_code", "")).strip()
    if raw_code:
        employee_code = raw_code
    elif email:
        employee_code = "UPL-" + hashlib.sha1(email.lower().encode("utf-8")).hexdigest()[:12]
    else:
        employee_code = f"UPL-ROW-{index + 1}"

    return {
        "employee_code": employee_code,
        "name": str(get_value("name", f"Candidate {index + 1}")).strip(),
        "email": email,
        "department": str(get_value("department", "Uploaded")).strip() or "Uploaded",
        "designation": str(get_value("designation", "Candidate")).strip() or "Candidate",
        "years_of_experience": _to_int(get_value("years_of_experience", 0)),
        "education_level": str(get_value("education_level", "Unknown")).strip() or "Unknown",
        "skills": _split_list(get_value("skills", "")),
        "certifications": _split_list(get_value("certifications", "")),
        "performance_score": 3,
        "projects_handled": 0,
        "satisfaction_score": 3.0,
    }


def _candidate_skill_vocab():
    vocab = set()
    for row in get_candidate_records(active_only=True):
        vocab.update(_split_list(row.get("skills") or ""))
    return sorted(vocab)


def _save_uploaded_dataset_file(file_storage, suffix):
    config.DATASET_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_stem = Path(file_storage.filename).stem.replace(" ", "_")
    digest = hashlib.sha1(f"{file_storage.filename}-{time.time()}".encode("utf-8")).hexdigest()[:10]
    filename = f"{safe_stem}_{digest}{suffix}"
    stored_path = config.DATASET_UPLOAD_DIR / filename
    file_storage.save(stored_path)
    return stored_path


def _rebuild_dataset_records(upload_id):
    upload = get_dataset_upload(upload_id)
    if not upload or not upload.get("file_path"):
        return
    path = Path(upload["file_path"])
    if not path.exists():
        return
    df, _ = read_dataset_file(path)
    candidates = [_row_to_candidate(row, i) for i, row in df.iterrows()]
    for index, candidate in enumerate(candidates, start=1):
        candidate["source_employee_code"] = candidate["employee_code"]
        candidate["employee_code"] = f"UP{upload_id}-{index}"
    clear_dataset_employees(upload_id)
    upsert_employees_from_upload(candidates, upload_id)
    update_dataset_row_count(upload_id, len(candidates))


def _split_list(value):
    if pd.isna(value):
        return []
    return [item.strip() for item in re.split(r"[;,|]", str(value)) if item.strip()]


def _normalize_col(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _to_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        match = re.search(r"\d+", str(value))
        return int(match.group()) if match else 0


def extract_education_requirements(text):
    text_lower = text.lower()
    return sorted({level for level in EDUCATION_LEVELS if level in text_lower})


def extract_keywords(text, limit=20):
    words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9+#.-]{2,}\b", text.lower())
    counts = {}
    for word in words:
        if word in STOPWORDS or word.isdigit():
            continue
        counts[word] = counts.get(word, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    return [word for word, _ in ranked[:limit]]


def _suggest_project_name(text):
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if first_line:
        return first_line[:80]
    return "Uploaded Project"


def _skill_key(skill):
    aliases = {
        "powerbi": "powerbi",
        "powerbidesktop": "powerbi",
        "machinelearning": "machinelearning",
        "ml": "machinelearning",
        "naturallanguageprocessing": "nlp",
        "llm": "nlp",
        "node": "nodejs",
        "nodejs": "nodejs",
        "reactjs": "react",
        "postgres": "postgresql",
        "googlecloud": "gcp",
    }
    return normalize_skill_key(skill)
