import pandas as pd
import numpy as np
import os
import sys

# Ensure parent directory is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from nlp.similarity import SkillSimilarityModel
from src.utils.skills import normalize_skill_key

class RecommendationEngine:
    """
    ML/Data Science component for scoring, ranking, and generating explanations 
    for recommended employees.
    """
    def __init__(self, df):
        self.df = df.copy()
        self.similarity_model = SkillSimilarityModel()
        if not self.df.empty and 'Skills' in self.df:
            self.similarity_model.fit(self.df['Skills'])
        
    def score_experience(self, employee_exp, req_exp):
        """Calculates experience score based on required experience."""
        if req_exp <= 0:
            return 1.0
        if employee_exp >= req_exp:
            return 1.0
        return float(employee_exp / req_exp)
        
    def score_certifications(self, employee_certs, req_certs):
        """Calculates certification score based on requirements."""
        if not req_certs:
            # Fallback: reward employees holding certifications overall
            n_certs = len(employee_certs)
            return float(min(1.0, n_certs / 2.0))
            
        # Match certifications case-insensitively
        emp_certs_lower = [c.lower().strip() for c in employee_certs]
        req_certs_lower = [c.lower().strip() for c in req_certs]
        
        matches = [c for c in req_certs_lower if any(c in ec or ec in c for ec in emp_certs_lower)]
        return float(len(matches) / len(req_certs_lower))
        
    def generate_explanation(self, row, req_skills, req_exp, req_certs, 
                             w_skill, w_exp, w_perf, w_cert):
        """
        Generates structured text explaining the composite recommendation score.
        """
        emp_skills_set = {normalize_skill_key(s) for s in row['Parsed_Skills']}
        req_skills_set = {normalize_skill_key(s) for s in req_skills}
        
        # Skill overlaps
        matched_skills = sorted(list(emp_skills_set.intersection(req_skills_set)))
        missing_skills = sorted(list(req_skills_set.difference(emp_skills_set)))
        
        # Skill explanation
        skill_pct = row['Skill_Similarity'] * 100
        skill_exp = f"{len(matched_skills)}/{len(req_skills)} skills matched ({skill_pct:.1f}% similarity)."
        
        # Experience explanation
        emp_exp = row['Years_of_Experience']
        exp_score = self.score_experience(emp_exp, req_exp)
        if req_exp > 0:
            if emp_exp >= req_exp:
                exp_exp = f"Requirement satisfied: has {emp_exp} years (required {req_exp} years)."
            else:
                exp_exp = f"Under-experienced: has {emp_exp} years (required {req_exp} years, experience score {exp_score:.0%})."
        else:
            exp_exp = f"No minimum experience required (candidate has {emp_exp} years)."
            
        # Performance explanation
        emp_perf = row['Performance_Score']
        perf_pct = emp_perf / 5.0
        perf_exp = f"High performance: rated {emp_perf}/5 (performance score {perf_pct:.0%})."
        
        # Certification explanation
        emp_certs = row['Parsed_Certifications']
        cert_score = self.score_certifications(emp_certs, req_certs)
        if req_certs:
            cert_exp = f"Holds relevant certifications: {len(emp_certs)} owned, certification match is {cert_score:.0%}."
        else:
            cert_exp = f"Holds {len(emp_certs)} general certification(s) (general reward score {cert_score:.0%})."
            
        # Composite score calculation breakdown
        skill_contrib = w_skill * row['Skill_Similarity']
        exp_contrib = w_exp * exp_score
        perf_contrib = w_perf * (emp_perf / 5.0)
        cert_contrib = w_cert * cert_score
        
        breakdown_text = (
            f"Composite Score Breakdown:\n"
            f"- Skill Match: {skill_contrib:.1%} (Weight {w_skill:.0%})\n"
            f"- Experience Match: {exp_contrib:.1%} (Weight {w_exp:.0%})\n"
            f"- Performance Score: {perf_contrib:.1%} (Weight {w_perf:.0%})\n"
            f"- Certification Match: {cert_contrib:.1%} (Weight {w_cert:.0%})\n"
            f"Total Match Score: {row['Final_Score']:.1%}"
        )
        
        return {
            "matched_skills": [s.capitalize() for s in matched_skills],
            "missing_skills": [s.capitalize() for s in missing_skills],
            "experience_statement": exp_exp,
            "performance_statement": perf_exp,
            "certification_statement": cert_exp,
            "skill_statement": skill_exp,
            "breakdown": breakdown_text
        }

    def get_recommendations(self, 
                            requirements, 
                            w_skill=0.40, 
                            w_experience=0.25, 
                            w_performance=0.20, 
                            w_certifications=0.15, 
                            departments=None, 
                            job_titles=None,
                            limit=10):
        """
        Recommends top employees based on NLP-extracted requirements and weights.
        
        Args:
            requirements (dict): Output from nlp.extractor.parse_project_requirements.
            w_skill (float): Weight for skill similarity (default 0.40)
            w_experience (float): Weight for experience score (default 0.25)
            w_performance (float): Weight for performance (default 0.20)
            w_certifications (float): Weight for certifications (default 0.15)
            departments (list): Optional list of departments to filter.
            job_titles (list): Optional list of job titles to filter.
            limit (int): Number of recommendations to return (default 10).
            
        Returns:
            pd.DataFrame: Recommended employees, ranked, with an extra column 'Explanation'.
        """
        req_skills = requirements.get("skills", [])
        req_exp = requirements.get("min_experience", 0)
        req_certs = requirements.get("certifications", [])
        
        if not req_skills:
            return pd.DataFrame() # Can't match without skills
            
        temp_df = self.df.copy()
        if temp_df.empty:
            return pd.DataFrame()
        
        # Apply filters
        if departments:
            depts_lower = [d.lower().strip() for d in departments]
            temp_df = temp_df[temp_df['Department'].str.lower().isin(depts_lower)]
        if job_titles:
            titles_lower = [t.lower().strip() for t in job_titles]
            temp_df = temp_df[temp_df['Job_Title'].str.lower().isin(titles_lower)]
            
        if temp_df.empty:
            return pd.DataFrame()
            
        # 1. Compute NLP Skill Similarity (40% default)
        similarities = self.similarity_model.calculate_similarity(req_skills, temp_df['Skills'])
        temp_df['Skill_Similarity'] = similarities
        
        # 2. Compute Experience Score (25% default)
        exp_scores = temp_df['Years_of_Experience'].apply(lambda x: self.score_experience(x, req_exp))
        
        # 3. Compute Performance Score (20% default)
        perf_scores = temp_df['Performance_Score'] / 5.0
        
        # 4. Compute Certifications Score (15% default)
        cert_scores = temp_df['Parsed_Certifications'].apply(lambda x: self.score_certifications(x, req_certs))
        
        # Compute Final Score
        # Ensure weights sum to 1.0
        w_sum = w_skill + w_experience + w_performance + w_certifications
        if w_sum > 0:
            n_w_skill = w_skill / w_sum
            n_w_exp = w_experience / w_sum
            n_w_perf = w_performance / w_sum
            n_w_cert = w_certifications / w_sum
        else:
            n_w_skill, n_w_exp, n_w_perf, n_w_cert = 0.40, 0.25, 0.20, 0.15
            
        temp_df['Final_Score'] = (
            n_w_skill * temp_df['Skill_Similarity'] +
            n_w_exp * exp_scores +
            n_w_perf * perf_scores +
            n_w_cert * cert_scores
        )
        
        # Rank employees
        temp_df = temp_df.sort_values(by=['Final_Score', 'Performance_Score', 'Years_of_Experience'], ascending=False)
        top_df = temp_df.head(limit).copy()
        
        # Generate explanations for top recommended employees
        explanations = []
        for idx, row in top_df.iterrows():
            exp = self.generate_explanation(
                row, req_skills, req_exp, req_certs,
                n_w_skill, n_w_exp, n_w_perf, n_w_cert
            )
            explanations.append(exp)
            
        top_df['Explanation'] = explanations
        
        return top_df
