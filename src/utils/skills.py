"""Shared skill parsing and comparison helpers."""
import re
import unicodedata


SKILL_KEY_ALIASES = {
    "powerbi": "powerbi",
    "powerbidesktop": "powerbi",
    "msbi": "powerbi",
    "machinelearning": "machinelearning",
    "ml": "machinelearning",
    "artificialintelligence": "machinelearning",
    "naturallanguageprocessing": "nlp",
    "largelanguagemodel": "nlp",
    "largelanguagemodels": "nlp",
    "llm": "nlp",
    "node": "nodejs",
    "nodejs": "nodejs",
    "reactjs": "react",
    "react": "react",
    "postgres": "postgresql",
    "postgresql": "postgresql",
    "googlecloud": "gcp",
    "googlecloudplatform": "gcp",
    "gcp": "gcp",
    "amazonwebservices": "aws",
    "awscloud": "aws",
    "microsoftazure": "azure",
    "scikitlearn": "sklearn",
    "scikit": "sklearn",
    "sklearn": "sklearn",
    "fastapi": "fastapi",
    "fastapiframework": "fastapi",
    "fastapiwebframework": "fastapi",
    "datapreprocessing": "datapreprocessing",
    "dataprep": "datapreprocessing",
    "preprocessing": "datapreprocessing",
    "featureengineering": "featureengineering",
    "featureextraction": "featureengineering",
    "featureselection": "featureengineering",
    "exploratorydataanalysis": "eda",
    "eda": "eda",
}


def normalize_skill_key(value):
    """Return a case-, spacing-, and punctuation-insensitive skill identity."""
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    key = re.sub(r"[^a-z0-9+#]", "", text)
    return SKILL_KEY_ALIASES.get(key, key)


def split_skills(value):
    """Split common skill-list formats while preserving display spelling."""
    if value is None:
        return []
    return [part.strip() for part in re.split(r"[;,|]", str(value)) if part.strip()]


def skill_key_set(values):
    if isinstance(values, str):
        values = split_skills(values)
    return {normalize_skill_key(value) for value in (values or []) if normalize_skill_key(value)}


def contains_all_skills(candidate_skills, required_skills):
    return skill_key_set(required_skills).issubset(skill_key_set(candidate_skills))
