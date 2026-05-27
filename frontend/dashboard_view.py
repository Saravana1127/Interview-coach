"""
frontend/dashboard_view.py — Evaluation report for both MCQ and HR sessions.
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))


_HIRE_COLORS = {
    "Strong Hire": "#22c55e",
    "Hire": "#7c5cfc",
    "Maybe": "#f59e0b",
    "No Hire": "#ef4444",
}
_TIER_COLORS = {
    "Expert": "#22c55e",
    "Proficient": "#7c5cfc",
    "Competent": "#06b6d4",
    "Developing": "#f59e0b",
    "Needs Improvement": "#ef4444",
}


def render_dashboard() -> None:
    ev = st.session_state.get("evaluation") or {}
    mode = ev.get("mode", "mcq")
    name = st.session_state.candidate_name
    job = st.session_state.job_title
    mode_label = "HR Behavioral Interview" if mode == "hr" else "MCQ Technical Assessment"

    st.markdown(
        f"""
        <div style="text-align:center;padding:1.5rem 0 .5rem;">
            <h1>Evaluation Report</h1>
            <p style="color:#64748b;margin-top:.25rem;">
                {name} &nbsp;·&nbsp; {job} &nbsp;·&nbsp; {mode_label}
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.divider()

    if mode == "mcq":
        _render_mcq_report(ev)
    else:
        _render_hr_report(ev)

    st.divider()
    _render_actions()


def _render_mcq_report(ev: dict) -> None:
    score_pct = ev.get("score_pct", 0)
    correct = ev.get("correct", 0)
    incorrect = ev.get("incorrect", 0)
    skipped = ev.get("skipped", 0)
    verdict = ev.get("verdict", "Competent")
    color = _TIER_COLORS.get(verdict, "#7c5cfc")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Score", f"{score_pct}%")
    with c2:
        st.metric("Correct", correct)
    with c3:
        st.metric("Incorrect", incorrect)
    with c4:
        st.metric("Skipped", skipped)

    st.markdown(
        f"""
        <div style="text-align:center;margin:1.5rem 0;">
            <span style="display:inline-block;padding:10px 36px;border-radius:24px;
                  background:{color}22;color:{color};border:2px solid {color};
                  font-weight:700;font-size:1.15rem;">
                {verdict}
            </span>
            <p style="color:#64748b;margin-top:.5rem;font-size:.88rem;">
                Your competency tier
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(f"**Overall Score: {score_pct} / 100**")
    st.progress(score_pct / 100)
    st.markdown("<br>", unsafe_allow_html=True)

    a_col, b_col = st.columns(2)
    with a_col:
        with st.expander("Technical Feedback", expanded=True):
            st.write(ev.get("technicalFeedback", "—"))
        if ev.get("strongAreas"):
            with st.expander("Strong Areas", expanded=True):
                for s in ev["strongAreas"]:
                    st.markdown(f"- {s}")

    with b_col:
        with st.expander("Behavioral Feedback", expanded=True):
            st.write(ev.get("behavioralFeedback", "—"))
        if ev.get("weakAreas"):
            with st.expander("Areas to Improve", expanded=True):
                for w in ev["weakAreas"]:
                    st.markdown(f"- {w}")

    _render_roadmap(ev.get("roadmap", []))


def _render_hr_report(ev: dict) -> None:
    overall = ev.get("overallScore", 60)
    comm = ev.get("communicationScore", 60)
    culture = ev.get("culturalFitScore", 60)
    conf = ev.get("confidenceScore", 60)
    verdict = ev.get("hiringVerdict", "Maybe")
    color = _HIRE_COLORS.get(verdict, "#7c5cfc")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Overall", f"{overall} / 100")
    with c2:
        st.metric("Communication", f"{comm} / 100")
    with c3:
        st.metric("Cultural Fit", f"{culture} / 100")
    with c4:
        st.metric("Confidence", f"{conf} / 100")

    st.markdown(
        f"""
        <div style="text-align:center;margin:1.5rem 0;">
            <span style="display:inline-block;padding:10px 36px;border-radius:24px;
                  background:{color}22;color:{color};border:2px solid {color};
                  font-weight:700;font-size:1.1rem;">
                Verdict: {verdict}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Behavior Analysis")
    for label, score, comment_key in [
        ("Communication & Clarity", comm, "communicationComment"),
        ("Cultural Fit & Professionalism", culture, "culturalFitComment"),
        ("Confidence & Self-Awareness", conf, "confidenceComment"),
    ]:
        st.markdown(f"**{label}: {score} / 100**")
        st.progress(score / 100)
        st.caption(ev.get(comment_key, ""))
        st.markdown("")

    st.markdown("<br>", unsafe_allow_html=True)

    s_col, i_col = st.columns(2)
    with s_col:
        with st.expander("Strengths", expanded=True):
            for s in ev.get("strengths", []):
                st.markdown(f"- {s}")
    with i_col:
        with st.expander("Areas for Improvement", expanded=True):
            for imp in ev.get("improvements", []):
                st.markdown(f"- {imp}")

    turn_feedback = ev.get("turnFeedback", [])
    if turn_feedback:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("### Turn-by-Turn Feedback")
        hr_answers = st.session_state.get("hr_answers", [])
        for tf in turn_feedback:
            t_num = tf.get("turn", 1)
            q_txt = tf.get("question", "")
            label = f"Turn {t_num}" + (f" — {q_txt[:55]}..." if len(q_txt) > 55 else f" — {q_txt}")
            with st.expander(label):
                if q_txt:
                    st.markdown(f"**Interview Coach:** {q_txt}")
                idx = t_num - 1
                if 0 <= idx < len(hr_answers):
                    st.markdown(f"**Your Answer:** {hr_answers[idx] or '*(no response)*'}")
                st.info(f"**Assessment:** {tf.get('assessment', '—')}")

    _render_roadmap(ev.get("roadmap", []))


def _render_roadmap(steps: list) -> None:
    if not steps:
        return

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### Learning Roadmap")
    for i, step in enumerate(steps, 1):
        st.markdown(
            f"""
            <div class="aip-card" style="margin-bottom:8px;padding:14px 20px;display:flex;gap:16px;align-items:center;">
                <span style="color:#7c5cfc;font-weight:800;font-size:1.1rem;min-width:24px;">
                    {i}
                </span>
                <span style="color:#94a3b8;font-size:.9rem;">{step}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_actions() -> None:
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("New Session", key="dash_new", use_container_width=True):
            _reset_all()
            st.session_state.view = "setup"
            st.rerun()
    with col2:
        if st.button("Print / Save PDF", key="dash_print", use_container_width=True):
            st.info("Press Ctrl+P or Cmd+P to print or save as PDF.")
    with col3:
        if st.button("Copy Summary", key="dash_copy", use_container_width=True):
            _show_copy_text()


def _reset_all() -> None:
    keys = [
        "mode",
        "evaluation",
        "mcq_questions",
        "mcq_current",
        "mcq_answers",
        "mcq_start_time",
        "hr_messages",
        "hr_turn",
        "hr_questions",
        "hr_answers",
        "hr_waiting",
        "resume_text",
        "resume_name",
    ]
    for key in keys:
        if key in st.session_state:
            del st.session_state[key]


def _show_copy_text() -> None:
    ev = st.session_state.get("evaluation") or {}
    mode = ev.get("mode", "mcq")
    name = st.session_state.candidate_name
    job = st.session_state.job_title

    if mode == "mcq":
        score = ev.get("score_pct", 0)
        verdict = ev.get("verdict", "—")
        text = (
            f"AI Placement Portal — MCQ Assessment\n"
            f"Candidate: {name}  Topic: {job}\n"
            f"Score: {score}%  Tier: {verdict}"
        )
    else:
        score = ev.get("overallScore", 0)
        verdict = ev.get("hiringVerdict", "—")
        text = (
            f"AI Placement Portal — HR Behavioral Interview\n"
            f"Candidate: {name}  Role: {job}\n"
            f"Overall: {score}/100  Verdict: {verdict}"
        )

    st.code(text, language=None)
    st.caption("Select all and copy the text above.")
