import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import MinMaxScaler
import os
from src.utils.skills import normalize_skill_key


def _skill_analyzer(value):
    return [normalize_skill_key(s) for s in str(value).split(';') if normalize_skill_key(s)]

class EmployeeRecommender:
    def __init__(self, df):
        """
        Initializes the recommender engine with a preprocessed DataFrame.
        """
        self.df = df.copy()
        
        # Initialize vectorizer for skills
        # Custom analyzer to split semicolon-separated skills
        self.tfidf = TfidfVectorizer(
            analyzer=_skill_analyzer
        )
        
        # Fit-transform skills to get skill representation matrix
        self.skill_matrix = self.tfidf.fit_transform(self.df['Skills'])
        
        # Normalize numerical columns for scoring
        self.scaler = MinMaxScaler()
        num_cols = ['Years_of_Experience', 'Performance_Score', 'Projects_Handled', 'Employee_Satisfaction_Score']
        
        # Add normalized columns with prefix 'norm_'
        norm_data = self.scaler.fit_transform(self.df[num_cols])
        for i, col in enumerate(num_cols):
            self.df[f'norm_{col}'] = norm_data[:, i]
            
    def get_recommendations(self, 
                            query_skills, 
                            w_skill=0.5, 
                            w_experience=0.2, 
                            w_performance=0.2, 
                            w_projects=0.1, 
                            min_experience=0, 
                            min_performance=1, 
                            departments=None, 
                            job_titles=None,
                            limit=10):
        """
        Recommends employees based on query skills, weights, and filters.
        
        Args:
            query_skills (str): Semicolon-separated skills (e.g., 'python;sql;git')
            w_skill (float): Weight for skill similarity (0 to 1)
            w_experience (float): Weight for experience (0 to 1)
            w_performance (float): Weight for performance score (0 to 1)
            w_projects (float): Weight for number of projects handled (0 to 1)
            min_experience (int): Filter out employees with experience less than this
            min_performance (int): Filter out employees with performance less than this
            departments (list): Filter by specific departments
            job_titles (list): Filter by specific job titles
            limit (int): Number of recommendations to return
            
        Returns:
            pd.DataFrame: Recommended employees ranked by final score.
        """
        temp_df = self.df.copy()
        
        # Apply strict filters first
        if min_experience > 0:
            temp_df = temp_df[temp_df['Years_of_Experience'] >= min_experience]
            
        if min_performance > 1:
            temp_df = temp_df[temp_df['Performance_Score'] >= min_performance]
            
        if departments:
            # Case insensitive match
            departments_lower = [d.lower() for d in departments]
            temp_df = temp_df[temp_df['Department'].str.lower().isin(departments_lower)]
            
        if job_titles:
            # Case insensitive match
            job_titles_lower = [j.lower() for j in job_titles]
            temp_df = temp_df[temp_df['Job_Title'].str.lower().isin(job_titles_lower)]
            
        if temp_df.empty:
            return pd.DataFrame() # Return empty if no employees match filters
            
        # Get skill similarity
        # Transform the query skills to the same TF-IDF space
        query_vector = self.tfidf.transform([query_skills])
        
        # Get skill matrix for filtered indices
        filtered_indices = temp_df.index
        filtered_skill_matrix = self.skill_matrix[filtered_indices]
        
        # Compute cosine similarity
        similarities = cosine_similarity(query_vector, filtered_skill_matrix).flatten()
        temp_df['Skill_Similarity'] = similarities
        
        # Calculate composite score
        # Ensure weights sum to 1.0 (normalize them dynamically if they don't)
        total_w = w_skill + w_experience + w_performance + w_projects
        if total_w > 0:
            n_w_skill = w_skill / total_w
            n_w_exp = w_experience / total_w
            n_w_perf = w_performance / total_w
            n_w_proj = w_projects / total_w
        else:
            n_w_skill, n_w_exp, n_w_perf, n_w_proj = 0.25, 0.25, 0.25, 0.25
            
        temp_df['Final_Score'] = (
            n_w_skill * temp_df['Skill_Similarity'] +
            n_w_exp * temp_df['norm_Years_of_Experience'] +
            n_w_perf * temp_df['norm_Performance_Score'] +
            n_w_proj * temp_df['norm_Projects_Handled']
        )
        
        # Sort by final score descending, and secondary sorts on performance, experience
        temp_df = temp_df.sort_values(by=['Final_Score', 'Performance_Score', 'Years_of_Experience'], ascending=False)
        
        # Return top N
        return temp_df.head(limit)

if __name__ == '__main__':
    # Test recommender
    from preprocessing import preprocess_data
    file_path = r"c:\Users\Himanshu\Desktop\CProjectsTalentBeacon\employee management system cleaned data output2.csv"
    if os.path.exists(file_path):
        df = preprocess_data(file_path)
        recommender = EmployeeRecommender(df)
        recs = recommender.get_recommendations(
            query_skills="Python;SQL;Git", 
            w_skill=0.6, 
            w_experience=0.2, 
            w_performance=0.2,
            min_experience=2
        )
        print("Recommendations test successful! Top 3 results:")
        print(recs[['Employee_ID', 'Department', 'Job_Title', 'Years_of_Experience', 'Performance_Score', 'Skill_Similarity', 'Final_Score']].head(3))
    else:
        print(f"File not found: {file_path}")
