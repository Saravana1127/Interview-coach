import streamlit as st
import time
import os
import sys

# Ensure local imports resolve correctly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ai_engine
import pdf_processor
from audio_component import audio_component
from video_handler import render_camera_feed
from components.proctoring import run_proctoring

# 1. Page Configuration
st.set_page_config(
    page_title="AI Placement Portal",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# 2. Global CSS Injection for High Contrast and Pure Typography
st.markdown(
    """
    <style>
    /* CSS Variables matching professional theme */
    :root {
        --bg: #f8fafc;
        --surface: #ffffff;
        --border: #e2e8f0;
        --text: #0f172a;
        --muted: #475569;
        --primary: #6d28d9;
        --cyan: #0891b2;
    }
    
    .stApp {
        background-color: var(--bg);
        color: var(--text);
    }
    
    /* Layout cards */
    .aip-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 24px;
        transition: transform 0.2s, border-color 0.2s;
        margin-bottom: 16px;
    }
    .aip-card:hover {
        transform: translateY(-2px);
        border-color: rgba(109, 40, 217, 0.4);
    }
    
    /* Ensure high contrast for text inside cards */
    .aip-card p, .aip-card div {
        color: #0f172a !important;
        font-weight: 700 !important;
    }
    
    /* Ensure Streamlit radio button options are highly contrasted and bold */
    div.stRadio > div[role="radiogroup"] label {
        color: #0f172a !important;
        font-weight: 700 !important;
        font-size: 1.05rem !important;
    }
    
    /* Remove headers */
    header[data-testid="stHeader"] {
        background: transparent !important;
    }
    
    /* Buttons styling */
    div[data-testid="stButton"] > button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.2s;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# 3. Session State Initialization
def init_session_state():
    defaults = {
        "step": 1,                 # 1: Setup, 2: Scoring, 3: Assessment, 4: Dashboard
        "mode": None,              # 'hr' | 'mcq'
        "candidate_name": "",
        "job_title": "",
        
        # Resume Scorer state
        "resume_text": "",
        "resume_score": None,      # dict from LLM evaluation
        
        # MCQ state
        "mcq_questions": [],
        "mcq_current": 0,
        "mcq_answers": [],
        "mcq_start_time": None,
        
        # HR state
        "hr_messages": [],
        "hr_turn": 0,
        "hr_questions": [],
        "hr_answers": [],
        "hr_waiting": False,
        "last_processed_transcript": "",
        
        # Proctoring state
        "integrity_stats": {"tabs": 0, "pastes": 0, "fs_exits": 0},
        "evaluation": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

init_session_state()

# 4. View Constants
TOTAL_TURNS = 5
MCQ_COUNT = 10

# ── STEP 1: SETUP & UPLOAD ───────────────────────────────────────────────────
def render_step1_setup():
    st.markdown(
        """
        <div style="text-align:center; padding: 2.5rem 0 1.5rem;">
            <h1 style="font-size:3rem; font-weight:900; margin-bottom:0.4rem;">
                AI Placement Portal
            </h1>
            <p style="color:#6d28d9; font-size:1.15rem; font-weight:500; margin-bottom:0.4rem;">
                Candidate Portal and Placement Pipeline
            </p>
            <p style="color:#475569; font-size:0.92rem; max-width:520px; margin:0 auto 2rem;">
                Step 1 of 4: Setup details and upload your document to begin the scoring and assessment pipeline.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _, form_col, _ = st.columns([1, 2, 1])
    with form_col:
        st.markdown("<h3 style='color:#6d28d9;'>Candidate Configuration</h3>", unsafe_allow_html=True)
        
        name = st.text_input(
            "Full Name",
            value=st.session_state.candidate_name,
            placeholder="e.g. Alex Johnson",
            max_chars=60,
            key="setup_name"
        )
        
        job = st.text_input(
            "Target Job Title / Topic",
            value=st.session_state.job_title,
            placeholder="e.g. Senior Software Engineer, Data Scientist",
            max_chars=100,
            key="setup_job"
        )

        mode_choice = st.radio(
            "Select Assessment Mode:",
            options=["HR Behavioral Interview", "Technical MCQ Quiz"],
            index=0 if st.session_state.mode == "hr" else (1 if st.session_state.mode == "mcq" else 0)
        )
        
        uploaded_file = st.file_uploader(
            "Upload Document (PDF format only)",
            type=["pdf"],
            help="Upload your resume (for HR mode) or a technical syllabus/study guide (for MCQ mode)."
        )

        st.session_state.candidate_name = name.strip()
        st.session_state.job_title = job.strip()
        st.session_state.mode = "hr" if mode_choice == "HR Behavioral Interview" else "mcq"

        st.markdown("<br>", unsafe_allow_html=True)
        
        if st.button("Upload and Analyze Profile", use_container_width=True):
            if not name.strip():
                st.error("Please enter your full name.")
            elif not job.strip():
                st.error("Please enter your target role or topic.")
            elif not uploaded_file:
                st.error("Please upload a PDF file.")
            else:
                _process_step1_data(uploaded_file)

def _process_step1_data(file_obj):
    with st.spinner("Analyzing document and running ATS assessment..."):
        try:
            # 1. Extract text from PDF
            raw_text = pdf_processor.extract_text_from_pdf(file_obj)
            st.session_state.resume_text = raw_text
            
            # 2. Evaluate against Target Job Title
            evaluation = ai_engine.evaluate_resume(raw_text, st.session_state.job_title)
            st.session_state.resume_score = evaluation
            
            # 3. Advance to Step 2
            st.session_state.step = 2
            st.rerun()
        except Exception as e:
            st.error(f"Failed to analyze profile: {e}")

# ── STEP 2: RESUME ATS SCORING ────────────────────────────────────────────────
def render_step2_scoring():
    st.markdown(
        """
        <div style="text-align:center; padding: 2.5rem 0 1.5rem;">
            <h1 style="font-size:3rem; font-weight:900; margin-bottom:0.4rem;">
                ATS Profile Analysis
            </h1>
            <p style="color:#6d28d9; font-size:1.15rem; font-weight:500; margin-bottom:0.4rem;">
                Step 2 of 4: ATS score feedback and keyword match checks.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    ev = st.session_state.resume_score or {}
    score = ev.get("atsScore", 50)
    keywords = ev.get("missingKeywords", [])
    feedback = ev.get("feedback", "No analysis details returned.")
    summary = ev.get("summary", "No background summary generated.")

    score_color = "#16a34a" if score >= 80 else ("#d97706" if score >= 60 else "#dc2626")

    _, content_col, _ = st.columns([1, 2, 1])
    with content_col:
        st.markdown(
            f"""
            <div style="text-align:center;margin:1.5rem 0;">
                <span style="display:inline-block;padding:12px 40px;border-radius:28px;
                      background:{score_color}22;color:{score_color};border:2px solid {score_color};
                      font-weight:900;font-size:1.5rem;">
                    ATS Match Score: {score}%
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.progress(score / 100)

        with st.expander("Candidate Summary Profile", expanded=True):
            st.write(summary)

        with st.expander("Recruiter Feedback", expanded=True):
            st.write(feedback)

        with st.expander("Missing Keywords and Skills", expanded=True):
            if keywords:
                for kw in keywords:
                    st.markdown(f"- {kw}")
            else:
                st.write("Profile has matching keywords and technical credentials.")

        st.markdown("<br>", unsafe_allow_html=True)
        
        btn_label = "Proceed to Live HR Interview" if st.session_state.mode == "hr" else "Proceed to Technical MCQ Assessment"
        if st.button(btn_label, use_container_width=True):
            # Reset/Initialize state for Step 3
            _reset_step3_state()
            st.session_state.step = 3
            st.rerun()

        if st.button("Change Profile Setup", use_container_width=True):
            st.session_state.step = 1
            st.rerun()

def _reset_step3_state():
    st.session_state.evaluation = None
    st.session_state.integrity_stats = {"tabs": 0, "pastes": 0, "fs_exits": 0}
    
    if st.session_state.mode == "hr":
        st.session_state.hr_messages  = []
        st.session_state.hr_turn      = 0
        st.session_state.hr_questions = []
        st.session_state.hr_answers   = []
        st.session_state.hr_waiting   = False
        st.session_state.last_spoken_turn = -1
        st.session_state.last_processed_transcript = ""
    else:
        st.session_state.mcq_questions  = []
        st.session_state.mcq_current    = 0
        st.session_state.mcq_answers    = []
        st.session_state.mcq_start_time = None

# ── STEP 3: LIVE ASSESSMENT (HR / MCQ) ────────────────────────────────────────
def render_step3_assessment():
    if st.session_state.mode == "hr":
        _render_step3_hr()
    else:
        _render_step3_mcq()

# ── Step 3: HR View ────────────────────────────────────────
def _render_step3_hr():
    name = st.session_state.candidate_name
    job  = st.session_state.job_title
    summary = (st.session_state.resume_score or {}).get("summary", "")

    # Run proctoring
    p_stats = run_proctoring(key="hr_proctoring")
    if p_stats:
        st.session_state.integrity_stats = p_stats

    # Handle pending LLM answer
    if st.session_state.hr_waiting:
        with st.spinner("Interview Coach is typing response..."):
            _get_coach_response(name, job)
        st.rerun()

    # Initialise conversation with resume summary context
    if not st.session_state.hr_messages:
        system_prompt = ai_engine.get_interview_coach_system_prompt(name, job, summary, TOTAL_TURNS)
        st.session_state.hr_messages = [{"role": "system", "content": system_prompt}]
        with st.spinner("Interview Coach is preparing opening question..."):
            _open_interview(name, job)
        st.rerun()

    h1, h2, h3 = st.columns([3, 1, 1])
    with h1:
        st.markdown("## Live Behavioral Interview")
        st.caption(f"Candidate: {name} · Target Role: {job}")
    with h2:
        st.metric("Turn", f"{st.session_state.hr_turn} / {TOTAL_TURNS}")
    with h3:
        if st.button("Cancel Pipeline", key="hr_cancel"):
            st.session_state.step = 1
            st.rerun()

    st.progress(
        min(st.session_state.hr_turn / TOTAL_TURNS, 1.0),
        text=f"Interview Progress: Turn {st.session_state.hr_turn} of {TOTAL_TURNS}",
    )
    st.divider()

    cam_col, chat_col = st.columns([1, 2], gap="large")

    with cam_col:
        st.markdown(
            """
            <div class="aip-card" style="text-align:center;padding:20px;">
                <h4 style="color:#6d28d9;margin:0 0 4px;">Interview Coach</h4>
                <p style="color:#475569;font-size:.78rem;margin:0;font-weight:normal !important;">AI Senior HR Professional</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            "<p style='color:#475569;font-weight:600;margin-bottom:6px;'>Your Camera Feed</p>",
            unsafe_allow_html=True,
        )
        # Automatic camera activation
        render_camera_feed(key="hr-webcam")

    with chat_col:
        st.markdown(
            "<h4 style='color:#6d28d9;margin-bottom:12px;'>Interview Session Log</h4>",
            unsafe_allow_html=True,
        )

        chat_box = st.container(height=340)
        with chat_box:
            for msg in st.session_state.hr_messages:
                if msg["role"] == "system":
                    continue
                if msg["role"] == "assistant":
                    with st.chat_message("assistant"):
                        st.markdown(f"**Interview Coach:** {msg['content']}")
                elif msg["role"] == "user":
                    content = msg["content"]
                    if content.startswith("[Candidate"):
                        clean = content.split("]:", 1)[-1].strip()
                    else:
                        clean = content
                    with st.chat_message("user"):
                        st.markdown(f"**{name}:** {clean}")

        interview_over = st.session_state.hr_turn >= TOTAL_TURNS

        # Automatic Audio Turn-Taking Bridge
        tts_text = ""
        if st.session_state.hr_messages:
            last_msg = st.session_state.hr_messages[-1]
            if last_msg["role"] == "assistant":
                tts_text = last_msg["content"]

        if not interview_over:
            st.markdown("<p style='color:#6d28d9;font-size:0.9rem;font-weight:600;margin-bottom:0.2rem;'>Voice Control Status</p>", unsafe_allow_html=True)
            
            # Embed the automatic voice component
            transcript = audio_component(tts_text=tts_text, key=f"audio_component_turn_{st.session_state.hr_turn}")
            
            if transcript is not None and transcript != st.session_state.get("last_processed_transcript"):
                st.session_state.last_processed_transcript = transcript
                if transcript.startswith("ERROR:"):
                    st.warning(f"Audio Input Issue: {transcript.replace('ERROR:', '').strip()}. You can type your response below instead.")
                elif transcript.strip():
                    _process_answer(transcript.strip())

            # Text input fallback
            user_input = st.chat_input(
                f"Type your response, {name}...",
                key=f"hr_chat_input_{st.session_state.hr_turn}",
            )
            if user_input and user_input.strip():
                _process_answer(user_input.strip())

        if interview_over:
            st.success("Interview complete. Proceed to Step 4 to generate your evaluation report.")
            if st.button(
                "Proceed to Evaluation Dashboard",
                key="hr_evaluate_btn",
                use_container_width=True,
            ):
                _evaluate_hr(name, job)

def _open_interview(name: str, job: str):
    try:
        opening = ai_engine.get_next_hr_message(
            conversation=st.session_state.hr_messages,
            turn=0,
            total_turns=TOTAL_TURNS,
            name=name,
        )
        st.session_state.hr_messages.append({"role": "assistant", "content": opening})
        st.session_state.hr_questions.append(opening)
    except Exception as exc:
        st.error(f"Could not reach Interview Coach: {exc}")

def _process_answer(answer: str):
    st.session_state.hr_messages.append(
        {"role": "user", "content": f"[Candidate response]: {answer}"}
    )
    st.session_state.hr_answers.append(answer)
    st.session_state.hr_turn    += 1
    st.session_state.hr_waiting  = True
    st.rerun()

def _get_coach_response(name: str, job: str):
    try:
        reply = ai_engine.get_next_hr_message(
            conversation=st.session_state.hr_messages,
            turn=st.session_state.hr_turn,
            total_turns=TOTAL_TURNS,
            name=name,
        )
        st.session_state.hr_messages.append({"role": "assistant", "content": reply})
        st.session_state.hr_questions.append(reply)
    except Exception as exc:
        fallback = "I apologize - I am having a brief connection issue. Please continue with your next response."
        st.session_state.hr_messages.append({"role": "assistant", "content": fallback})
        st.session_state.hr_questions.append(fallback)
        st.warning(f"Error: {exc}")
    finally:
        st.session_state.hr_waiting = False

def _evaluate_hr(name: str, job: str):
    with st.spinner("Interview Coach is writing your evaluation report..."):
        try:
            result = ai_engine.evaluate_hr_session(
                name        = name,
                job         = job,
                hr_questions= st.session_state.hr_questions,
                hr_answers  = st.session_state.hr_answers,
                total_turns = TOTAL_TURNS,
            )
            st.session_state.evaluation = {"mode": "hr", **result}
            st.session_state.step       = 4
            st.rerun()
        except Exception as exc:
            st.error(f"Evaluation failed: {exc}")

# ── Step 3: MCQ View ───────────────────────────────────────
def _render_step3_mcq():
    name  = st.session_state.candidate_name
    topic = st.session_state.job_title

    # Run proctoring
    p_stats = run_proctoring(key="mcq_proctoring")
    if p_stats:
        st.session_state.integrity_stats = p_stats

    h1, h2 = st.columns([4, 1])
    with h1:
        st.markdown(f"## MCQ Assessment - {topic}")
        st.caption(f"Candidate: {name}")
    with h2:
        if st.button("Cancel Pipeline", key="mcq_cancel"):
            st.session_state.step = 1
            st.rerun()

    st.divider()

    # Generate MCQ questions based on target topic
    if not st.session_state.mcq_questions:
        with st.spinner(f"Interview Coach is generating {MCQ_COUNT} questions for {topic}..."):
            try:
                qs = ai_engine.generate_mcq_questions(topic, count=MCQ_COUNT)
                st.session_state.mcq_questions  = qs
                st.session_state.mcq_answers    = [None] * len(qs)
                st.session_state.mcq_start_time = time.time()
                st.session_state.mcq_current    = 0
            except Exception as exc:
                st.error(f"Failed to generate questions: {exc}")
                if st.button("Back to Setup", key="mcq_gen_fail_back"):
                    st.session_state.step = 1
                    st.rerun()
                return
        st.rerun()

    questions = st.session_state.mcq_questions
    total     = len(questions)
    cur       = st.session_state.mcq_current
    answers   = st.session_state.mcq_answers
    answered  = sum(1 for a in answers if a is not None)

    p1, p2, p3 = st.columns([3, 1, 1])
    with p1:
        st.progress(answered / total, text=f"Progress: {answered} / {total} answered")
    with p2:
        st.markdown(f"<div style='text-align:center;color:#6d28d9;font-weight:700;font-size:1.1rem;'>Question {cur + 1} / {total}</div>", unsafe_allow_html=True)
    with p3:
        elapsed = int(time.time() - st.session_state.mcq_start_time) if st.session_state.mcq_start_time else 0
        m, s = divmod(elapsed, 60)
        st.markdown(f"<div style='text-align:center;color:#475569;padding-top:4px;'>Time: {m:02d}:{s:02d}</div>", unsafe_allow_html=True)

    # Dot navigator
    dot_cols = st.columns(total)
    for i, col in enumerate(dot_cols):
        with col:
            ans   = answers[i]
            color = "#6d28d9" if i == cur else ("#16a34a" if ans is not None else "#475569")
            if st.button(str(i + 1), key=f"dot_{i}", use_container_width=True):
                st.session_state.mcq_current = i
                st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    q = questions[cur]
    st.markdown(
        f"""
        <div class="aip-card">
            <div style="color:#6d28d9;font-size:.78rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;margin-bottom:10px;">
                Question {cur + 1} of {total}
            </div>
            <p style="color:#0f172a;font-size:1.1rem;font-weight:700;line-height:1.65;margin:0;">{q['question']}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    labels = [f"{chr(65+idx)}. {opt}" for idx, opt in enumerate(q.get("options", []))]

    selected_label = st.radio(
        "Select your answer:",
        options=labels,
        index=answers[cur],
        key=f"mcq_radio_{cur}",
        label_visibility="collapsed",
    )

    if selected_label is not None:
        new_idx = labels.index(selected_label)
        if answers[cur] != new_idx:
            st.session_state.mcq_answers[cur] = new_idx

    nav1, nav2, nav3 = st.columns([1, 2, 1])

    with nav1:
        if cur > 0:
            if st.button("Previous", key="mcq_prev", use_container_width=True):
                st.session_state.mcq_current -= 1
                st.rerun()

    with nav2:
        unanswered = total - sum(1 for a in st.session_state.mcq_answers if a is not None)
        if unanswered > 0:
            st.markdown(f"<div style='text-align:center;color:#d97706;font-size:.85rem;padding-top:8px;'>Warning: {unanswered} question(s) unanswered</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div style='text-align:center;color:#16a34a;font-size:.85rem;padding-top:8px;'>All questions answered</div>", unsafe_allow_html=True)

    with nav3:
        is_last = cur == total - 1
        btn_txt = "Submit Quiz" if is_last else "Next"
        if st.button(btn_txt, key="mcq_next", use_container_width=True):
            if is_last:
                _submit_mcq()
            else:
                st.session_state.mcq_current += 1
                st.rerun()

def _submit_mcq():
    with st.spinner("Interview Coach is evaluating your answers..."):
        try:
            result = ai_engine.evaluate_mcq_session(
                name      = st.session_state.candidate_name,
                topic     = st.session_state.job_title,
                questions = st.session_state.mcq_questions,
                answers   = st.session_state.mcq_answers,
            )
            st.session_state.evaluation = {"mode": "mcq", **result}
            st.session_state.step       = 4
            st.rerun()
        except Exception as exc:
            st.error(f"Evaluation failed: {exc}")

# ── STEP 4: FINAL EVALUATION DASHBOARD ────────────────────────────────────────
def render_step4_dashboard():
    ev   = st.session_state.get("evaluation") or {}
    mode = ev.get("mode", "mcq")
    name = st.session_state.candidate_name
    job  = st.session_state.job_title
    mode_label = "HR Behavioral Interview" if mode == "hr" else "MCQ Technical Assessment"

    st.markdown(
        f"""
        <div style="text-align:center;padding:1.5rem 0 .5rem;">
            <h1>Evaluation Report Dashboard</h1>
            <p style="color:#475569;margin-top:.25rem;">
                Candidate: {name} &nbsp;·&nbsp; Target Job: {job} &nbsp;·&nbsp; Mode: {mode_label}
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.divider()

    # Always render Step 2 ATS score matching summary in dashboard
    ats_score = (st.session_state.resume_score or {}).get("atsScore", 0)
    st.markdown(f"### Resume ATS Match Score: **{ats_score}%**")
    st.progress(ats_score / 100)
    st.markdown("<br>", unsafe_allow_html=True)

    if mode == "mcq":
        _render_mcq_report(ev)
    else:
        _render_hr_report(ev)

    _render_integrity_stats()

    st.divider()
    _render_actions()

def _render_mcq_report(ev: dict):
    score_pct = ev.get("score_pct", 0)
    correct   = ev.get("correct",   0)
    incorrect = ev.get("incorrect", 0)
    skipped   = ev.get("skipped",   0)
    verdict   = ev.get("verdict", "Competent")
    
    tier_colors = {
        "Expert":            "#16a34a",
        "Proficient":        "#6d28d9",
        "Competent":         "#0891b2",
        "Developing":        "#d97706",
        "Needs Improvement": "#dc2626",
    }
    color = tier_colors.get(verdict, "#6d28d9")

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Assessment Score", f"{score_pct}%")
    with c2: st.metric("Correct Answers",  correct)
    with c3: st.metric("Incorrect Answers", incorrect)
    with c4: st.metric("Skipped",          skipped)

    st.markdown(
        f"""
        <div style="text-align:center;margin:1.5rem 0;">
            <span style="display:inline-block;padding:10px 36px;border-radius:24px;
                  background:{color}22;color:{color};border:2px solid {color};
                  font-weight:700;font-size:1.15rem;">
                Assessment Tier: {verdict}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    a_col, b_col = st.columns(2)
    with a_col:
        with st.expander("Technical Feedback", expanded=True):
            st.write(ev.get("technicalFeedback", "None"))
        if ev.get("strongAreas"):
            with st.expander("Strong Areas", expanded=True):
                for s in ev["strongAreas"]:
                    st.markdown(f"Verified: {s}")

    with b_col:
        with st.expander("Behavioral Feedback", expanded=True):
            st.write(ev.get("behavioralFeedback", "None"))
        if ev.get("weakAreas"):
            with st.expander("Areas to Improve", expanded=True):
                for w in ev["weakAreas"]:
                    st.markdown(f"Goal: {w}")

    _render_roadmap(ev.get("roadmap", []))

def _render_hr_report(ev: dict):
    overall = ev.get("overallScore",        60)
    comm    = ev.get("communicationScore",  60)
    culture = ev.get("culturalFitScore",    60)
    conf    = ev.get("confidenceScore",     60)
    verdict = ev.get("hiringVerdict",  "Maybe")
    
    hire_colors = {
        "Strong Hire": "#16a34a",
        "Hire":        "#6d28d9",
        "Maybe":       "#d97706",
        "No Hire":     "#dc2626",
    }
    color = hire_colors.get(verdict, "#6d28d9")

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Interview Overall", f"{overall} / 100")
    with c2: st.metric("Communication",    f"{comm} / 100")
    with c3: st.metric("Cultural Fit",     f"{culture} / 100")
    with c4: st.metric("Confidence",       f"{conf} / 100")

    st.markdown(
        f"""
        <div style="text-align:center;margin:1.5rem 0;">
            <span style="display:inline-block;padding:10px 36px;border-radius:24px;
                  background:{color}22;color:{color};border:2px solid {color};
                  font-weight:700;font-size:1.1rem;">
                Hiring Verdict: {verdict}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    for label, score, comment_key in [
        ("Communication and Clarity",        comm,    "communicationComment"),
        ("Cultural Fit and Professionalism",  culture, "culturalFitComment"),
        ("Confidence and Self-Awareness",     conf,    "confidenceComment"),
    ]:
        st.markdown(f"**{label}: {score} / 100**")
        st.progress(score / 100)
        st.caption(ev.get(comment_key, ""))
        st.markdown("")

    st.markdown("<br>", unsafe_allow_html=True)

    s_col, i_col = st.columns(2)
    with s_col:
        with st.expander("Strengths Identified", expanded=True):
            for s in ev.get("strengths", []):
                st.markdown(f"Strength: {s}")
    with i_col:
        with st.expander("Areas for Improvement", expanded=True):
            for imp in ev.get("improvements", []):
                st.markdown(f"Improvement: {imp}")

    turn_feedback = ev.get("turnFeedback", [])
    if turn_feedback:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("### Turn-by-Turn Q and A Coaching Breakdown")
        hr_answers = st.session_state.get("hr_answers", [])
        for tf in turn_feedback:
            t_num = tf.get("turn", 1)
            q_txt = tf.get("question", "")
            label = f"Turn {t_num}" + (f" - {q_txt[:55]}..." if len(q_txt) > 55 else f" - {q_txt}")
            with st.expander(label):
                if q_txt:
                    st.markdown(f"**Interview Coach:** {q_txt}")
                idx = t_num - 1
                if 0 <= idx < len(hr_answers):
                    st.markdown(f"**Your Answer:** {hr_answers[idx] or 'No response'}")
                st.info(f"Assessment: {tf.get('assessment', 'None')}")

    _render_roadmap(ev.get("roadmap", []))

def _render_integrity_stats():
    stats = st.session_state.get("integrity_stats", {})
    if not stats:
        return
    
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### Session Integrity")
    
    c1, c2, c3 = st.columns(3)
    
    tabs = stats.get("tabs", 0)
    pastes = stats.get("pastes", 0)
    fs_exits = stats.get("fs_exits", 0)
    
    with c1:
        st.metric("Tab Switches", tabs, delta=f"{tabs} violations" if tabs > 0 else "Clean", delta_color="inverse")
    with c2:
        st.metric("Copy/Paste Attempts", pastes, delta=f"{pastes} violations" if pastes > 0 else "Clean", delta_color="inverse")
    with c3:
        st.metric("Fullscreen Exits", fs_exits, delta=f"{fs_exits} violations" if fs_exits > 0 else "Clean", delta_color="inverse")

def _render_roadmap(steps: list):
    if not steps:
        return
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### Personalized Learning Roadmap")
    for i, step in enumerate(steps, 1):
        st.markdown(
            f"""
            <div class="aip-card" style="margin-bottom:8px;padding:14px 20px;display:flex;gap:16px;align-items:center;">
                <span style="color:#6d28d9;font-weight:800;font-size:1.1rem;min-width:24px;">
                    {i}
                </span>
                <span style="color:#0f172a;font-size:.9rem;font-weight:700;">{step}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

def _render_actions():
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("New Session", key="dash_new", use_container_width=True):
            _reset_all()
            st.session_state.step = 1
            st.rerun()
    with col2:
        if st.button("Print / Save PDF", key="dash_print", use_container_width=True):
            st.info("Press Ctrl+P (or Cmd+P) to print or save as PDF.")
    with col3:
        if st.button("Copy Summary", key="dash_copy", use_container_width=True):
            _show_copy_text()

def _reset_all():
    keys = [
        "mode", "evaluation", "resume_text", "resume_score",
        "mcq_questions", "mcq_current", "mcq_answers", "mcq_start_time",
        "hr_messages", "hr_turn", "hr_questions", "hr_answers", "hr_waiting",
        "last_spoken_turn", "last_processed_transcript"
    ]
    for k in keys:
        if k in st.session_state:
            del st.session_state[k]

def _show_copy_text():
    ev   = st.session_state.get("evaluation") or {}
    mode = ev.get("mode", "mcq")
    name = st.session_state.candidate_name
    job  = st.session_state.job_title
    ats_score = (st.session_state.resume_score or {}).get("atsScore", 0)

    if mode == "mcq":
        score   = ev.get("score_pct", 0)
        verdict = ev.get("verdict", "None")
        text = (
            f"AI Placement Portal - MCQ Assessment\n"
            f"Candidate: {name} | Topic: {job}\n"
            f"Resume ATS Score: {ats_score}%\n"
            f"Quiz Score: {score}% | Tier: {verdict}"
        )
    else:
        score   = ev.get("overallScore", 0)
        verdict = ev.get("hiringVerdict", "None")
        text = (
            f"AI Placement Portal - HR Behavioral Interview\n"
            f"Candidate: {name} | Role: {job}\n"
            f"Resume ATS Score: {ats_score}%\n"
            f"Interview Overall: {score}/100 | Verdict: {verdict}"
        )
    st.code(text, language=None)
    st.caption("Select all and copy the text above.")

# ── ROUTER ────────────────────────────────────────────────────────────────────
def main():
    step = st.session_state.step
    if step == 1:
        render_step1_setup()
    elif step == 2:
        render_step2_scoring()
    elif step == 3:
        render_step3_assessment()
    elif step == 4:
        render_step4_dashboard()
    else:
        st.error(f"Unknown step pipeline: {step}")
        if st.button("Reset Pipeline"):
            st.session_state.step = 1
            st.rerun()

if __name__ == "__main__":
    main()
