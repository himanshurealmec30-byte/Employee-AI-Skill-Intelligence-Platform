import pandas as pd
from src.utils.skills import skill_key_set
import numpy as np

def evaluate_recommendations(recommendations_df, query_skills):
    """
    Evaluates recommendation quality based on coverage, similarity, performance, and diversity.
    
    Args:
        recommendations_df (pd.DataFrame): DataFrame returned by the recommender.
        query_skills (str): Semicolon-separated string of query skills.
        
    Returns:
        dict: Evaluation metrics dictionary.
    """
    metrics = {
        'count': 0,
        'avg_similarity': 0.0,
        'skill_coverage': 0.0,
        'avg_experience': 0.0,
        'avg_performance': 0.0,
        'dept_diversity': 0.0,
        'title_diversity': 0.0
    }
    
    if recommendations_df.empty:
        return metrics
    
    n_recs = len(recommendations_df)
    metrics['count'] = n_recs
    
    # 1. Average Skill Similarity
    metrics['avg_similarity'] = recommendations_df['Skill_Similarity'].mean()
    
    # 2. Skill Coverage (Recall)
    # Parse query skills into a set of lowercased tokens
    query_set = skill_key_set(query_skills)
    if len(query_set) > 0:
        covered_skills = set()
        for idx, row in recommendations_df.iterrows():
            emp_skills = skill_key_set(row['Skills'])
            covered_skills.update(emp_skills.intersection(query_set))
        metrics['skill_coverage'] = len(covered_skills) / len(query_set)
    else:
        metrics['skill_coverage'] = 1.0
        
    # 3. Average Experience and Performance
    metrics['avg_experience'] = recommendations_df['Years_of_Experience'].mean()
    metrics['avg_performance'] = recommendations_df['Performance_Score'].mean()
    
    # 4. Diversity Metrics
    # Dept diversity = ratio of unique depts to total recommendations
    unique_depts = recommendations_df['Department'].nunique()
    metrics['dept_diversity'] = unique_depts / n_recs if n_recs > 0 else 0.0
    
    # Title diversity = ratio of unique job titles to total recommendations
    unique_titles = recommendations_df['Job_Title'].nunique()
    metrics['title_diversity'] = unique_titles / n_recs if n_recs > 0 else 0.0
    
    return metrics
