import streamlit as st
import pandas as pd
import plotly.express as px

def render_home_page(df):
    """Renders the Page 1: Home Dashboard."""
    st.markdown("## 🎯 Executive Talent Overview")
    
    # Calculate company metrics
    total_emp = len(df)
    avg_exp = df['Years_of_Experience'].mean()
    avg_perf = df['Performance_Score'].mean()
    avg_sat = df['Employee_Satisfaction_Score'].mean()
    
    # Render KPI cards
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">Total Talent Pool</div>
                <div class="metric-value">{total_emp:,}</div>
                <div class="metric-sub">Active Employees</div>
            </div>
            """, unsafe_allow_html=True
        )
    with col2:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">Average Experience</div>
                <div class="metric-value">{avg_exp:.1f} Yrs</div>
                <div class="metric-sub">Corporate Tenures</div>
            </div>
            """, unsafe_allow_html=True
        )
    with col3:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">Avg Performance Score</div>
                <div class="metric-value">{avg_perf:.2f}/5.0</div>
                <div class="metric-sub">Overall Rating</div>
            </div>
            """, unsafe_allow_html=True
        )
    with col4:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">Satisfaction Score</div>
                <div class="metric-value">{avg_sat:.2f}/5.0</div>
                <div class="metric-sub">Pulse Index</div>
            </div>
            """, unsafe_allow_html=True
        )
        
    st.markdown("---")
    
    col_left, col_right = st.columns([3, 2])
    
    with col_left:
        st.markdown("### 🔍 About TalentBeacon 2.0")
        st.write("""
        **TalentBeacon 2.0** is an enterprise-grade AI-powered Employee Recommendation & Skill Intelligence Platform. 
        It integrates Natural Language Processing (NLP), Machine Learning similarity algorithms, and interactive 
        visualizations to solve resource allocation challenges.
        
        #### Core Operations:
        1. **NLP Requirement Parsing**: Upload project charters or text descriptions (PDF, DOCX, TXT) to automatically extract core tech stacks, certifications, and experience requirements.
        2. **Hybrid Scoring Engine**: Rank candidates by blending Skill Match (TF-IDF Cosine Similarity), experience suitability, ratings performance, and credentials.
        3. **Explainable Recommendations**: Understand exactly why candidates are recommended, with clear lists of matched and missing skills.
        4. **Skill Intelligence Analytics**: Profile corporate competencies, identify capability gaps, and track demographics.
        """)
        
    with col_right:
        st.markdown("### 🏢 Department Size Distribution")
        # Visual distribution
        dept_counts = df['Department'].value_counts().reset_index()
        dept_counts.columns = ['Department', 'Count']
        
        fig = px.pie(
            dept_counts, 
            values='Count', 
            names='Department',
            hole=0.4,
            color_discrete_sequence=px.colors.qualitative.Pastel
        )
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#94a3b8'),
            legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5),
            margin=dict(t=10, b=50, l=10, r=10),
            height=300
        )
        st.plotly_chart(fig, use_container_width=True)
