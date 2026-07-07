import pandas as pd
import numpy as np

def validate_employee_csv(df):
    """
    Validates the structure and quality of an uploaded employee DataFrame.
    
    Args:
        df (pd.DataFrame): DataFrame to validate.
        
    Returns:
        dict: Validation report containing 'is_valid', 'errors', 'warnings', 
              'missing_stats', 'data_quality_score', and 'quality_metrics'.
    """
    report = {
        'is_valid': True,
        'errors': [],
        'warnings': [],
        'missing_stats': {},
        'data_quality_score': 100,
        'quality_metrics': {}
    }
    
    if df.empty:
        report['is_valid'] = False
        report['errors'].append("The uploaded file is empty.")
        report['data_quality_score'] = 0
        return report
        
    # Standardize column names for checking (strip, replace spaces with underscores, lowercase)
    norm_cols = [str(c).strip().replace(' ', '_').lower() for c in df.columns]
    
    # Required columns (standardized lowercase)
    required_cols_map = {
        'employee_id': 'Employee_ID',
        'department': 'Department',
        'job_title': 'Job_Title',
        'years_of_experience': 'Years_of_Experience',
        'education_level': 'Education_Level',
        'performance_score': 'Performance_Score',
        'projects_handled': 'Projects_Handled',
        'employee_satisfaction_score': 'Employee_Satisfaction_Score',
        'certifications': 'Certifications',
        'skills': 'Skills',
        'hire_date': 'Hire_Date'
    }
    
    # Check for missing required columns
    missing_required = []
    for col_key, original_name in required_cols_map.items():
        # Handle "years of experience" space variance
        if col_key not in norm_cols and col_key != 'years_of_experience':
            missing_required.append(original_name)
        elif col_key == 'years_of_experience':
            if 'years_of_experience' not in norm_cols and 'years_of_experience' not in [c.replace(' ', '_') for c in norm_cols]:
                # Special check for 'Years of Experience'
                has_exp = False
                for c in df.columns:
                    c_clean = str(c).strip().lower().replace(' ', '_')
                    if 'experience' in c_clean and ('years' in c_clean or 'yrs' in c_clean):
                        has_exp = True
                        break
                if not has_exp:
                    missing_required.append(original_name)
                    
    if missing_required:
        report['is_valid'] = False
        report['errors'].append(f"Missing required columns: {', '.join(missing_required)}")
        report['data_quality_score'] -= min(50, len(missing_required) * 15)
        
    # 1. Missing Values Stats
    total_cells = df.size
    total_missing = df.isnull().sum().sum()
    missing_percentage = (total_missing / total_cells) * 100 if total_cells > 0 else 0
    
    report['missing_stats'] = df.isnull().sum().to_dict()
    report['quality_metrics']['missing_percentage'] = missing_percentage
    report['data_quality_score'] -= min(30, int(missing_percentage * 2))
    
    # 2. Duplicate Employee ID Check
    # Find employee ID column
    id_col = None
    for c in df.columns:
        if str(c).strip().replace(' ', '_').lower() == 'employee_id':
            id_col = c
            break
            
    if id_col is not None:
        duplicates_count = df[id_col].duplicated().sum()
        duplicate_percentage = (duplicates_count / len(df)) * 100 if len(df) > 0 else 0
        report['quality_metrics']['duplicate_ids'] = duplicates_count
        report['quality_metrics']['duplicate_percentage'] = duplicate_percentage
        if duplicates_count > 0:
            report['warnings'].append(f"Found {duplicates_count} duplicate Employee ID(s). Recommendations may have overlaps.")
            report['data_quality_score'] -= min(20, int(duplicate_percentage * 3))
    else:
        report['quality_metrics']['duplicate_ids'] = 0
        report['quality_metrics']['duplicate_percentage'] = 0
        
    # 3. Numeric Ranges Validation
    # Validate experience column range
    exp_col = None
    for c in df.columns:
        c_clean = str(c).strip().lower().replace(' ', '_')
        if 'years_of_experience' in c_clean or c_clean == 'years_of_experience' or ('years' in c_clean and 'experience' in c_clean):
            exp_col = c
            break
            
    if exp_col is not None:
        try:
            non_numeric_exp = pd.to_numeric(df[exp_col], errors='coerce').isnull().sum()
            if non_numeric_exp > 0:
                report['warnings'].append(f"Experience column contains {non_numeric_exp} non-numeric values. These will be filled with 0.")
                report['data_quality_score'] -= min(10, non_numeric_exp)
                
            neg_exp = (pd.to_numeric(df[exp_col], errors='coerce') < 0).sum()
            if neg_exp > 0:
                report['warnings'].append(f"Experience column has {neg_exp} negative values.")
                report['data_quality_score'] -= min(10, neg_exp)
        except Exception:
            pass
            
    # Validate performance score range
    perf_col = None
    for c in df.columns:
        if str(c).strip().replace(' ', '_').lower() == 'performance_score':
            perf_col = c
            break
            
    if perf_col is not None:
        try:
            perf_series = pd.to_numeric(df[perf_col], errors='coerce')
            out_of_bounds = ((perf_series < 1) | (perf_series > 5)).sum()
            if out_of_bounds > 0:
                report['warnings'].append(f"Performance Score contains {out_of_bounds} values outside the standard [1, 5] range.")
                report['data_quality_score'] -= min(15, out_of_bounds)
        except Exception:
            pass
            
    # Bound quality score between 0 and 100
    report['data_quality_score'] = max(0, min(100, report['data_quality_score']))
    
    return report
