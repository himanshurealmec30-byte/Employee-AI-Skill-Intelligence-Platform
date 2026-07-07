import streamlit as st
import os
import sys

# Ensure parent directory is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.helpers import extract_text_from_file
from nlp.extractor import parse_project_requirements

def render_project_analysis_page(df):
    """Renders the Page 2: Project Analysis & Document Parsing."""
    st.markdown("## 📄 Project Requirement Extraction (NLP)")
    st.write("Upload a project proposal, job description, or description document to extract requirements.")
    
    # Init session state if not existing
    if 'parsed_requirements' not in st.session_state:
        st.session_state['parsed_requirements'] = {
            "skills": ["Python", "SQL", "Git"],
            "min_experience": 2,
            "certifications": [],
            "domain": "Data Science & Artificial Intelligence"
        }
        
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown("### Upload Project Charter / Job Description")
        uploaded_file = st.file_uploader(
            "Choose a document file", 
            type=['pdf', 'docx', 'txt'],
            help="Supported formats: PDF, DOCX, TXT"
        )
        
        st.markdown("**OR** Paste Requirement Text Directly:")
        raw_text_input = st.text_area(
            "Paste details here...", 
            height=180,
            placeholder="e.g., We need a Senior DevOps Engineer with 4+ years of experience. Strong skills in Docker, Kubernetes, AWS, Jenkins and Bash. Certifications in AWS solutions architect is preferred."
        )
        
        extract_btn = st.button("Extract Requirements", type="primary")
        
    with col2:
        st.markdown("### Extraction Output")
        
        extracted_text = ""
        if extract_btn:
            if uploaded_file is not None:
                with st.spinner("Parsing uploaded file..."):
                    try:
                        extracted_text = extract_text_from_file(uploaded_file)
                        st.success(f"Successfully read file: {uploaded_file.name}")
                    except Exception as e:
                        st.error(f"Error reading file: {e}")
            elif raw_text_input.strip() != "":
                extracted_text = raw_text_input
            else:
                st.warning("Please upload a file or paste requirement text first.")
                
            if extracted_text:
                # Extract all unique skills and certs from original dataframe to seed NLP matching
                # Gather unique skills from the dataframe
                all_unique_skills = sorted(list(set([s for list_s in df['Parsed_Skills'] for s in list_s])))
                all_unique_certs = sorted(list(set([c for list_c in df['Parsed_Certifications'] for c in list_c])))
                
                # Run NLP parser
                with st.spinner("Extracting parameters using NLP..."):
                    results = parse_project_requirements(
                        extracted_text, 
                        skill_vocab=all_unique_skills, 
                        known_certs=all_unique_certs
                    )
                    st.session_state['parsed_requirements'] = results
                    st.success("Extraction Completed!")
                    
        # Display current parsed requirements (either loaded from session state or newly extracted)
        curr_reqs = st.session_state['parsed_requirements']
        
        st.markdown(f"""
        <div class="metric-card" style="margin-top: 10px;">
            <div class="metric-title">Inferred Project Domain</div>
            <div class="metric-value" style="font-size: 1.3rem; color: #38bdf8;">{curr_reqs.get('domain', 'N/A')}</div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown(f"**Minimum Experience Required**: `{curr_reqs.get('min_experience', 0)} years`")
        
        st.markdown("**Required Skills Extracted**:")
        skills = curr_reqs.get('skills', [])
        if skills:
            # Render as neat visual badge layout
            st.markdown(" ".join([f"`{s}`" for s in skills]))
        else:
            st.write("*No matching skills extracted yet.*")
            
        st.markdown("**Certifications Required**:")
        certs = curr_reqs.get('certifications', [])
        if certs:
            for c in certs:
                st.markdown(f"<div class='cert-item'>{c}</div>", unsafe_allow_html=True)
        else:
            st.write("*No specific certifications extracted.*")
            
        # Button to go direct to recommendations
        st.markdown("---")
        st.write("Ready to match candidates? Navigate to the **Employee Recommendations** page to view recommendations.")
