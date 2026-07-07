import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

def render_analytics_page(df):
    """Renders Page 4: Talent Pool Analytics & Insights."""
    st.markdown("## 📊 Skill Intelligence & Employee Demographics")
    st.write("Visual profiling and structural composition of the active employee dataset.")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        # 1. Top Skills Distribution
        st.markdown("#### Top 15 Most Common Skills")
        all_skills = [s for list_s in df['Parsed_Skills'] for s in list_s]
        if all_skills:
            skills_df = pd.Series(all_skills).value_counts().head(15).reset_index()
            skills_df.columns = ['Skill', 'Count']
            
            fig_skills = px.bar(
                skills_df,
                x='Count',
                y='Skill',
                orientation='h',
                color='Count',
                color_continuous_scale='tealgrn'
            )
            fig_skills.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color='#94a3b8'),
                xaxis=dict(showgrid=True, gridcolor='#1f2235'),
                yaxis=dict(categoryorder='total ascending'),
                margin=dict(l=10, r=10, t=10, b=10),
                coloraxis_showscale=False,
                height=350
            )
            st.plotly_chart(fig_skills, use_container_width=True)
        else:
            st.write("No skills found.")
            
        # 2. Average Experience by Department
        st.markdown("#### Average Tenures (Experience) by Department")
        avg_exp = df.groupby('Department')['Years_of_Experience'].mean().reset_index().sort_values(by='Years_of_Experience')
        
        fig_exp = px.bar(
            avg_exp,
            x='Years_of_Experience',
            y='Department',
            orientation='h',
            color='Years_of_Experience',
            color_continuous_scale='Purples'
        )
        fig_exp.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#94a3b8'),
            xaxis=dict(showgrid=True, gridcolor='#1f2235'),
            margin=dict(l=10, r=10, t=10, b=10),
            coloraxis_showscale=False,
            height=350
        )
        st.plotly_chart(fig_exp, use_container_width=True)
        
    with col2:
        # 3. Performance Scores
        st.markdown("#### Performance Ratings Distribution")
        perf_counts = df['Performance_Score'].value_counts().sort_index().reset_index()
        perf_counts.columns = ['Rating', 'EmployeesCount']
        
        fig_perf = px.bar(
            perf_counts,
            x='Rating',
            y='EmployeesCount',
            color='EmployeesCount',
            color_continuous_scale='blues'
        )
        fig_perf.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#94a3b8'),
            yaxis=dict(showgrid=True, gridcolor='#1f2235'),
            margin=dict(l=10, r=10, t=10, b=10),
            coloraxis_showscale=False,
            height=350
        )
        st.plotly_chart(fig_perf, use_container_width=True)
        
        # 4. Certifications count
        st.markdown("#### Most Common Certifications")
        all_certs = [c for list_c in df['Parsed_Certifications'] for c in list_c]
        if all_certs:
            certs_df = pd.Series(all_certs).value_counts().head(10).reset_index()
            certs_df.columns = ['Certification', 'Count']
            
            fig_certs = px.bar(
                certs_df,
                x='Count',
                y='Certification',
                orientation='h',
                color='Count',
                color_continuous_scale='amp'
            )
            fig_certs.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color='#94a3b8'),
                xaxis=dict(showgrid=True, gridcolor='#1f2235'),
                yaxis=dict(categoryorder='total ascending'),
                margin=dict(l=10, r=10, t=10, b=10),
                coloraxis_showscale=False,
                height=350
            )
            st.plotly_chart(fig_certs, use_container_width=True)
        else:
            st.write("No certifications recorded.")
            
    # Scatter plot on full screen width
    st.markdown("---")
    st.markdown("#### Experience vs Projects Handled (by Performance Score)")
    sample_df = df.sample(min(1500, len(df)), random_state=42)
    fig_scatter = px.scatter(
        sample_df,
        x='Years_of_Experience',
        y='Projects_Handled',
        color='Performance_Score',
        size='Employee_Satisfaction_Score',
        color_continuous_scale='viridis',
        hover_data=['Employee_ID', 'Department', 'Job_Title']
    )
    fig_scatter.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#94a3b8'),
        xaxis=dict(showgrid=True, gridcolor='#1f2235'),
        yaxis=dict(showgrid=True, gridcolor='#1f2235'),
        margin=dict(l=10, r=10, t=20, b=10),
        height=380
    )
    st.plotly_chart(fig_scatter, use_container_width=True)
