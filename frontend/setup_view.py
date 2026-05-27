"""
frontend/setup_view.py — Landing page & mode/candidate configuration.
"""

import io

import streamlit as st


def render_setup() -> None:
    st.markdown(
        """
        <div style="text-align:center; padding: 2.5rem 0 1.5rem;">
            <h1 style="font-size:3rem; font-weight:900; margin-bottom:0.4rem;">
                AI Placement Portal
            </h1>
            <p style="color:#a78bfa; font-size:1.15rem; font-weight:500; margin-bottom:0.4rem;">
                AI-powered interview preparation platform
            </p>
            <p style="color:#64748b; font-size:0.92rem; max-width:520px; margin:0 auto 2rem;">
                Practice behavioral interviews with your Interview Coach, or take a timed MCQ assessment
                with instant reporting.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_hr, col_mcq = st.columns(2, gap="large")

    with col_hr:
        st.markdown(
            """
            <div class="aip-card" style="border-color:rgba(124,92,252,.5);text-align:center;min-height:220px;">
                <h3 style="color:#a78bfa;margin:.5rem 0 .4rem;">HR Behavioral Interview</h3>
                <p style="color:#64748b;font-size:.88rem;line-height:1.6;">
                    Live interview practice with your AI Coach, webcam support, and a detailed coaching report.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Start HR Interview", key="btn_mode_hr", use_container_width=True):
            st.session_state.mode = "hr"
            st.rerun()

    with col_mcq:
        st.markdown(
            """
            <div class="aip-card" style="border-color:rgba(6,182,212,.5);text-align:center;min-height:220px;">
                <h3 style="color:#06b6d4;margin:.5rem 0 .4rem;">MCQ Technical Assessment</h3>
                <p style="color:#64748b;font-size:.88rem;line-height:1.6;">
                    AI-generated, role-specific questions with timed progress tracking and a tailored learning roadmap.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Start MCQ Quiz", key="btn_mode_mcq", use_container_width=True):
            st.session_state.mode = "mcq"
            st.rerun()

    mode = st.session_state.get("mode")
    if not mode:
        _render_feature_highlights()
        return

    st.divider()

    _, form_col, _ = st.columns([1, 2, 1])
    with form_col:
        mode_label = "HR Behavioral Interview" if mode == "hr" else "MCQ Technical Assessment"
        st.markdown(
            f"<h3 style='text-align:center;color:#a78bfa;margin-bottom:1.5rem;'>Configure Your {mode_label}</h3>",
            unsafe_allow_html=True,
        )

        name = st.text_input(
            "Your Full Name",
            value=st.session_state.get("candidate_name", ""),
            placeholder="e.g. Alex Johnson",
            max_chars=60,
            key="inp_name",
        )
        job = st.text_input(
            "Job Role / Assessment Topic",
            value=st.session_state.get("job_title", ""),
            placeholder="e.g. Senior Software Engineer, Data Scientist",
            max_chars=100,
            key="inp_job",
        )

        if mode == "hr":
            uploaded = st.file_uploader(
                "Upload your resume",
                key="resume_upload",
            )

            if uploaded is not None:
                resume_text, resume_name = _read_resume_text(uploaded)
                if resume_text:
                    st.session_state.resume_text = resume_text
                    st.session_state.resume_name = resume_name
                    st.success(f"Resume loaded: {resume_name}")
                    _render_resume_preview(resume_text, resume_name)
                else:
                    st.error("Could not extract text from the uploaded file. Please try another file.")
                    st.session_state.resume_text = ""
                    st.session_state.resume_name = ""
            else:
                if st.session_state.get("resume_text"):
                    st.caption(f"Resume loaded: {st.session_state.get('resume_name', 'Unknown')}")

        st.session_state.candidate_name = name.strip()
        st.session_state.job_title = job.strip()

        st.markdown("<br>", unsafe_allow_html=True)

        btn_label = "Start Interview with Interview Coach" if mode == "hr" else "Generate & Start Quiz"
        if st.button(btn_label, key="btn_start", use_container_width=True):
            if not name.strip():
                st.error("Please enter your full name.")
            elif not job.strip():
                st.error("Please enter a job role or topic.")
            elif mode == "hr" and not st.session_state.get("resume_text", ""):
                st.error("Please upload a resume before starting the HR interview.")
            else:
                _reset_mode_state(mode)
                st.session_state.view = mode
                st.rerun()

        if st.button("Change Mode", key="btn_back", use_container_width=True):
            st.session_state.mode = None
            st.rerun()


# ── Private helpers ──────────────────────────────────────────────────────────

def _read_resume_text(uploaded_file) -> tuple[str, str]:
    """Extract text from any file format with multiple fallback methods."""
    import io
    import base64
    
    filename = uploaded_file.name.lower()
    raw = uploaded_file.getvalue()

    # Try text-based formats first (UTF-8 safe)
    text_extensions = (".txt", ".md", ".csv", ".json", ".log", ".xml", ".html", ".yml", ".yaml", ".ini", ".conf")
    if filename.endswith(text_extensions):
        try:
            return raw.decode("utf-8", errors="ignore").strip(), uploaded_file.name
        except Exception:
            pass

    # PDF extraction
    if filename.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            if text.strip():
                return text.strip(), uploaded_file.name
        except Exception:
            pass

    # Image extraction with OCR
    if filename.endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff", ".webp")):
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(raw))
            try:
                import pytesseract
                text = pytesseract.image_to_string(img)
                if text.strip():
                    return text.strip(), uploaded_file.name
            except Exception:
                pass
        except Exception:
            pass

    # DOCX extraction
    if filename.endswith(".docx"):
        try:
            from docx import Document
            doc = Document(io.BytesIO(raw))
            text = "\n".join(para.text for para in doc.paragraphs)
            if text.strip():
                return text.strip(), uploaded_file.name
        except Exception:
            pass

    # RTF extraction
    if filename.endswith(".rtf"):
        try:
            text = raw.decode("utf-8", errors="ignore")
            return text.strip(), uploaded_file.name
        except Exception:
            pass

    # XLSX extraction
    if filename.endswith((".xlsx", ".xls")):
        try:
            import openpyxl
            from io import BytesIO as BIO
            workbook = openpyxl.load_workbook(BIO(raw))
            text_parts = []
            for sheet in workbook.sheetnames:
                ws = workbook[sheet]
                for row in ws.iter_rows(values_only=True):
                    text_parts.append(" ".join(str(cell) if cell else "" for cell in row))
            text = "\n".join(text_parts)
            if text.strip():
                return text.strip(), uploaded_file.name
        except Exception:
            pass

    # PPTX extraction
    if filename.endswith(".pptx"):
        try:
            from pptx import Presentation
            prs = Presentation(io.BytesIO(raw))
            text_parts = []
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text"):
                        text_parts.append(shape.text)
            text = "\n".join(text_parts)
            if text.strip():
                return text.strip(), uploaded_file.name
        except Exception:
            pass

    # Fallback: Use file metadata as context
    file_size_mb = len(raw) / (1024 * 1024)
    fallback_text = f"File: {uploaded_file.name}\nSize: {file_size_mb:.2f} MB\nType: {uploaded_file.type or 'Unknown'}\n\nThis file format requires special processing. The HR evaluation will use the file metadata."
    return fallback_text, uploaded_file.name


def _reset_mode_state(mode: str) -> None:
    """Clear stale session state before entering a new session."""
    st.session_state.evaluation = None
    if mode == "hr":
        st.session_state.hr_messages = []
        st.session_state.hr_turn = 0
        st.session_state.hr_questions = []
        st.session_state.hr_answers = []
        st.session_state.hr_waiting = False
        st.session_state.last_spoken_turn = -1
    else:
        st.session_state.mcq_questions = []
        st.session_state.mcq_current = 0
        st.session_state.mcq_answers = []
        st.session_state.mcq_start_time = None


def _render_resume_preview(resume_text: str, resume_name: str) -> None:
    """Render a compact, truncated preview of the uploaded resume."""
    cleaned = "\n".join(line.strip() for line in resume_text.splitlines() if line.strip())
    if not cleaned:
        return

    preview = cleaned[:1000]
    if len(cleaned) > 1000:
        preview = f"{preview}\n..."

    with st.expander(f"Preview: {resume_name}", expanded=False):
        st.code(preview, language="text")


def _render_feature_highlights() -> None:
    st.markdown("<br>", unsafe_allow_html=True)
    f1, f2, f3 = st.columns(3)
    features = [
        (
            "AI Interview Coach",
            "Adaptive behavioral questions powered by a local LLM. Get real coaching feedback after every session.",
        ),
        (
            "Webcam Monitoring",
            "Live camera feed during HR interviews for an authentic, proctored experience.",
        ),
        (
            "Instant Reports",
            "Scored evaluation with a verdict, strengths, improvement areas, and a tailored learning roadmap.",
        ),
    ]
    for col, (title, desc) in zip([f1, f2, f3], features):
        with col:
            st.markdown(
                f"""
                <div class="aip-card" style="text-align:center;padding:20px;">
                    <h4 style="color:#a78bfa;margin:.5rem 0;">{title}</h4>
                    <p style="color:#64748b;font-size:.82rem;line-height:1.55;">{desc}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
