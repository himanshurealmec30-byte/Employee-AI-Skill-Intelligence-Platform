import pandas as pd
import numpy as np
import re

def clean_text(text):
    """Cleans encoding artifacts and standardizes string representations."""
    if not isinstance(text, str):
        return ""
    # Replace double-encoded UTF-8 dash characters
    text = re.sub(r'ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“|Ã¢â‚¬â€œ|â€“|—', '-', text)
    # Replace other potential encoding glitches
    text = text.encode('ascii', 'ignore').decode('ascii')
    return text.strip()

def preprocess_data(file_path):
    """
    Loads, cleans, and preprocesses the employee dataset.
    Returns:
        pd.DataFrame: Preprocessed DataFrame.
    """
    try:
        # Try loading with utf-8 first, fallback to latin-1
        try:
            df = pd.read_csv(file_path, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(file_path, encoding='latin-1')
        
        # Clean column names: strip whitespace, replace spaces with underscores
        df.columns = df.columns.str.strip().str.replace(' ', '_')
        
        # Verify required columns exist, mapping if necessary
        # Expected: Employee_ID, Department, Job_Title, Years_of_Experience,
        # Education_Level, Performance_Score, Projects_Handled,
        # Employee_Satisfaction_Score, Certifications, Skills, Hire_Date.
        
        # Fill missing values
        df['Department'] = df['Department'].fillna('Unknown').astype(str)
        df['Job_Title'] = df['Job_Title'].fillna('Unknown').astype(str)
        df['Education_Level'] = df['Education_Level'].fillna('Unknown').astype(str)
        df['Certifications'] = df['Certifications'].fillna('').astype(str)
        df['Skills'] = df['Skills'].fillna('').astype(str)
        
        # Clean strings
        df['Department'] = df['Department'].apply(clean_text)
        df['Job_Title'] = df['Job_Title'].apply(clean_text)
        df['Education_Level'] = df['Education_Level'].apply(clean_text)
        df['Certifications'] = df['Certifications'].apply(clean_text)
        df['Skills'] = df['Skills'].apply(clean_text)
        
        # Standardize numerical columns
        df['Years_of_Experience'] = pd.to_numeric(df['Years_of_Experience'], errors='coerce').fillna(0).astype(int)
        df['Performance_Score'] = pd.to_numeric(df['Performance_Score'], errors='coerce').fillna(3).astype(int)
        df['Projects_Handled'] = pd.to_numeric(df['Projects_Handled'], errors='coerce').fillna(0).astype(int)
        df['Employee_Satisfaction_Score'] = pd.to_numeric(df['Employee_Satisfaction_Score'], errors='coerce').fillna(df['Employee_Satisfaction_Score'].median())
        
        # Parse Hire_Date
        df['Hire_Date'] = pd.to_datetime(df['Hire_Date'], errors='coerce')
        
        # Parse list-like columns
        # Skills are semicolon separated (e.g. C++;Python;Git;PostgreSQL)
        df['Parsed_Skills'] = df['Skills'].apply(lambda x: [s.strip() for s in x.split(';') if s.strip()])
        
        # Certifications are comma separated
        df['Parsed_Certifications'] = df['Certifications'].apply(lambda x: [c.strip() for c in x.split(',') if c.strip()])
        
        return df
    
    except Exception as e:
        print(f"Error preprocessing data: {e}")
        raise e

if __name__ == '__main__':
    # Test the preprocessor
    import os
    file_path = os.environ.get("DEFAULT_CSV_PATH", "sample_employee_dataset.csv")
    if os.path.exists(file_path):
        df = preprocess_data(file_path)
        print("Data preprocessed successfully!")
        print(f"Dataset Shape: {df.shape}")
        print("\nColumns:\n", df.columns.tolist())
        print("\nFirst row sample:")
        print(df.iloc[0].to_dict())
    else:
        print(f"File not found: {file_path}")
