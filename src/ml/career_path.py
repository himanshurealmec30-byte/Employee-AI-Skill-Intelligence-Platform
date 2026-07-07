"""
Career Path Recommendation using content-based filtering and skill similarity.
"""
from src.nlp.skill_embedder import SkillEmbedder
from src.ml.skill_gap import analyze_gap_from_skill_lists
import config


def recommend_career_paths(employee_skills, current_role=None, role_definitions=None, top_n=5):
    """
    Suggest future career paths based on skill overlap with target roles.
    """
    if role_definitions is None:
        from database.seed import ROLE_DEFINITIONS
        role_definitions = ROLE_DEFINITIONS

    paths = []
    for role_name, spec in role_definitions.items():
        if current_role and role_name.lower() == current_role.lower():
            continue

        gap = analyze_gap_from_skill_lists(
            employee_skills,
            spec["required"],
            spec.get("desired", []),
        )
        readiness = gap["match_percentage"]
        transition_score = readiness * 0.7 + (100 - gap["gap_severity_score"]) * 0.3

        paths.append({
            "target_role": role_name,
            "readiness_percentage": readiness,
            "transition_score": round(transition_score, 1),
            "matched_skills": gap["matched_skills"],
            "skills_to_develop": gap["missing_skills"] + gap["missing_desired"],
            "roadmap_steps": _build_roadmap(gap["missing_skills"], role_name),
        })

    paths.sort(key=lambda x: x["transition_score"], reverse=True)
    return paths[:top_n]


def _build_roadmap(missing_skills, role_name):
    steps = []
    for i, skill in enumerate(missing_skills[:5], 1):
        steps.append({
            "step": i,
            "action": f"Complete {skill} training module",
            "skill": skill,
            "estimated_weeks": 2 + (i - 1),
        })
    if not steps:
        steps.append({
            "step": 1,
            "action": f"Apply for {role_name} internal mobility program",
            "skill": None,
            "estimated_weeks": 4,
        })
    return steps
