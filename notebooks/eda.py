import os
import sys
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Ensure parent directory is in sys.path to import src modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.preprocessing import preprocess_data

def run_eda(csv_path, output_dir):
    """Runs EDA on the employee dataset and saves visualizations."""
    os.makedirs(output_dir, exist_ok=True)
    
    print("Loading and preprocessing data...")
    df = preprocess_data(csv_path)
    
    # Write text summary to log
    summary_path = os.path.join(output_dir, 'data_summary.txt')
    with open(summary_path, 'w') as f:
        f.write("=== DATASET PROFILE ===\n")
        f.write(f"Shape: {df.shape}\n\n")
        f.write("=== COLUMNS & TYPES ===\n")
        for col, dtype in zip(df.columns, df.dtypes):
            f.write(f"{col}: {dtype}\n")
        f.write("\n=== MISSING VALUES ===\n")
        f.write(df.isnull().sum().to_string())
        f.write("\n\n=== CATEGORICAL DISTRIBUTIONS ===\n")
        f.write("\nDepartments:\n")
        f.write(df['Department'].value_counts().to_string())
        f.write("\n\nJob Titles:\n")
        f.write(df['Job_Title'].value_counts().to_string())
    print(f"Text summary saved to {summary_path}")
    
    # Styling plots
    sns.set_theme(style="darkgrid")
    plt.rcParams['font.family'] = 'sans-serif'
    
    # 1. Department Distribution Plot
    plt.figure(figsize=(10, 6))
    sns.countplot(data=df, y='Department', order=df['Department'].value_counts().index, palette='viridis')
    plt.title('Employee Count by Department', fontsize=14, fontweight='bold')
    plt.xlabel('Count')
    plt.ylabel('Department')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'department_distribution.png'), dpi=300)
    plt.close()
    
    # 2. Performance Score vs Years of Experience
    plt.figure(figsize=(10, 6))
    sns.boxplot(data=df, x='Performance_Score', y='Years_of_Experience', palette='coolwarm')
    plt.title('Years of Experience by Performance Score', fontsize=14, fontweight='bold')
    plt.xlabel('Performance Score')
    plt.ylabel('Years of Experience')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'experience_by_performance.png'), dpi=300)
    plt.close()
    
    # 3. Top Skills Frequency Count
    plt.figure(figsize=(12, 8))
    all_skills_flat = [s for list_s in df['Parsed_Skills'] for s in list_s]
    skills_counts = pd.Series(all_skills_flat).value_counts().head(20)
    sns.barplot(x=skills_counts.values, y=skills_counts.index, palette='crest')
    plt.title('Top 20 Most Frequent Skills', fontsize=14, fontweight='bold')
    plt.xlabel('Number of Employees')
    plt.ylabel('Skills')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'top_skills_frequency.png'), dpi=300)
    plt.close()
    
    # 4. Satisfaction Score Distribution
    plt.figure(figsize=(10, 6))
    sns.histplot(data=df, x='Employee_Satisfaction_Score', kde=True, color='dodgerblue', bins=20)
    plt.title('Distribution of Employee Satisfaction Score', fontsize=14, fontweight='bold')
    plt.xlabel('Satisfaction Score')
    plt.ylabel('Frequency')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'satisfaction_score_distribution.png'), dpi=300)
    plt.close()
    
    print(f"All EDA visualizations successfully saved in: {output_dir}")

if __name__ == '__main__':
    csv_path = os.environ.get("DEFAULT_CSV_PATH", "sample_employee_dataset.csv")
    output_dir = r"c:\Users\Himanshu\Desktop\CProjectsTalentBeacon\notebooks\plots"
    run_eda(csv_path, output_dir)
