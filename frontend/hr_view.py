"""
frontend/hr_view.py — Live HR Behavioral Interview with Interview Coach.

Streamlit rerun-based state machine:
  ┌──────────────────────────────────────────────────────────────────────┐
  │ Render call                                                          │
  │   if hr_waiting → spinner → _get_coach_response() → rerun           │
  │   elif hr_messages empty → spinner → _open_interview() → rerun      │
  │   else → render chat + input                                         │
  │     user submits → _process_answer() → hr_waiting=True → rerun      │
  │   if turn >= TOTAL_TURNS → show evaluate button                     │
  └──────────────────────────────────────────────────────────────────────┘
"""

import sys
from pathlib import Path
import json
import io
import base64

import streamlit as st
from gtts import gTTS
from streamlit_mic_recorder import speech_to_text

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.ai_engine import (
    evaluate_hr_session,
    get_interview_coach_system_prompt,
    get_next_hr_message,
)
from backend.video_handler import render_camera_feed

TOTAL_TURNS = 5


def render_hr() -> None:
    name = st.session_state.candidate_name
    job  = st.session_state.job_title

    # ── Pending LLM response — handle BEFORE any UI rendering ────────────────
    if st.session_state.hr_waiting:
        with st.spinner("Interview Coach is thinking..."):
            _get_coach_response(name, job)
        st.rerun()

    # ── Initialise conversation on first entry ────────────────────────────────
    if not st.session_state.hr_messages:
        system_prompt = get_interview_coach_system_prompt(name, job, TOTAL_TURNS)
        st.session_state.hr_messages = [{"role": "system", "content": system_prompt}]
        with st.spinner("Interview Coach is preparing your opening message..."):
            _open_interview(name, job)
        st.rerun()

    # ── Header row ────────────────────────────────────────────────────────────
    h1, h2, h3 = st.columns([3, 1, 1])
    with h1:
        st.markdown("## HR Behavioral Interview")
        st.caption(f"Candidate: **{name}** · Role: **{job}**")
    with h2:
        st.metric("Turn", f"{st.session_state.hr_turn} / {TOTAL_TURNS}")
    with h3:
        if st.button("Exit", key="hr_exit"):
            st.session_state.view = "setup"
            st.session_state.mode = None
            st.rerun()

    st.progress(
        min(st.session_state.hr_turn / TOTAL_TURNS, 1.0),
        text=f"Interview Progress: Turn {st.session_state.hr_turn} of {TOTAL_TURNS}",
    )
    st.divider()

    # ── Two-column layout: coach panel + chat ─────────────────────────────────
    cam_col, chat_col = st.columns([1, 2], gap="large")

    # ── Left: coach avatar + webcam ───────────────────────────────────────────
    with cam_col:
        st.markdown(
            """
            <div class="aip-card" style="text-align:center;padding:20px;">
                <h4 style="color:#a78bfa;margin:0 0 4px;">Interview Coach</h4>
                <p style="color:#64748b;font-size:.78rem;margin:0;">AI Senior HR Professional</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            "<p style='color:#94a3b8;font-weight:600;margin-bottom:6px;'>Your Camera</p>",
            unsafe_allow_html=True,
        )
        render_camera_feed(key="hr-webcam")

    # ── Right: chat thread + input ────────────────────────────────────────────
    with chat_col:
        st.markdown(
            "<h4 style='color:#a78bfa;margin-bottom:12px;'>Interview Session</h4>",
            unsafe_allow_html=True,
        )

        # Render conversation history
        chat_box = st.container(height=380)
        with chat_box:
            for msg in st.session_state.hr_messages:
                if msg["role"] == "system":
                    continue
                if msg["role"] == "assistant":
                    with st.chat_message("assistant"):
                        st.markdown(f"**Interview Coach:** {msg['content']}")
                elif msg["role"] == "user":
                    # Filter internal prompts sent to the LLM
                    content = msg["content"]
                    if content.startswith("[Candidate"):
                        # Strip prefix to show the clean answer
                        clean = content.split("]:", 1)[-1].strip()
                    else:
                        clean = content
                    with st.chat_message("user"):
                        st.markdown(f"**{name}:** {clean}")

        interview_over = st.session_state.hr_turn >= TOTAL_TURNS

        # Active input
        if not interview_over:
            st.markdown("<p style='color:#a78bfa;font-size:0.9rem;font-weight:600;'>Your Turn</p>", unsafe_allow_html=True)

            # Voice input (Real-time browser extraction)
            voice_text = speech_to_text(
                start_prompt="Speak Answer",
                stop_prompt="Stop Speaking",
                language='en',
                use_container_width=True,
                just_once=True,
                key=f"hr_stt_{st.session_state.hr_turn}"
            )

            # Text input
            user_input = st.chat_input(
                f"Type your response, {name}…",
                key=f"hr_chat_input_{st.session_state.hr_turn}",
            )

            # Handle Voice Input
            if voice_text:
                _process_answer(voice_text)

            # Handle Text Input
            elif user_input and user_input.strip():
                _process_answer(user_input.strip())

        # Text-to-Speech injection for the latest assistant message
        if st.session_state.hr_messages:
            last_msg = st.session_state.hr_messages[-1]
            if last_msg["role"] == "assistant":
                # Use hr_turn to track which turn we've spoken. 
                # Turn 0 is the opening.
                current_turn = st.session_state.hr_turn
                if current_turn > st.session_state.get("last_spoken_turn", -1):
                    st.session_state.last_spoken_turn = current_turn
                    _play_audio_tts(last_msg["content"])

        # Finished state
        if interview_over:
            st.success("Interview complete! Click below to generate your evaluation report.")
            if st.button(
                "Generate My Evaluation Report",
                key="hr_evaluate_btn",
                use_container_width=True,
            ):
                _evaluate_hr(name, job)


# ── State-machine helpers ──────────────────────────────────────────────────────

def _open_interview(name: str, job: str) -> None:
    """Fetch the coach's opening message (first LLM call)."""
    try:
        opening = get_next_hr_message(
            conversation=st.session_state.hr_messages,
            turn=0,
            total_turns=TOTAL_TURNS,
            name=name,
        )
        st.session_state.hr_messages.append({"role": "assistant", "content": opening})
        st.session_state.hr_questions.append(opening)
    except Exception as exc:
        st.error(f"Could not reach Interview Coach: {exc}")


def _process_answer(answer: str) -> None:
    """Record the candidate's answer, increment turn, flag for LLM response."""
    st.session_state.hr_messages.append(
        {"role": "user", "content": f"[Candidate's response]: {answer}"}
    )
    st.session_state.hr_answers.append(answer)
    st.session_state.hr_turn    += 1
    st.session_state.hr_waiting  = True
    st.rerun()


def _get_coach_response(name: str, job: str) -> None:
    """Fetch the coach's reply after a candidate answer (called during spinner)."""
    try:
        reply = get_next_hr_message(
            conversation=st.session_state.hr_messages,
            turn=st.session_state.hr_turn,
            total_turns=TOTAL_TURNS,
            name=name,
        )
        st.session_state.hr_messages.append({"role": "assistant", "content": reply})
        st.session_state.hr_questions.append(reply)
    except Exception as exc:
        fallback = (
            "I apologise — I'm having a brief connectivity issue. "
            "Please continue with your next thought."
        )
        st.session_state.hr_messages.append({"role": "assistant", "content": fallback})
        st.session_state.hr_questions.append(fallback)
        st.warning(f"LLM error: {exc}")
    finally:
        st.session_state.hr_waiting = False


def _evaluate_hr(name: str, job: str) -> None:
    """Evaluate the completed interview and navigate to the dashboard."""
    with st.spinner("Interview Coach is writing your evaluation report..."):
        try:
            result = evaluate_hr_session(
                name=name,
                job=job,
                hr_questions=st.session_state.hr_questions,
                hr_answers=st.session_state.hr_answers,
                total_turns=TOTAL_TURNS,
                resume_text=st.session_state.get("resume_text", ""),
            )
            st.session_state.evaluation = {"mode": "hr", **result}
            st.session_state.view = "dashboard"
            st.rerun()
        except Exception as exc:
            st.error(f"Evaluation failed: {exc}")


def _play_audio_tts(text: str) -> None:
    try:
        tts = gTTS(text, lang='en')
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        b64 = base64.b64encode(fp.getvalue()).decode()
        md = f"""
            <audio autoplay="true">
            <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
            </audio>
            """
        st.markdown(md, unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"Audio TTS Error: {e}")
