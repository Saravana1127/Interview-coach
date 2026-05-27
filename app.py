"""
app.py — Main Entry Point for the AI Placement Portal (Streamlit edition).

Handles global page configuration, custom CSS injection, session state
initialization, and routing between the 4 main views.
"""

import streamlit as st

# ── 1. Page Configuration ─────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Placement Portal",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── 2. Global CSS Injection ───────────────────────────────────────────────────
# We use st.markdown to inject custom CSS since we are no longer using HTML/CSS files.
st.markdown(
    """
    <style>
    /* Base theme overrides */
    :root {
        --bg: #f8fafc;
        --surface: #ffffff;
        --border: #e2e8f0;
        --text: #0f172a;
        --muted: #475569;
        --primary: #6d28d9;
        --cyan: #0891b2;
    }
    
    /* Make the whole app feel like a modern dark-mode web app */
    .stApp {
        background-color: var(--bg);
        color: var(--text);
    }
    
    /* Custom Card class we use in markdown */
    .aip-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 24px;
        transition: transform 0.2s, border-color 0.2s;
    }
    .aip-card:hover {
        transform: translateY(-2px);
        border-color: rgba(124, 92, 252, 0.4);
    }
    
    /* Hide top header bar to make it feel like a standalone app */
    header[data-testid="stHeader"] {
        background: transparent !important;
    }
    
    /* Style buttons */
    div[data-testid="stButton"] > button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.2s;
    }
    
    /* Make text inputs and textareas blend in */
    div[data-testid="stTextInput"] > div > div > input,
    div[data-testid="stChatInput"] > div > div > textarea {
        border-radius: 8px;
    }
    
    </style>
    """,
    unsafe_allow_html=True,
)


# ── 3. Session State Initialization ───────────────────────────────────────────
# We initialize all required state variables here if they don't exist yet.
def init_session_state():
    defaults = {
        "view": "setup",           # 'setup' | 'mcq' | 'hr' | 'dashboard'
        "mode": None,              # 'mcq' | 'hr' | None
        "candidate_name": "",
        "job_title": "",
        "resume_text": "",
        "resume_name": "",

        # MCQ State
        "mcq_questions": [],
        "mcq_current": 0,
        "mcq_answers": [],
        "mcq_start_time": None,

        # HR State
        "hr_messages": [],
        "hr_turn": 0,
        "hr_questions": [],
        "hr_answers": [],
        "hr_waiting": False,

        # Shared State
        "evaluation": None,
    }

    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

init_session_state()


# ── 4. View Router ────────────────────────────────────────────────────────────
# Import the views here to avoid circular imports and keep startup fast
from frontend.setup_view import render_setup
from frontend.mcq_view import render_mcq
from frontend.hr_view import render_hr
from frontend.dashboard_view import render_dashboard

def main():
    view = st.session_state.view
    
    if view == "setup":
        render_setup()
    elif view == "mcq":
        render_mcq()
    elif view == "hr":
        render_hr()
    elif view == "dashboard":
        render_dashboard()
    else:
        st.error(f"Unknown view: {view}")
        if st.button("Reset"):
            st.session_state.view = "setup"
            st.rerun()

if __name__ == "__main__":
    main()
