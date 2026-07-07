import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import os
import sys

# Ensure parent directory is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from recommendation.engine import RecommendationEngine

def render_recommendations_page(df):
    """Renders Page 3: Recommendations & Details."""
    st.markdown("## 👥 Candidate Matchmaker & Recommendations")
    
    # Initialize Engine
    engine = RecommendationEngine(df)
    
    # Load defaults from project analysis session state if available
    defaults = st.session_state.get('parsed_requirements', {
        "skills": ["Python", "SQL", "Git"],
        "min_experience": 2,
        "certifications": [],
        "domain": "Data Science & Artificial Intelligence"
    })
    
    col_ctrl, col_table = st.columns([1, 2])
    
    with col_ctrl:
        st.markdown("### Match Parameters")
        
        # Skill Multi-select (Seeded with NLP extraction)
        all_skills = sorted(list(set([s for list_s in df['Parsed_Skills'] for s in list_s])))
        selected_skills = st.multiselect(
            "Project Skills:",
            options=all_skills,
            default=defaults.get("skills", [])
        )
        
        # Experience Slider
        req_exp = st.slider(
            "Required Experience (Yrs):",
            0, 15, int(defaults.get("min_experience", 0))
        )
        
        # Certifications select
        all_certs = sorted(list(set([c for list_c in df['Parsed_Certifications'] for c in list_c])))
        selected_certs = st.multiselect(
            "Required Certifications:",
            options=all_certs,
            default=defaults.get("certifications", [])
        )
        
        st.markdown("### Score Component Weights")
        w_skill = st.slider("Skill Match Weight", 0.0, 1.0, 0.40, 0.05)
        w_exp = st.slider("Experience Match Weight", 0.0, 1.0, 0.25, 0.05)
        w_perf = st.slider("Performance Match Weight", 0.0, 1.0, 0.20, 0.05)
        w_cert = st.slider("Certification Match Weight", 0.0, 1.0, 0.15, 0.05)
        
        st.markdown("### Strict Filters")
        depts = sorted(df['Department'].unique().tolist())
        selected_depts = st.multiselect("Filter Departments", depts, default=[])
        
        titles = sorted(df['Job_Title'].unique().tolist())
        selected_titles = st.multiselect("Filter Job Titles", titles, default=[])
        
        limit = st.slider("Max Candidates", 5, 20, 10)
        
    with col_table:
        st.markdown("### Recommendations Rankings")
        
        # Pack parameters
        req_dict = {
            "skills": selected_skills,
            "min_experience": req_exp,
            "certifications": selected_certs
        }
        
        if not selected_skills:
            st.warning("Please specify at least one skill to match candidates.")
            return
            
        with st.spinner("Ranking candidates..."):
            recs = engine.get_recommendations(
                requirements=req_dict,
                w_skill=w_skill,
                w_experience=w_exp,
                w_performance=w_perf,
                w_certifications=w_cert,
                departments=selected_depts if selected_depts else None,
                job_titles=selected_titles if selected_titles else None,
                limit=limit
            )
            
        if recs.empty:
            st.error("No employees match the strict filters or hold matching criteria. Relax your filters.")
            return
            
        # Keep recommendations globally in session state for export
        st.session_state['current_recommendations'] = recs
        st.session_state['current_query_skills'] = ";".join(selected_skills)
        
        # Display recommendations with custom cards & progress bars
        for rank, (idx, row) in enumerate(recs.iterrows(), 1):
            score_pct = int(row['Final_Score'] * 100)
            
            # Highlight border color based on score tier
            if score_pct >= 85:
                border_color = "#10b981"  # Emerald Green
            elif score_pct >= 70:
                border_color = "#6366f1"  # Indigo
            else:
                border_color = "#f59e0b"  # Amber
                
            st.markdown(
                f"""
                <div style="background: rgba(26, 29, 46, 0.8); border-left: 5px solid {border_color}; 
                            border-radius: 8px; padding: 15px; margin-bottom: 15px; border-top: 1px solid #1f2235;
                            border-right: 1px solid #1f2235; border-bottom: 1px solid #1f2235;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <span style="font-size: 1.15rem; font-weight: 700; color: #ffffff;">Rank #{rank} — Employee ID: {row['Employee_ID']}</span>
                            <span style="background: rgba(99, 102, 241, 0.15); color: #818cf8; padding: 2px 8px; 
                                         border-radius: 4px; font-size: 0.75rem; font-weight: 600; margin-left: 10px;">
                                {row['Job_Title']} in {row['Department']}
                            </span>
                        </div>
                        <div style="text-align: right;">
                            <span style="font-size: 1.35rem; font-weight: 800; color: {border_color};">{score_pct}% Match</span>
                        </div>
                    </div>
                    
                    <div style="margin-top: 10px; font-size: 0.85rem; color: #94a3b8;">
                        <strong>Skills Owned:</strong> {', '.join([f'<code>{s}</code>' for s in row['Parsed_Skills']])}
                    </div>
                </div>
                """, unsafe_allow_html=True
            )
            
            # Interactive explainability details inside Streamlit expander
            expl = row['Explanation']
            with st.expander(f"🔍 View Match Explanation & Breakdown for Candidate #{rank}"):
                col_e1, col_e2 = st.columns([1, 1])
                with col_e1:
                    st.markdown(f"**Skills Match**: {expl['skill_statement']}")
                    if expl['matched_skills']:
                        st.markdown(f"🟢 **Matched Skills**: {', '.join(expl['matched_skills'])}")
                    if expl['missing_skills']:
                        st.markdown(f"🔴 **Missing Skills**: {', '.join(expl['missing_skills'])}")
                        
                with col_e2:
                    st.markdown(f"📈 **Experience**: {expl['experience_statement']}")
                    st.markdown(f"⭐ **Performance**: {expl['performance_statement']}")
                    st.markdown(f"📜 **Credentials**: {expl['certification_statement']}")
                    
                st.code(expl['breakdown'], language="text")
                
        # Individual profile graph section
        st.markdown("---")
        st.markdown("### 📊 Candidate Comparative Profiler")
        
        emp_ids = recs['Employee_ID'].tolist()
        profile_emp_id = st.selectbox(
            "Select a candidate to render their comparative metrics radar graph:",
            options=emp_ids,
            format_func=lambda x: f"Candidate ID {x} ({recs[recs['Employee_ID']==x]['Job_Title'].values[0]})"
        )
        
        if profile_emp_id:
            row_p = recs[recs['Employee_ID'] == profile_emp_id].iloc[0]
            
            # Calculate metrics comparative vectors
            dept_avg = df[df['Department'] == row_p['Department']].mean(numeric_only=True)
            company_avg = df.mean(numeric_only=True)
            
            categories = ['Years_of_Experience', 'Performance_Score', 'Projects_Handled', 'Employee_Satisfaction_Score']
            
            emp_vals = []
            dept_vals = []
            comp_vals = []
            
            for col in categories:
                max_val = df[col].max() if df[col].max() > 0 else 1
                emp_vals.append(row_p[col] / max_val)
                dept_vals.append(dept_avg[col] / max_val)
                comp_vals.append(company_avg[col] / max_val)
                
            categories_labels = ['Experience', 'Performance', 'Projects Handled', 'Satisfaction']
            
            # Add Skill similarity
            categories_labels.append('Skill Match')
            emp_vals.append(row_p['Skill_Similarity'])
            dept_vals.append(0.25)
            comp_vals.append(0.15)
            
            # Plot
            fig = go.Figure()
            
            fig.add_trace(go.Scatterpolar(
                r=emp_vals,
                theta=categories_labels,
                fill='toself',
                fillcolor='rgba(16, 185, 129, 0.15)',
                line=dict(color='#10b981', width=3),
                name=f"Candidate ID {profile_emp_id}"
            ))
            fig.add_trace(go.Scatterpolar(
                r=dept_vals,
                theta=categories_labels,
                fill='toself',
                fillcolor='rgba(99, 102, 241, 0.1)',
                line=dict(color='#6366f1', width=2, dash='dash'),
                name=f"{row_p['Department']} Dept Avg"
            ))
            fig.add_trace(go.Scatterpolar(
                r=comp_vals,
                theta=categories_labels,
                line=dict(color='#94a3b8', width=1, dash='dot'),
                name="Company Avg"
            ))
            
            fig.update_layout(
                polar=dict(
                    radialaxis=dict(visible=True, range=[0, 1.05], showticklabels=False, gridcolor='#1f2235'),
                    angularaxis=dict(gridcolor='#1f2235', linecolor='#1f2235'),
                    bgcolor='#121420'
                ),
                paper_bgcolor='#0d0e15',
                plot_bgcolor='#0d0e15',
                height=380,
                legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5),
                margin=dict(t=20, b=50, l=40, r=40)
            )
            
            st.plotly_chart(fig, use_container_width=True)
