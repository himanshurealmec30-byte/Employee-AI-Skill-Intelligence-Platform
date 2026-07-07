"""
NLP Skill Embedding & TF-IDF Model Training
Trains and persists TF-IDF vectorizer on employee skill corpus.
"""
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import config
from src.nlp.extractor import DEFAULT_SKILL_VOCAB, SKILL_ALIASES, parse_project_requirements
from src.utils.skills import normalize_skill_key


def _semicolon_skill_analyzer(text):
    """Module-level analyzer so TF-IDF vectorizer can be pickled."""
    return [normalize_skill_key(s) for s in str(text).split(";") if normalize_skill_key(s)]


class SkillEmbedder:
    """Trained NLP model for skill vectorization and semantic matching."""

    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            analyzer=_semicolon_skill_analyzer,
            min_df=1,
            max_features=5000,
        )
        self.skill_vocab = []
        self.fitted = False

    def _skills_to_doc(self, skills_list):
        return ";".join(skills_list)

    def train(self, skills_series: pd.Series, skill_vocab=None):
        """Fit TF-IDF on employee skill documents."""
        docs = skills_series.fillna("").astype(str)
        self.vectorizer.fit(docs)

        if skill_vocab is None:
            all_skills = set()
            for s in skills_series:
                all_skills.update([x.strip() for x in str(s).split(";") if x.strip()])
            self.skill_vocab = sorted(all_skills)
        else:
            self.skill_vocab = sorted(set(skill_vocab))

        self.fitted = True
        return self

    def save(self, tfidf_path=None, vocab_path=None):
        tfidf_path = tfidf_path or config.TFIDF_SKILL_MODEL_PATH
        vocab_path = vocab_path or config.SKILL_VOCAB_PATH
        Path(tfidf_path).parent.mkdir(parents=True, exist_ok=True)
        with open(tfidf_path, "wb") as f:
            pickle.dump(self.vectorizer, f)
        with open(vocab_path, "w", encoding="utf-8") as f:
            json.dump(self.skill_vocab, f, indent=2)

    @classmethod
    def load(cls, tfidf_path=None, vocab_path=None):
        tfidf_path = tfidf_path or config.TFIDF_SKILL_MODEL_PATH
        vocab_path = vocab_path or config.SKILL_VOCAB_PATH
        model = cls()
        with open(tfidf_path, "rb") as f:
            model.vectorizer = pickle.load(f)
        with open(vocab_path, "r", encoding="utf-8") as f:
            model.skill_vocab = json.load(f)
        model.fitted = True
        return model

    def similarity(self, query_skills, employee_skills_series):
        if not self.fitted:
            raise RuntimeError("Model not trained. Call train() or load() first.")
        query_doc = self._skills_to_doc(query_skills)
        query_vec = self.vectorizer.transform([query_doc])
        emp_matrix = self.vectorizer.transform(employee_skills_series.fillna("").astype(str))
        return cosine_similarity(query_vec, emp_matrix).flatten()

    def extract_from_text(self, text):
        """NLP extraction using trained vocabulary."""
        return parse_project_requirements(text, skill_vocab=self.skill_vocab or DEFAULT_SKILL_VOCAB)


def train_nlp_models(df=None, csv_path=None):
    """Train and persist NLP skill embedding model."""
    if df is None:
        from src.preprocessing import preprocess_data
        csv_path = csv_path or str(config.DEFAULT_CSV_PATH)
        df = preprocess_data(csv_path)

    embedder = SkillEmbedder()
    embedder.train(df["Skills"])
    embedder.save()

    # Validation: sample similarity check
    sample_query = ["Python", "SQL", "Machine Learning"]
    sims = embedder.similarity(sample_query, df["Skills"].head(100))
    top_idx = int(np.argmax(sims))

    metrics = {
        "vocabulary_size": len(embedder.skill_vocab),
        "tfidf_features": len(embedder.vectorizer.get_feature_names_out()),
        "alias_count": len(SKILL_ALIASES),
        "sample_top_similarity": float(sims[top_idx]),
        "sample_employee_id": int(df.iloc[top_idx]["Employee_ID"]),
    }
    return embedder, metrics
