"""
Skill Gap Analysis Engine
Compares employee skills vs target role requirements.
"""
from src.db import repository
from src.utils.skills import normalize_skill_key


LEVEL_ORDER = {"beginner": 1, "intermediate": 2, "advanced": 3, "expert": 4}


def analyze_skill_gap(employee_id, role_id):
    employee = repository.get_employee_by_id(employee_id)
    role = repository.get_role_with_skills(role_id)
    if not employee or not role:
        return None

    emp_skills = set()
    if employee.get("skills"):
        emp_skills = {normalize_skill_key(s) for s in employee["skills"].split(";") if s.strip()}

    required = []
    desired = []
    matched = []
    gaps = []
    gap_details = []

    for rs in role.get("skills", []):
        skill_name = rs["name"]
        skill_lower = normalize_skill_key(skill_name)
        entry = {
            "skill": skill_name,
            "is_required": bool(rs["is_required"]),
            "min_level": rs["min_level"],
            "category": rs.get("category", "technical"),
        }
        if rs["is_required"]:
            required.append(skill_name)
        else:
            desired.append(skill_name)

        if skill_lower in emp_skills:
            matched.append(entry)
        else:
            gaps.append(entry)
            severity = "high" if rs["is_required"] else "medium"
            gap_details.append({
                "skill": skill_name,
                "severity": severity,
                "min_level": rs["min_level"],
                "recommendations": _get_learning_recommendations(skill_name),
            })

    req_matched = sum(1 for g in matched if any(g["skill"] == r for r in required))
    gap_severity = round(
        (len([g for g in gaps if g["is_required"]]) / max(len(required), 1)) * 100, 1
    )
    match_pct = round(
        (req_matched / max(len(required), 1)) * 100, 1
    )

    return {
        "employee_id": employee_id,
        "employee_code": employee.get("employee_code"),
        "role_id": role_id,
        "role_name": role["name"],
        "match_percentage": match_pct,
        "gap_severity_score": gap_severity,
        "required_skills": required,
        "desired_skills": desired,
        "matched_skills": [m["skill"] for m in matched],
        "missing_skills": [g["skill"] for g in gaps],
        "gap_details": gap_details,
    }


def _get_learning_recommendations(skill_name):
    resources = repository.get_learning_for_skill(skill_name)
    if resources:
        return [
            {"title": r["title"], "source": r["source"], "url": r.get("url"), "hours": r.get("duration_hours")}
            for r in resources[:5]
        ]
    return [
        {"title": f"{skill_name} Fundamentals", "source": "youtube", "url": f"https://youtube.com/results?search_query={skill_name}+tutorial"},
        {"title": f"{skill_name} Certification Prep", "source": "external_cert", "url": None},
    ]


def analyze_gap_from_skill_lists(employee_skills, role_required, role_desired=None):
    """Pure function gap analysis without DB."""
    role_desired = role_desired or []
    emp_set = {normalize_skill_key(s) for s in employee_skills}
    req_set = {normalize_skill_key(s) for s in role_required}
    des_set = {normalize_skill_key(s) for s in role_desired}

    matched = sorted(req_set & emp_set)
    missing = sorted(req_set - emp_set)
    missing_desired = sorted(des_set - emp_set)

    return {
        "matched_skills": [s.title() for s in matched],
        "missing_skills": [s.title() for s in missing],
        "missing_desired": [s.title() for s in missing_desired],
        "match_percentage": round(len(matched) / max(len(req_set), 1) * 100, 1),
        "gap_severity_score": round(len(missing) / max(len(req_set), 1) * 100, 1),
    }
