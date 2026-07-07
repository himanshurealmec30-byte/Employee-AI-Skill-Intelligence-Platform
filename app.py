import streamlit as st
import pandas as pd
import os
from streamlit_option_menu import option_menu

# Set page config for premium look
st.set_page_config(
    page_title="TalentBeacon 2.0 - AI Recommendation & Skill Intelligence",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for modern glassmorphism, corporate theme, KPI cards, and custom transitions
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }
    
    h1, h2, h3, h4 {
        font-family: 'Outfit', sans-serif;
        font-weight: 700;
        letter-spacing: -0.5px;
    }
    
    .stApp {
        background-color: #0b0c10;
        color: #c5c6c7;
    }
    
    /* Custom Sidebar styling */
    section[data-testid="stSidebar"] {
        background-color: #1f2833 !important;
        border-right: 1px solid #0b0c10;
    }
    
    /* Card design */
    .metric-card {
        background: rgba(31, 40, 51, 0.45);
        border: 1px solid #45f3ff;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
        transition: transform 0.3s ease, border-color 0.3s ease;
        margin-bottom: 15px;
    }
    
    .metric-card:hover {
        transform: translateY(-2px);
        border-color: #66fcf1;
    }
    
    .metric-title {
        color: #94a3b8;
        font-size: 0.85rem;
        font-weight: 600;
        text-transform: uppercase;
        margin-bottom: 5px;
    }
    
    .metric-value {
        color: #66fcf1;
        font-size: 1.8rem;
        font-weight: 700;
    }
    
    .metric-sub {
        color: #c5c6c7;
        font-size: 0.8rem;
        margin-top: 5px;
    }
    
    /* Header decoration */
    .hero-container {
        background: linear-gradient(135deg, #1f2833 0%, #0b0c10 100%);
        border: 1px solid #45f3ff;
        border-radius: 16px;
        padding: 30px;
        margin-bottom: 25px;
        text-align: left;
    }
    
    .hero-title {
        font-size: 2.5rem;
        background: linear-gradient(to right, #66fcf1, #45f3ff);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 8px;
    }
    
    .hero-subtitle {
        font-size: 1.05rem;
        color: #c5c6c7;
        max-width: 900px;
    }
    
    /* Status indicator */
    .status-ok {
        background: rgba(102, 252, 241, 0.1);
        border: 1px solid #66fcf1;
        color: #66fcf1;
        padding: 6px 12px;
        border-radius: 8px;
        font-size: 0.8rem;
        display: inline-block;
        margin-bottom: 12px;
    }
    
    /* Styled lists for certs */
    .cert-item {
        background: rgba(31, 40, 51, 0.7);
        border-left: 3px solid #66fcf1;
        padding: 6px 12px;
        margin-bottom: 6px;
        border-radius: 0 6px 6px 0;
        font-size: 0.85rem;
    }
    </style>
""", unsafe_allow_html=True)

# Import local codebase modules
try:
    from src.preprocessing import preprocess_data
    from src.dashboard.home import render_home_page
    from src.dashboard.project_analysis import render_project_analysis_page
    from src.dashboard.recommendations import render_recommendations_page
    from src.dashboard.analytics import render_analytics_page
    from src.dashboard.reports import render_reports_page
    from src.dashboard.dataset_mgmt import render_dataset_mgmt_page
except ImportError as e:
    st.error(f"Could not import custom local modules from `src/`. Error: {e}")
    st.stop()

DEFAULT_CSV_PATH = "employee management system cleaned data output2.csv"

# Load default dataset into session state if not already loaded
if 'active_df' not in st.session_state:
    if not os.path.exists(DEFAULT_CSV_PATH):
        st.error(f"Dataset file `{DEFAULT_CSV_PATH}` not found in the root workspace folder.")
        st.stop()
    try:
        st.session_state['active_df'] = preprocess_data(DEFAULT_CSV_PATH)
    except Exception as e:
        st.error(f"Failed to load dataset: {e}")
        st.stop()

# Sidebar Navigation using streamlit-option-menu
with st.sidebar:
    st.markdown("""
        <div style='text-align: center; padding-top: 15px; padding-bottom: 15px;'>
            <img src='https://img.icons8.com/color/96/000000/radar-plot.png' width='60' />
            <h3 style='color: #66fcf1; margin-top: 10px; margin-bottom: 0px;'>TalentBeacon 2.0</h3>
            <span style='color: #94a3b8; font-size: 0.75rem;'>AI Resource Intelligence</span>
        </div>
    """, unsafe_allow_html=True)
    
    selected_page = option_menu(
        menu_title=None,
        options=[
            "Home Dashboard",
            "Project Analysis",
            "Employee Recommendations",
            "Analytics & Insights",
            "Reports & Exports",
            "Dataset Management"
        ],
        icons=[
            "house",
            "file-earmark-text",
            "people",
            "bar-chart-line",
            "download",
            "gear"
        ],
        menu_icon="cast",
        default_index=0,
        styles={
            "container": {"padding": "0px", "background-color": "#1f2833"},
            "icon": {"color": "#66fcf1", "font-size": "15px"}, 
            "nav-link": {
                "font-size": "14px", 
                "text-align": "left", 
                "margin": "0px", 
                "color": "#c5c6c7",
                "--hover-color": "#45f3ff",
                "background-color": "#1f2833"
            },
            "nav-link-selected": {"background-color": "#0b0c10", "color": "#66fcf1", "font-weight": "bold"},
        }
    )
    
    # Simple status indicator in sidebar footer
    st.markdown("---")
    st.markdown("""
        <div style='text-align: center; font-size: 0.75rem; color: #94a3b8;'>
            Enterprise Version 2.0.0<br/>
            Connected to <b>Active DB</b>
        </div>
    """, unsafe_allow_html=True)

# Render main panel based on page selection
st.markdown(
    """
    <div class="hero-container">
        <span class="status-ok">● Pipeline Active & Encrypted</span>
        <div class="hero-title">TalentBeacon 2.0</div>
        <div class="hero-subtitle">
            An advanced corporate resource planning suite. Leverage NLP requirement extraction, 
            TF-IDF cosine similarity, and multi-criteria explainable matching to align the perfect team.
        </div>
    </div>
    """, 
    unsafe_allow_html=True
)

active_df = st.session_state['active_df']

if selected_page == "Home Dashboard":
    render_home_page(active_df)
elif selected_page == "Project Analysis":
    render_project_analysis_page(active_df)
elif selected_page == "Employee Recommendations":
    render_recommendations_page(active_df)
elif selected_page == "Analytics & Insights":
    render_analytics_page(active_df)
elif selected_page == "Reports & Exports":
    render_reports_page(active_df)
elif selected_page == "Dataset Management":
    render_dataset_mgmt_page()
