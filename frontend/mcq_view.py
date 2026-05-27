"""
frontend/mcq_view.py — MCQ Technical Assessment quiz interface.

Flow:
  1. First render: questions list is empty → spinner → generate via LLM → st.rerun()
  2. Subsequent renders: show current question with st.radio + dot nav + progress bar
  3. Last question "Submit" → evaluate → navigate to dashboard view
"""

import time

import streamlit as st

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.ai_engine import generate_mcq_questions, evaluate_mcq_session


# ── Constants ────────────────────────────────────────────────────────────────
_MCQ_COUNT = 10


def render_mcq() -> None:
    name  = st.session_state.candidate_name
    topic = st.session_state.job_title

    # ── Top bar ──────────────────────────────────────────────────────────────
    h1, h2 = st.columns([4, 1])
    with h1:
        st.markdown(f"## MCQ Assessment — *{topic}*")
        st.caption(f"Candidate: **{name}**")
    with h2:
        if st.button("Exit", key="mcq_exit"):
            st.session_state.view = "setup"
            st.session_state.mode = None
            st.rerun()

    st.divider()

    # ── Generate questions on first entry ────────────────────────────────────
    if not st.session_state.mcq_questions:
        with st.spinner(
            f"Interview Coach is generating {_MCQ_COUNT} questions for **{topic}**..."
        ):
            try:
                qs = generate_mcq_questions(topic, count=_MCQ_COUNT)
                st.session_state.mcq_questions  = qs
                st.session_state.mcq_answers    = [None] * len(qs)
                st.session_state.mcq_start_time = time.time()
                st.session_state.mcq_current    = 0
            except Exception as exc:
                st.error(f"Failed to generate questions: {exc}")
                if st.button("Back to Setup", key="mcq_gen_fail_back"):
                    st.session_state.view = "setup"
                    st.rerun()
                return
        st.rerun()

    questions = st.session_state.mcq_questions
    total     = len(questions)
    cur       = st.session_state.mcq_current
    answers   = st.session_state.mcq_answers
    answered  = sum(1 for a in answers if a is not None)

    # ── Progress bar + timer ─────────────────────────────────────────────────
    p1, p2, p3 = st.columns([3, 1, 1])
    with p1:
        st.progress(answered / total, text=f"Progress: {answered} / {total} answered")
    with p2:
        st.markdown(
            f"<div style='text-align:center;color:#a78bfa;font-weight:700;font-size:1.1rem;'>"
            f"Q {cur + 1} / {total}</div>",
            unsafe_allow_html=True,
        )
    with p3:
        elapsed = int(time.time() - st.session_state.mcq_start_time) if st.session_state.mcq_start_time else 0
        m, s = divmod(elapsed, 60)
        st.markdown(
            f"<div style='text-align:center;color:#64748b;padding-top:4px;'>Time {m:02d}:{s:02d}</div>",
            unsafe_allow_html=True,
        )

    # ── Question dot navigator ────────────────────────────────────────────────
    dot_cols = st.columns(total)
    for i, col in enumerate(dot_cols):
        with col:
            ans   = answers[i]
            color = "#7c5cfc" if i == cur else ("#22c55e" if ans is not None else "#334155")
            style = (
                f"text-align:center;background:{color};border-radius:50%;"
                f"width:32px;height:32px;line-height:32px;margin:auto;"
                f"color:white;font-size:.72rem;cursor:pointer;font-weight:700;"
            )
            if st.markdown(
                f"<div style='{style}'>{i + 1}</div>", unsafe_allow_html=True
            ) is None and st.button(
                " ", key=f"dot_{i}", help=f"Question {i + 1}",
                use_container_width=True,
            ):
                st.session_state.mcq_current = i
                st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Current question card ─────────────────────────────────────────────────
    q = questions[cur]
    st.markdown(
        f"""
        <div class="aip-card">
            <div style="color:#7c5cfc;font-size:.78rem;font-weight:700;
                        text-transform:uppercase;letter-spacing:.08em;margin-bottom:10px;">
                Question {cur + 1} of {total}
            </div>
            <p style="color:#f1f5f9;font-size:1.1rem;font-weight:600;
                      line-height:1.65;margin:0;">{q['question']}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Answer options ────────────────────────────────────────────────────────
    labels = [f"{chr(65+i)}.  {opt}" for i, opt in enumerate(q.get("options", []))]

    selected_label = st.radio(
        "Select your answer:",
        options=labels,
        index=answers[cur],       # None → no default; int → pre-select
        key=f"mcq_radio_{cur}",
        label_visibility="collapsed",
    )

    # Sync widget → session_state (Streamlit reruns on radio change automatically)
    if selected_label is not None:
        new_idx = labels.index(selected_label)
        if answers[cur] != new_idx:
            st.session_state.mcq_answers[cur] = new_idx

    # ── Navigation row ────────────────────────────────────────────────────────
    nav1, nav2, nav3 = st.columns([1, 2, 1])

    with nav1:
        if cur > 0:
            if st.button("← Previous", key="mcq_prev", use_container_width=True):
                st.session_state.mcq_current -= 1
                st.rerun()

    with nav2:
        unanswered = total - sum(1 for a in st.session_state.mcq_answers if a is not None)
        if unanswered > 0:
            st.markdown(
                f"<div style='text-align:center;color:#f59e0b;font-size:.85rem;padding-top:8px;'>"
                f"{unanswered} question{'s' if unanswered > 1 else ''} unanswered</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<div style='text-align:center;color:#22c55e;font-size:.85rem;padding-top:8px;'>"
                "All questions answered!</div>",
                unsafe_allow_html=True,
            )

    with nav3:
        is_last = cur == total - 1
        btn_txt = "Submit Quiz" if is_last else "Next"
        if st.button(btn_txt, key="mcq_next", use_container_width=True):
            if is_last:
                _submit_mcq()
            else:
                st.session_state.mcq_current += 1
                st.rerun()


# ── Private helper ────────────────────────────────────────────────────────────

def _submit_mcq() -> None:
    """Evaluate answers via LLM and navigate to the dashboard."""
    with st.spinner("Interview Coach is evaluating your answers..."):
        try:
            result = evaluate_mcq_session(
                name      = st.session_state.candidate_name,
                topic     = st.session_state.job_title,
                questions = st.session_state.mcq_questions,
                answers   = st.session_state.mcq_answers,
            )
            st.session_state.evaluation = {"mode": "mcq", **result}
            st.session_state.view       = "dashboard"
            st.rerun()
        except Exception as exc:
            st.error(f"Evaluation failed: {exc}")
