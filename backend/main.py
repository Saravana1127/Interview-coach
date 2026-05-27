"""
main.py — AI Placement Portal · FastAPI Backend

Endpoints
---------
GET  /api/health              Health check
POST /api/chat                Raw LLM proxy (HR turn-by-turn conversation)
POST /api/mcq/generate        Generate MCQ questions for a given topic
POST /api/hr/evaluate         Evaluate a completed HR interview
POST /api/mcq/evaluate        Evaluate a completed MCQ session
POST /api/proctoring/flag     Log a proctoring violation event

The frontend static files (frontend/) are served at "/" so that a single
`uvicorn backend.main:app` command boots the entire application.
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, List, Optional

# Ensure backend/ is on the path so `ai_engine` is importable whether uvicorn
# is launched as  `python -m uvicorn backend.main:app`  (cwd = project root)
# or as           `python -m uvicorn main:app`           (cwd = backend/)
_BACKEND_DIR = Path(__file__).parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ai_engine import (
    build_hr_evaluation_prompt,
    build_hr_system_prompt,
    build_mcq_evaluation_prompt,
    build_mcq_generation_prompt,
    call_llm,
)

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

load_dotenv()

API_URL       = os.getenv("OPENWEBUI_API_URL", "http://localhost:11434/v1/chat/completions")
DEFAULT_MODEL = os.getenv("MODEL_NAME", "llama3")
API_KEY       = os.getenv("OPENWEBUI_API_KEY", "")

app = FastAPI(
    title="AI Placement Portal",
    description="Backend API for the AI-powered mock interview simulator.",
    version="2.0.0",
)

# ---------------------------------------------------------------------------
# CORS — allow any origin so a standalone Live Server also works
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages:    List[ChatMessage]
    model:       Optional[str]   = None
    temperature: Optional[float] = 0.7
    apiUrl:      Optional[str]   = None


class McqGenerateRequest(BaseModel):
    topic: str
    count: int           = 10
    model: Optional[str] = None


class IntegrityStats(BaseModel):
    tabs:   int = 0
    pastes: int = 0
    mouse:  int = 0


class HrEvaluateRequest(BaseModel):
    name:               str
    jobTitle:           str
    assistantQuestions: List[str]
    candidateAnswers:   List[str]
    totalTurns:         int
    integrity:          IntegrityStats
    model:              Optional[str] = None


class McqQuestion(BaseModel):
    question:    str
    options:     List[str]
    correct:     int
    explanation: str
    selected:    Optional[int] = None
    timeSpent:   int           = 0


class McqEvaluateRequest(BaseModel):
    name:      str
    topic:     str
    questions: List[McqQuestion]
    integrity: IntegrityStats
    model:     Optional[str] = None


class ProctoringFlagRequest(BaseModel):
    type:    str
    phase:   str
    context: Optional[Any] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json(text: str):
    """Strip markdown fences and robustly parse JSON from an LLM response."""
    text = re.sub(r"```json\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"```\s*",     "", text)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Last-ditch: find the first { ... } or [ ... ] block
        m = re.search(r"[\[{][\s\S]*[\]}]", text)
        if m:
            return json.loads(m.group())
        raise ValueError(f"Could not parse JSON from LLM output: {text[:300]}")


def _fallback_hr(req: HrEvaluateRequest) -> dict:
    return {
        "communicationScore":   60,
        "communicationComment": "Completed the interview. Review transcript for details.",
        "culturalFitScore":     60,
        "culturalFitComment":   "Participated in all turns. Consider using the STAR method.",
        "confidenceScore":      60,
        "confidenceComment":    "Showed willingness to engage with all questions.",
        "overallScore":         60,
        "hiringVerdict":        "Maybe",
        "strengths":    ["Completed all interview turns", "Engaged with the interviewer", "Showed effort"],
        "improvements": ["Use the STAR method", "Provide specific examples", "Practice concise communication"],
        "turnFeedback": [
            {
                "turn":       i + 1,
                "question":   (q[:120] if q else ""),
                "assessment": (a if a else "No response provided"),
            }
            for i, (q, a) in enumerate(
                zip(req.assistantQuestions, req.candidateAnswers)
            )
        ],
    }


def _fallback_mcq(questions: List[McqQuestion], topic: str, score_pct: int) -> dict:
    times     = [q.timeSpent for q in questions]
    avg       = round(sum(times) / len(times)) if times else 0
    fastest_i = times.index(min(times)) if times else 0
    slowest_i = times.index(max(times)) if times else 0
    verdict   = (
        "Expert"            if score_pct >= 90 else
        "Proficient"        if score_pct >= 75 else
        "Competent"         if score_pct >= 50 else
        "Developing"        if score_pct >= 35 else
        "Needs Improvement"
    )
    return {
        "verdict":            verdict,
        "technicalFeedback":  f"Scored {score_pct}% on {topic}. Performance indicates a {verdict.lower()} level.",
        "behavioralFeedback": "Session completed. Review integrity metrics for details.",
        "timeAnalysis": {
            "averageTime":  avg,
            "fastestIndex": fastest_i,
            "slowestIndex": slowest_i,
        },
        "roadmap": [
            f"Review foundational concepts in {topic}",
            "Practice with additional mock assessments",
            "Follow structured online courses or tutorials",
            "Build real-world projects to solidify knowledge",
        ],
    }


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@app.get("/api/health", tags=["Utility"])
async def health():
    """Quick health-check — also tells the client which model is configured."""
    return {"status": "ok", "model": DEFAULT_MODEL, "api_url": API_URL}


@app.post("/api/chat", tags=["HR Interview"])
async def proxy_chat(req: ChatRequest):
    """
    Transparent proxy to the LLM backend.
    Used by the HR mode for turn-by-turn conversation with Sarah.
    Returns an OpenAI-compatible choices array.
    """
    api_url = req.apiUrl or API_URL
    model   = req.model   or DEFAULT_MODEL
    msgs    = [m.model_dump() for m in req.messages]

    try:
        content = await call_llm(msgs, req.temperature or 0.7, api_url, model, API_KEY)
        return {"choices": [{"message": {"role": "assistant", "content": content}}]}
    except httpx.ConnectError:
        raise HTTPException(502, f"Cannot reach LLM at {api_url}. Is Ollama/Open WebUI running?")
    except httpx.TimeoutException:
        raise HTTPException(504, "LLM request timed out after 90 seconds.")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"LLM returned HTTP {exc.response.status_code}: {exc.response.text[:300]}")
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/mcq/generate", tags=["MCQ"])
async def generate_mcq(req: McqGenerateRequest):
    """
    Ask the LLM to generate a JSON array of MCQ questions for `topic`.
    Returns { questions: [...] }.
    """
    model      = req.model or DEFAULT_MODEL
    system_msg = {"role": "system", "content": "You are a professional technical assessment system. Output only valid JSON with no markdown."}
    user_msg   = {"role": "user",   "content": build_mcq_generation_prompt(req.topic, req.count)}

    try:
        raw       = await call_llm([system_msg, user_msg], 0.7, API_URL, model, API_KEY)
        questions = _parse_json(raw)
        if not isinstance(questions, list) or not questions:
            raise ValueError("Expected a non-empty JSON array of questions")
        return {"questions": questions}
    except Exception as exc:
        raise HTTPException(500, f"MCQ generation failed: {exc}")


@app.post("/api/hr/evaluate", tags=["HR Interview"])
async def evaluate_hr(req: HrEvaluateRequest):
    """
    Evaluate a completed HR behavioral interview.
    Builds the transcript from assistantQuestions + candidateAnswers and calls the LLM.
    Returns a scored JSON report with strengths, improvements, and turn-by-turn feedback.
    """
    model = req.model or DEFAULT_MODEL

    transcript_parts = []
    for i, (q, a) in enumerate(zip(req.assistantQuestions, req.candidateAnswers)):
        transcript_parts.append(
            f"Turn {i + 1}:\nSarah: {q}\nCandidate: {a or '(no response)'}"
        )
    transcript     = "\n\n".join(transcript_parts)
    integrity_stats = (
        f"Tab switches: {req.integrity.tabs}, "
        f"Pastes: {req.integrity.pastes}, "
        f"Mouse exits: {req.integrity.mouse}"
    )

    system_msg = {"role": "system", "content": "You are an expert HR interview evaluator. Return only valid JSON."}
    user_msg   = {"role": "user",   "content": build_hr_evaluation_prompt(
        req.name, req.jobTitle, req.totalTurns, transcript, integrity_stats
    )}

    try:
        raw      = await call_llm([system_msg, user_msg], 0.3, API_URL, model, API_KEY)
        feedback = _parse_json(raw)
        return feedback
    except Exception:
        return _fallback_hr(req)


@app.post("/api/mcq/evaluate", tags=["MCQ"])
async def evaluate_mcq(req: McqEvaluateRequest):
    """
    Evaluate a completed MCQ session.
    Returns a JSON report with verdict, technical/behavioral feedback, time analysis,
    and a personalised learning roadmap.
    """
    model = req.model or DEFAULT_MODEL
    qs    = req.questions

    correct   = sum(1 for q in qs if q.selected == q.correct)
    incorrect = sum(1 for q in qs if q.selected is not None and q.selected != q.correct)
    skipped   = sum(1 for q in qs if q.selected is None)
    score_pct = round((correct / len(qs)) * 100) if qs else 0

    q_lines = []
    for i, q in enumerate(qs):
        sel    = q.options[q.selected] if q.selected is not None else "(skipped)"
        result = "Correct" if q.selected == q.correct else ("Skipped" if q.selected is None else "Incorrect")
        q_lines.append(
            f"Q{i+1}: {q.question}\n"
            f"  Selected: {sel}  Correct: {q.options[q.correct]}\n"
            f"  Time: {q.timeSpent}s  Result: {result}"
        )
    q_summary = "\n\n".join(q_lines)

    integrity_stats = (
        f"Tab switches: {req.integrity.tabs}, "
        f"Pastes: {req.integrity.pastes}, "
        f"Mouse exits: {req.integrity.mouse}"
    )

    system_msg = {"role": "system", "content": "You are an expert technical/HR assessment evaluator. Return only valid JSON."}
    user_msg   = {"role": "user",   "content": build_mcq_evaluation_prompt(
        req.name, req.topic,
        len(qs), correct, incorrect, skipped, score_pct,
        integrity_stats, q_summary,
    )}

    try:
        raw      = await call_llm([system_msg, user_msg], 0.3, API_URL, model, API_KEY)
        feedback = _parse_json(raw)
        return feedback
    except Exception:
        return _fallback_mcq(qs, req.topic, score_pct)


@app.post("/api/proctoring/flag", tags=["Proctoring"])
async def flag_proctoring(req: ProctoringFlagRequest):
    """
    Receive and log a proctoring violation from the frontend.
    In production this could be written to a database or audit log.
    """
    print(f"[PROCTOR] type={req.type!r}  phase={req.phase!r}  ctx={req.context}")
    return {"logged": True}


# ---------------------------------------------------------------------------
# Serve frontend static files
# Must come LAST so it doesn't shadow any /api/* routes.
# ---------------------------------------------------------------------------

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
else:
    @app.get("/")
    async def root():
        return {"message": "Frontend directory not found. Serve frontend/ separately."}


# ---------------------------------------------------------------------------
# Dev entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("BACKEND_PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
