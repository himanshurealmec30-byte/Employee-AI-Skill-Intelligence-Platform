"""Unified recommendation service using trained ML/NLP models."""
import pandas as pd
import re
import math
from pathlib import Path
from urllib.parse import quote_plus

import config
from src.preprocessing import preprocess_data
from src.recommendation.engine import RecommendationEngine
from src.nlp.skill_embedder import SkillEmbedder
from src.ml.readiness_trainer import ReadinessModelTrainer
from src.ml.skill_gap import analyze_gap_from_skill_lists
from src.ml.career_path import recommend_career_paths
from database.seed import ROLE_DEFINITIONS
from src.utils.skills import normalize_skill_key, split_skills


SERVICE_COLUMNS = [
    "Employee_ID",
    "Employee_Code",
    "Display_Employee_ID",
    "Department",
    "Job_Title",
    "Years_of_Experience",
    "Education_Level",
    "Performance_Score",
    "Projects_Handled",
    "Employee_Satisfaction_Score",
    "Certifications",
    "Skills",
    "Name",
    "Email",
    "Hire_Date",
    "Parsed_Skills",
    "Parsed_Certifications",
]


def _empty_service_dataframe():
    return pd.DataFrame({column: pd.Series(dtype="object") for column in SERVICE_COLUMNS})


def _display_skill(skill):
    text = str(skill or "").strip()
    compact = normalize_skill_key(text)
    labels = {
        "powerbi": "Power BI",
        "sql": "SQL",
        "python": "Python",
        "aws": "AWS",
        "gcp": "GCP",
        "azure": "Azure",
        "nlp": "NLP",
        "machinelearning": "Machine Learning",
        "deeplearning": "Deep Learning",
        "nodejs": "Node.js",
        "sklearn": "Scikit-Learn",
    }
    return labels.get(compact, text or compact.title())


def _learning_links(skill):
    label = _display_skill(skill)
    query = quote_plus(label)
    return [
        {
            "title": f"{label} tutorial videos",
            "source": "YouTube",
            "url": f"https://www.youtube.com/results?search_query={query}+tutorial",
        },
        {
            "title": f"{label} courses",
            "source": "Coursera",
            "url": f"https://www.coursera.org/search?query={query}",
        },
        {
            "title": f"{label} certification training",
            "source": "Udemy",
            "url": f"https://www.udemy.com/courses/search/?q={query}",
        },
    ]


def _rows_to_service_dataframe(rows):
    records = []
    for row in rows:
        employee_id = row.get("id") or row.get("employee_id")
        employee_code = str(row.get("employee_code") or employee_id)
        records.append({
            "Employee_ID": int(employee_id),
            "Employee_Code": employee_code,
            "Display_Employee_ID": _display_employee_id(employee_code, employee_id),
            "Department": row.get("department") or "Uploaded",
            "Job_Title": row.get("designation") or "Employee",
            "Years_of_Experience": int(row.get("years_of_experience") or 0),
            "Education_Level": row.get("education_level") or "Unknown",
            "Performance_Score": int(row.get("performance_score") or 3),
            "Projects_Handled": int(row.get("projects_handled") or 0),
            "Employee_Satisfaction_Score": float(row.get("satisfaction_score") or 3.0),
            "Certifications": row.get("certifications") or "",
            "Skills": row.get("skills") or "",
            "Hire_Date": pd.NaT,
        })
    df = pd.DataFrame(records)
    if df.empty:
        return _empty_service_dataframe()
    df["Parsed_Skills"] = df["Skills"].fillna("").apply(lambda x: [s.strip() for s in str(x).split(";") if s.strip()])
    df["Parsed_Certifications"] = df["Certifications"].fillna("").apply(lambda x: [c.strip() for c in str(x).split(",") if c.strip()])
    return df


def _display_employee_id(employee_code, fallback):
    match = re.match(r"^UP\d+-(\d+)$", str(employee_code or ""))
    if match:
        return int(match.group(1))
    try:
        return int(employee_code)
    except (TypeError, ValueError):
        return int(fallback)


def _skill_key(skill):
    return normalize_skill_key(skill)


def _split_skill_query(value):
    return split_skills(value)


class TalentBeaconService:
    """Central service for ML/NLP-powered talent intelligence."""

    def __init__(self, user_id=None):
        self.user_id = user_id
        self._initialized = False

    def initialize(self, use_db=False, user_id=None):
        if self._initialized:
            return
        if user_id is not None:
            self.user_id = user_id
        self.use_db = use_db
        self.df = self._load_active_dataframe()

        if Path(config.TFIDF_SKILL_MODEL_PATH).exists():
            self.embedder = SkillEmbedder.load()
        else:
            self.embedder = SkillEmbedder()
            if not self.df.empty:
                self.embedder.train(self.df["Skills"])
        if not self.df.empty:
            # Keep NLP vocabulary aligned with the currently active upload.
            self.embedder.train(self.df["Skills"])

        if Path(config.READINESS_MODEL_PATH).exists():
            self.readiness_trainer = ReadinessModelTrainer.load()
        else:
            self.readiness_trainer = None

        self.engine = RecommendationEngine(self.df)
        self._initialized = True

    def reload(self):
        self._initialized = False
        self.initialize()

    def _load_active_dataframe(self):
        try:
            from src.services.workspace_service import load_active_employee_df
            df = load_active_employee_df(user_id=self.user_id)
            if not df.empty:
                return df
        except Exception:
            pass
        return _empty_service_dataframe()

    def match_employees_to_role(self, role_name, limit=10):
        spec = ROLE_DEFINITIONS.get(role_name)
        if not spec or self.df.empty:
            return []
        requirements = {
            "skills": spec["required"] + spec.get("desired", []),
            "min_experience": 2,
            "certifications": [],
        }
        results = self.engine.get_recommendations(requirements, limit=limit)
        if results.empty:
            return []

        output = []
        for _, row in results.iterrows():
            explanation = row.get("Explanation", {})
            score_breakdown = self._recommendation_score_breakdown(row, requirements)
            output.append({
                "employee_id": int(row.get("Display_Employee_ID", row["Employee_ID"])),
                "department": row["Department"],
                "designation": row["Job_Title"],
                "years_of_experience": int(row["Years_of_Experience"]),
                "performance_score": int(row["Performance_Score"]),
                "match_score": round(float(row["Final_Score"]) * 100, 1),
                "skill_similarity": round(float(row["Skill_Similarity"]) * 100, 1),
                "skills": row["Skills"],
                "explanation": explanation,
                "matched_skills": explanation.get("matched_skills", []),
                "missing_skills": explanation.get("missing_skills", []),
                "skill_coverage": round(float(row["Skill_Similarity"]) * 100, 1),
                "score_breakdown": score_breakdown,
            })
        return output

    def match_employees_to_project(self, skills, min_experience=0, certifications=None, limit=10):
        requirements = {
            "skills": skills,
            "min_experience": min_experience,
            "certifications": certifications or [],
        }
        if self.df.empty:
            return []
        required = {_skill_key(skill) for skill in skills if str(skill).strip()}
        if required:
            minimum_matches = max(1, math.ceil(len(required) * 0.60))
            active_df = self.df.copy()
            active_df["_Matched_Skills"] = active_df["Parsed_Skills"].apply(
                lambda values: sorted(required & {_skill_key(s) for s in values})
            )
            active_df = active_df[active_df["_Matched_Skills"].str.len() >= minimum_matches].copy()
        else:
            active_df = self.df
        if min_experience:
            active_df = active_df[active_df["Years_of_Experience"] >= int(min_experience)]
        if active_df.empty:
            return []
        original_engine = self.engine
        try:
            self.engine = RecommendationEngine(active_df)
            results = self.engine.get_recommendations(
                requirements,
                limit=min(len(active_df), max(limit * 10, 100)),
            )
        finally:
            self.engine = original_engine
        if results.empty:
            return []
        output = []
        for _, row in results.iterrows():
            score_breakdown = self._recommendation_score_breakdown(row, requirements)
            output.append({
                "employee_id": int(row.get("Display_Employee_ID", row["Employee_ID"])),
                "db_employee_id": int(row["Employee_ID"]),
                "department": row["Department"],
                "designation": row["Job_Title"],
                "match_score": round(float(row["Final_Score"]) * 100, 1),
                "skills": row["Skills"],
                "matched_skills": sorted(required & {_skill_key(s) for s in row["Parsed_Skills"]}),
                "missing_skills": sorted(required - {_skill_key(s) for s in row["Parsed_Skills"]}),
                "skill_coverage": round(
                    len(required & {_skill_key(s) for s in row["Parsed_Skills"]}) / max(len(required), 1) * 100,
                    1,
                ),
                "score_breakdown": score_breakdown,
            })
        output.sort(key=lambda item: (item["skill_coverage"], item["match_score"]), reverse=True)
        return output[:limit]

    def parse_requirements_nlp(self, text):
        return self.embedder.extract_from_text(text)

    def _recommendation_score_breakdown(self, row, requirements):
        weights = {
            "skills": 40,
            "experience": 25,
            "performance": 20,
            "certifications": 15,
        }
        skill_score = float(row.get("Skill_Similarity") or 0) * 100
        exp_score = self.engine.score_experience(
            float(row.get("Years_of_Experience") or 0),
            int(requirements.get("min_experience") or 0),
        ) * 100
        performance_score = min(max(float(row.get("Performance_Score") or 0) / 5.0, 0), 1) * 100
        cert_score = self.engine.score_certifications(
            row.get("Parsed_Certifications") or [],
            requirements.get("certifications") or [],
        ) * 100
        parts = [
            {"label": "Skills", "score": round(skill_score, 1), "weight": weights["skills"]},
            {"label": "Experience", "score": round(exp_score, 1), "weight": weights["experience"]},
            {"label": "Performance", "score": round(performance_score, 1), "weight": weights["performance"]},
            {"label": "Certifications", "score": round(cert_score, 1), "weight": weights["certifications"]},
        ]
        for part in parts:
            part["contribution"] = round(part["score"] * part["weight"] / 100, 1)
        strengths = []
        limits = []
        if skill_score >= 95:
            strengths.append("all required skills are covered")
        elif skill_score >= 60:
            strengths.append(f"most required skills are covered ({round(skill_score, 1)}%)")
        else:
            limits.append(f"skill coverage is only {round(skill_score, 1)}%")
        if exp_score >= 100:
            strengths.append("experience requirement is satisfied")
        else:
            limits.append(f"experience is below the requirement ({round(exp_score, 1)}% fit)")
        if performance_score >= 80:
            strengths.append("performance rating is strong")
        elif performance_score < 60:
            limits.append("performance rating lowers the score")
        if cert_score >= 80:
            strengths.append("certification fit is strong")
        elif cert_score == 0:
            limits.append("no relevant certification credit was found")
        else:
            limits.append(f"certification fit is partial ({round(cert_score, 1)}%)")
        reason = "The score is based on " + ", ".join(strengths or ["available employee data"])
        if limits:
            reason += ", but " + ", ".join(limits)
        reason += "."
        return {
            "parts": parts,
            "total": round(sum(part["contribution"] for part in parts), 1),
            "formula": "Skills 40% + Experience 25% + Performance 20% + Certifications 15%",
            "reason": reason,
        }

    def _find_employee_row(self, employee_id):
        if self.df.empty:
            return self.df
        employee_id = int(employee_id)
        if "Display_Employee_ID" in self.df:
            row = self.df[self.df["Display_Employee_ID"] == employee_id]
            if not row.empty:
                return row
        row = self.df[self.df["Employee_ID"] == employee_id]
        if not row.empty:
            return row
        if "Employee_Code" in self.df:
            row = self.df[self.df["Employee_Code"].astype(str) == str(employee_id)]
            if not row.empty:
                return row
        return self.df.iloc[0:0]

    def get_skill_gap(self, employee_id, role_name):
        row = self._find_employee_row(employee_id)
        if row.empty:
            return None
        spec = ROLE_DEFINITIONS.get(role_name)
        if not spec:
            return None
        emp_skills = row.iloc[0]["Parsed_Skills"]
        gap = analyze_gap_from_skill_lists(emp_skills, spec["required"], spec.get("desired", []))
        gap["employee_id"] = int(row.iloc[0].get("Display_Employee_ID", employee_id))
        gap["role_name"] = role_name
        gap["learning_recommendations"] = [
            {"title": f"{s} Fundamentals", "source": "internal_lms"}
            for s in gap["missing_skills"][:5]
        ]
        return gap

    def get_readiness_score(self, employee_id, role_name):
        row = self._find_employee_row(employee_id)
        if row.empty:
            return None
        spec = ROLE_DEFINITIONS.get(role_name)
        if not spec:
            return None

        emp_skills = {_skill_key(s) for s in row.iloc[0]["Parsed_Skills"]}
        required = {_skill_key(s) for s in spec["required"]}
        desired = {_skill_key(s) for s in spec.get("desired", [])}

        req_ratio = len(emp_skills & required) / max(len(required), 1)
        des_ratio = len(emp_skills & desired) / max(len(desired), 1) if desired else 0.5

        features = {
            "role_name": role_name,
            "years_of_experience": int(row.iloc[0]["Years_of_Experience"]),
            "performance_score": int(row.iloc[0]["Performance_Score"]),
            "projects_handled": int(row.iloc[0]["Projects_Handled"]),
            "satisfaction_score": float(row.iloc[0]["Employee_Satisfaction_Score"]),
            "num_certifications": len(row.iloc[0]["Parsed_Certifications"]),
            "num_skills": len(row.iloc[0]["Parsed_Skills"]),
            "req_match_ratio": req_ratio,
            "des_match_ratio": des_ratio,
        }

        if self.readiness_trainer:
            skill_vec = self.readiness_trainer.mlb.transform([row.iloc[0]["Parsed_Skills"]])[0]
            for i in range(len(skill_vec)):
                features[f"skill_{i}"] = skill_vec[i]
            score = self.readiness_trainer.predict_readiness(features)
        else:
            score = round(req_ratio * 100, 1)

        return {
            "employee_id": int(row.iloc[0].get("Display_Employee_ID", employee_id)),
            "role_name": role_name,
            "readiness_score": score,
            "ready": score >= 70,
        }

    def get_career_paths(self, employee_id, top_n=5):
        row = self._find_employee_row(employee_id)
        if row.empty:
            return []
        return recommend_career_paths(
            row.iloc[0]["Parsed_Skills"],
            current_role=row.iloc[0]["Job_Title"],
            top_n=top_n,
        )

    def search_employees(self, skill=None, department=None, min_performance=0):
        temp = self.df.copy()
        if temp.empty:
            return []
        required = {_skill_key(s) for s in _split_skill_query(skill)} if skill else set()
        if department:
            temp = temp[temp["Department"].str.lower() == department.lower()]
        if min_performance:
            temp = temp[temp["Performance_Score"] >= min_performance]
        if required:
            minimum_matches = max(1, math.ceil(len(required) * 0.40))
            temp["Matched_Skills"] = temp["Parsed_Skills"].apply(
                lambda values: sorted(required & {_skill_key(s) for s in values})
            )
            temp["Missing_Skills"] = temp["Parsed_Skills"].apply(
                lambda values: sorted(required - {_skill_key(s) for s in values})
            )
            temp["Skill_Match_Count"] = temp["Matched_Skills"].str.len()
            temp["Skill_Match_Total"] = len(required)
            temp = temp[temp["Skill_Match_Count"] >= minimum_matches]
            temp = temp.sort_values(
                ["Skill_Match_Count", "Performance_Score", "Years_of_Experience"],
                ascending=[False, False, False],
            )
        else:
            temp = temp.copy()
            temp["Matched_Skills"] = [[] for _ in range(len(temp))]
            temp["Missing_Skills"] = [[] for _ in range(len(temp))]
            temp["Skill_Match_Count"] = 0
            temp["Skill_Match_Total"] = 0
            temp = temp.sort_values(
                ["Performance_Score", "Years_of_Experience"],
                ascending=[False, False],
            )
        if "Display_Employee_ID" in temp:
            temp = temp.copy()
            temp["Employee_ID"] = temp["Display_Employee_ID"]
        return [self._employee_search_record(row, required) for _, row in temp.head(50).iterrows()]

    def get_employee_intelligence(
        self,
        employee_id,
        role_name=None,
        project_skills=None,
        project_min_experience=0,
        query_skills=None,
    ):
        row_df = self._find_employee_row(employee_id)
        if row_df.empty:
            return None
        row = row_df.iloc[0]
        employee_skills = list(row.get("Parsed_Skills") or [])
        role_gap = None
        if role_name and role_name in ROLE_DEFINITIONS:
            spec = ROLE_DEFINITIONS[role_name]
            role_gap = analyze_gap_from_skill_lists(employee_skills, spec["required"], spec.get("desired", []))
            role_gap["required_skills"] = spec["required"]
            role_gap["desired_skills"] = spec.get("desired", [])
            role_gap["role_name"] = role_name

        project_skills = project_skills or []
        project_gap = self._gap_for_skills(employee_skills, project_skills)
        project_gap["min_experience"] = int(project_min_experience or 0)
        project_gap["experience_ok"] = int(row.get("Years_of_Experience") or 0) >= int(project_min_experience or 0)

        query_gap = self._gap_for_skills(employee_skills, _split_skill_query(query_skills))
        missing = []
        for bucket in (project_gap, role_gap or {}, query_gap):
            for skill in bucket.get("missing_skills", []):
                key = _skill_key(skill)
                if key and key not in {_skill_key(existing) for existing in missing}:
                    missing.append(_display_skill(skill))
        learning = []
        for skill in missing[:6]:
            learning.extend(_learning_links(skill))

        return {
            "employee": self._employee_search_record(row, {_skill_key(s) for s in _split_skill_query(query_skills)}),
            "skills": [_display_skill(skill) for skill in employee_skills],
            "certifications": [str(c).strip() for c in row.get("Parsed_Certifications", []) if str(c).strip()],
            "nlp_analysis": self._nlp_profile_analysis(row, project_skills=project_skills, role_name=role_name),
            "role_gap": role_gap,
            "project_gap": project_gap,
            "query_gap": query_gap,
            "learning_recommendations": learning,
        }

    def _employee_search_record(self, row, required=None):
        required = required or set()
        skills = list(row.get("Parsed_Skills") or _split_skill_query(row.get("Skills", "")))
        existing = {_skill_key(skill) for skill in skills}
        matched = sorted(required & existing)
        missing = sorted(required - existing)
        total = len(required)
        coverage = round(len(matched) / max(total, 1) * 100, 1) if total else 0
        display_id = int(row.get("Display_Employee_ID", row.get("Employee_ID", 0)))
        return {
            "employee_id": display_id,
            "Employee_ID": display_id,
            "db_employee_id": int(row.get("Employee_ID", display_id)),
            "name": str(row.get("Name", f"Employee {display_id}") or f"Employee {display_id}"),
            "Name": str(row.get("Name", f"Employee {display_id}") or f"Employee {display_id}"),
            "email": str(row.get("Email", "") or ""),
            "Email": str(row.get("Email", "") or ""),
            "department": str(row.get("Department", "") or ""),
            "Department": str(row.get("Department", "") or ""),
            "designation": str(row.get("Job_Title", "") or ""),
            "Job_Title": str(row.get("Job_Title", "") or ""),
            "education": str(row.get("Education_Level", "Unknown") or "Unknown"),
            "Education_Level": str(row.get("Education_Level", "Unknown") or "Unknown"),
            "years_of_experience": int(row.get("Years_of_Experience") or 0),
            "Years_of_Experience": int(row.get("Years_of_Experience") or 0),
            "performance_score": int(row.get("Performance_Score") or 0),
            "Performance_Score": int(row.get("Performance_Score") or 0),
            "projects_handled": int(row.get("Projects_Handled") or 0),
            "skills": "; ".join(skills),
            "Skills": "; ".join(skills),
            "matched_skills": [_display_skill(skill) for skill in matched],
            "Matched_Skills": matched,
            "missing_skills": [_display_skill(skill) for skill in missing],
            "Missing_Skills": missing,
            "skill_match_count": len(matched),
            "Skill_Match_Count": len(matched),
            "skill_match_total": total,
            "Skill_Match_Total": total,
            "skill_match_percentage": coverage,
        }

    def _gap_for_skills(self, employee_skills, required_skills):
        required_map = {_skill_key(skill): _display_skill(skill) for skill in required_skills if str(skill).strip()}
        existing = {_skill_key(skill) for skill in employee_skills}
        matched = sorted(required_map[key] for key in required_map if key in existing)
        missing = sorted(required_map[key] for key in required_map if key not in existing)
        return {
            "required_skills": list(required_map.values()),
            "matched_skills": matched,
            "missing_skills": missing,
            "match_percentage": round(len(matched) / max(len(required_map), 1) * 100, 1) if required_map else 0,
        }

    def _nlp_profile_analysis(self, row, project_skills=None, role_name=None):
        skills = list(row.get("Parsed_Skills") or [])
        profile_text = " ".join([
            str(row.get("Name", "")),
            str(row.get("Job_Title", "")),
            str(row.get("Department", "")),
            str(row.get("Education_Level", "")),
            " ".join(skills),
            str(row.get("Certifications", "")),
        ])
        parsed = self.parse_requirements_nlp(profile_text)
        focus_skills = project_skills or []
        if role_name and role_name in ROLE_DEFINITIONS:
            focus_skills = list(dict.fromkeys(focus_skills + ROLE_DEFINITIONS[role_name]["required"]))
        focus_gap = self._gap_for_skills(skills, focus_skills)
        keywords = [
            part for part in re.findall(r"\b[A-Za-z][A-Za-z0-9+#.]{2,}\b", profile_text)
            if part.casefold() not in {"employee", "uploaded", "unknown"}
        ]
        return {
            "extracted_skills": parsed.get("skills") or [_display_skill(skill) for skill in skills],
            "keywords": list(dict.fromkeys(keywords))[:12],
            "semantic_match_percentage": focus_gap["match_percentage"],
            "summary": (
                f"{row.get('Job_Title', 'Employee')} profile with "
                f"{int(row.get('Years_of_Experience') or 0)} years of experience and "
                f"{len(skills)} detected skills."
            ),
        }

    def get_analytics(self):
        if self.df.empty:
            return {
                "total_employees": 0,
                "departments": {},
                "avg_performance": 0,
                "avg_experience": 0,
                "top_skills": [],
                "roles_available": list(ROLE_DEFINITIONS.keys()),
                "needs_upload": True,
            }
        skill_counts = {}
        for skills in self.df["Parsed_Skills"]:
            for s in skills:
                skill_counts[s] = skill_counts.get(s, 0) + 1
        top_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)[:15]
        total_employees = len(self.df)
        departments = self.df["Department"].value_counts().to_dict()
        experience_bands = {
            "0-2 years": int((self.df["Years_of_Experience"] <= 2).sum()),
            "3-5 years": int(self.df["Years_of_Experience"].between(3, 5).sum()),
            "6-10 years": int(self.df["Years_of_Experience"].between(6, 10).sum()),
            "10+ years": int((self.df["Years_of_Experience"] > 10).sum()),
        }

        return {
            "total_employees": total_employees,
            "departments": departments,
            "department_rows": [
                {"name": name, "count": int(count), "percentage": round((int(count) / max(total_employees, 1)) * 100, 1)}
                for name, count in departments.items()
            ],
            "avg_performance": round(float(self.df["Performance_Score"].mean()), 2),
            "avg_experience": round(float(self.df["Years_of_Experience"].mean()), 2),
            "top_skills": [
                {"skill": s, "count": int(c), "percentage": round((int(c) / max(total_employees, 1)) * 100, 1)}
                for s, c in top_skills
            ],
            "experience_bands": experience_bands,
            "experience_rows": [
                {"name": name, "count": int(count), "percentage": round((int(count) / max(total_employees, 1)) * 100, 1)}
                for name, count in experience_bands.items()
            ],
            "roles_available": list(ROLE_DEFINITIONS.keys()),
        }


def get_service(user_id=None):
    svc = TalentBeaconService(user_id=user_id)
    svc.initialize(user_id=user_id)
    return svc


def reload_service(user_id=None):
    svc = TalentBeaconService(user_id=user_id)
    svc.reload()
    return svc
