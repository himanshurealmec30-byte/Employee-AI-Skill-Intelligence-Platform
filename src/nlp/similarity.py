import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from src.utils.skills import normalize_skill_key


def _semicolon_skill_analyzer(text):
    return [normalize_skill_key(s) for s in str(text).split(";") if normalize_skill_key(s)]


class SkillSimilarityModel:
    """
    NLP component for representing employee skills in vector space and 
    computing similarity against project queries.
    """
    def __init__(self):
        # Custom semicolon tokenizer to keep technical phrases intact
        # e.g., "React.js" is one token, not "React" and "js"
        self.vectorizer = TfidfVectorizer(analyzer=_semicolon_skill_analyzer)
        self.fitted = False
        
    def fit(self, employee_skills_series):
        """Fits TF-IDF model on employee skills dataset."""
        if employee_skills_series.empty:
            raise ValueError("Employee skills series is empty.")
        self.vectorizer.fit(employee_skills_series)
        self.fitted = True
        
    def calculate_similarity(self, query_skills_list, employee_skills_series):
        """
        Calculates cosine similarity between query skills and employee skills.
        
        Args:
            query_skills_list (list): List of query skill strings (e.g. ['python', 'sql'])
            employee_skills_series (pd.Series): Semicolon-separated employee skills.
            
        Returns:
            np.ndarray: Array of similarity scores.
        """
        if not self.fitted:
            self.fit(employee_skills_series)
            
        # Convert query skills list to a semicolon-separated string to match TF-IDF format
        query_str = ";".join(query_skills_list)
        
        # Transform both query and employees
        query_vec = self.vectorizer.transform([query_str])
        emp_matrix = self.vectorizer.transform(employee_skills_series)
        
        # Calculate Cosine Similarity
        similarity_scores = cosine_similarity(query_vec, emp_matrix).flatten()
        return similarity_scores
