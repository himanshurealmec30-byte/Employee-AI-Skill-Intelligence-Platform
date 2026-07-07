import streamlit as st
import pandas as pd
import io

def generate_txt_report(recs, query_skills):
    """Generates a text summary report for candidate recommendations."""
    output = io.StringIO()
    output.write("====================================================\n")
    output.write("          TALENTBEACON RECOMMENDATION REPORT         \n")
    output.write("====================================================\n\n")
    
    output.write(f"Query Skills Matched: {query_skills.replace(';', ', ')}\n")
    output.write(f"Total Recommendations: {len(recs)}\n\n")
    
    output.write("----------------------------------------------------\n")
    output.write("TOP RECOMMENDED CANDIDATES\n")
    output.write("----------------------------------------------------\n")
    
    for rank, (idx, row) in enumerate(recs.iterrows(), 1):
        score_pct = int(row['Final_Score'] * 100)
        expl = row['Explanation']
        
        output.write(f"Rank #{rank}: Employee ID {row['Employee_ID']}\n")
        output.write(f"  Department: {row['Department']}\n")
        output.write(f"  Job Title: {row['Job_Title']}\n")
        output.write(f"  Match Percentage: {score_pct}%\n")
        output.write(f"  Experience: {row['Years_of_Experience']} years\n")
        output.write(f"  Performance Score: {row['Performance_Score']}/5\n")
        output.write(f"  Skills: {row['Skills'].replace(';', ', ')}\n")
        output.write(f"  Certifications: {row['Certifications'] if row['Certifications'] else 'None'}\n")
        output.write(f"  Explainability Details:\n")
        output.write(f"    - {expl['skill_statement']}\n")
        output.write(f"    - {expl['experience_statement']}\n")
        output.write(f"    - {expl['performance_statement']}\n")
        output.write(f"    - {expl['certification_statement']}\n")
        output.write("----------------------------------------------------\n")
        
    return output.getvalue()

def render_reports_page(df):
    """Renders Page 5: Reports & Exports."""
    st.markdown("## 📥 Export Reports & Recommendations")
    st.write("Generate and download tabular spreadsheets or text summary documentation.")
    
    # Fetch current recommendations from session state
    recs = st.session_state.get('current_recommendations', pd.DataFrame())
    query_skills = st.session_state.get('current_query_skills', "")
    
    if recs.empty:
        st.warning("No recommendations have been generated yet. Please go to the **Employee Recommendations** page to generate results first.")
        return
        
    st.success(f"Loaded {len(recs)} generated recommendations from the active session.")
    
    # Display table preview
    st.markdown("### Preview of Data to Export")
    export_preview = recs[[
        'Employee_ID', 'Department', 'Job_Title', 
        'Years_of_Experience', 'Performance_Score', 
        'Projects_Handled', 'Skill_Similarity', 'Final_Score'
    ]].copy()
    export_preview.columns = [
        'ID', 'Department', 'Job Title', 
        'Experience (Yrs)', 'Performance Score', 
        'Projects Handled', 'Skill Similarity', 'Match Score'
    ]
    st.dataframe(export_preview, use_container_width=True, hide_index=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Export Tabular Results (CSV)")
        st.write("Download candidates ranking with detail columns, ready to open in Excel or upload to an HR database.")
        
        # Format CSV
        csv_data = recs.to_csv(index=False).encode('utf-8')
        
        st.download_button(
            label="💾 Download Recommendations CSV",
            data=csv_data,
            file_name="TalentBeacon_Recommendations.csv",
            mime="text/csv"
        )
        
    with col2:
        st.markdown("#### Export Executive Summary (Text Report)")
        st.write("Download a text document detailing the project parameters, matched/missing skills, and explanations for each recommendation.")
        
        # Format TXT
        txt_data = generate_txt_report(recs, query_skills)
        
        st.download_button(
            label="📄 Download Summary TXT Report",
            data=txt_data.encode('utf-8'),
            file_name="TalentBeacon_Executive_Report.txt",
            mime="text/plain"
        )
