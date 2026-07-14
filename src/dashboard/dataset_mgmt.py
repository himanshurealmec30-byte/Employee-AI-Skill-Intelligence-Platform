import streamlit as st
import pandas as pd
import os
import sys

# Ensure parent directory is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.validators import validate_employee_csv
from preprocessing import preprocess_data

def render_dataset_mgmt_page():
    """Renders Page 6: Dataset Management & Validation."""
    st.markdown("## ⚙️ Dataset Management & Quality Assurance")
    st.write("Upload custom employee CSV datasets, run schema integrity audits, and track data quality metrics.")
    
    col_upload, col_report = st.columns([1, 1])
    
    with col_upload:
        st.markdown("### Upload Custom Employee File")
        uploaded_csv = st.file_uploader(
            "Upload Employee CSV File", 
            type=['csv'],
            help="File must contain standard columns (Employee_ID, Department, Job_Title, Years_of_Experience, etc.)"
        )
        
        # Load buttons
        if uploaded_csv is not None:
            try:
                # Read raw data for validation
                raw_df = pd.read_csv(uploaded_csv)
                st.success("File uploaded successfully! Running validation report...")
                
                # Run validator
                report = validate_employee_csv(raw_df)
                
                # Store in session state for validation display
                st.session_state['temp_df'] = raw_df
                st.session_state['validation_report'] = report
                st.session_state['temp_file_name'] = uploaded_csv.name
                
            except Exception as e:
                st.error(f"Error reading CSV: {e}")
                
        # Reset Button
        st.markdown("---")
        st.markdown("#### Database Reset")
        st.write("Reset database back to the default company employee pool:")
        
        if st.button("Reset to Default Database"):
            if os.path.exists(default_csv):
                try:
                    df = preprocess_data(default_csv)
                    st.session_state['active_df'] = df
                    # Clear recommendations from previous custom datasets
                    if 'current_recommendations' in st.session_state:
                        del st.session_state['current_recommendations']
                    st.success("Database successfully reset to default employee pool!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error loading default data: {e}")
            else:
                st.error(f"Default dataset not found at `{default_csv}`")

    with col_report:
        st.markdown("### Data Quality & Schema Audit")
        
        if 'validation_report' not in st.session_state:
            st.info("Upload a custom employee dataset on the left to inspect its validation report.")
            
            # Show default database info
            curr_df = st.session_state.get('active_df', pd.DataFrame())
            if not curr_df.empty:
                st.markdown("#### Active Dataset Profile:")
                st.markdown(f"""
                - **Active Dataset**: `Default Talent Pool`
                - **Rows Count**: `{len(curr_df):,}`
                - **Columns Count**: `{len(curr_df.columns)}`
                """)
            return
            
        report = st.session_state['validation_report']
        file_name = st.session_state['temp_file_name']
        
        # Render Data Quality Score Progress bar
        quality_score = report['data_quality_score']
        
        st.markdown(f"**Validating File**: `{file_name}`")
        
        # Color tier based on score
        if quality_score >= 80:
            score_color = "green"
            progress_bar_color = "🟢"
        elif quality_score >= 50:
            score_color = "orange"
            progress_bar_color = "🟡"
        else:
            score_color = "red"
            progress_bar_color = "🔴"
            
        st.markdown(f"#### Data Quality Score: <span style='color:{score_color}; font-size:1.8rem; font-weight:800;'>{quality_score}/100</span>", unsafe_allow_html=True)
        st.progress(quality_score / 100.0)
        
        # Check validation status
        if report['is_valid']:
            st.success("✅ **Schema Verified!** Structure is valid and ready to load.")
            
            # Allow user to load it
            if st.button("Apply & Load Uploaded Dataset", type="primary"):
                with st.spinner("Processing and loading custom dataset..."):
                    try:
                        # Clean/Preprocess the uploaded temp_df
                        # We save it temporarily to a CSV or preprocess it directly
                        temp_csv_path = "temp_uploaded_data.csv"
                        st.session_state['temp_df'].to_csv(temp_csv_path, index=False)
                        
                        df = preprocess_data(temp_csv_path)
                        st.session_state['active_df'] = df
                        
                        # Clean up temp file
                        if os.path.exists(temp_csv_path):
                            os.remove(temp_csv_path)
                            
                        # Clear old session data
                        if 'current_recommendations' in st.session_state:
                            del st.session_state['current_recommendations']
                        if 'validation_report' in st.session_state:
                            del st.session_state['validation_report']
                            
                        st.success("Successfully loaded custom employee database!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error loading custom dataset: {e}")
        else:
            st.error("❌ **Schema Invalid!** The database cannot be loaded because of missing required fields.")
            
        # Display Errors & Warnings
        if report['errors']:
            st.markdown("##### 🚨 Structural Errors:")
            for err in report['errors']:
                st.markdown(f"- {err}")
                
        if report['warnings']:
            st.markdown("##### ⚠️ Data Warnings:")
            for warn in report['warnings']:
                st.markdown(f"- {warn}")
                
        # Display Null count table
        st.markdown("##### Null/Missing Values Stats:")
        missing_df = pd.DataFrame(list(report['missing_stats'].items()), columns=['Column', 'Null Count'])
        st.dataframe(missing_df, use_container_width=True, hide_index=True)
