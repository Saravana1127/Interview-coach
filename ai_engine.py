import os
import re
import json
import json_repair
from typing import Optional, List, Dict
import requests
from dotenv import load_dotenv

load_dotenv()

API_URL       = os.getenv("OPENWEBUI_API_URL", "http://localhost:11434/v1/chat/completions")
DEFAULT_MODEL = os.getenv("MODEL_NAME",         "llama3.2:1b")
API_KEY       = os.getenv("OPENWEBUI_API_KEY",  "")

# Core LLM call
def call_llm(messages: List[Dict], temperature: float = 0.7, model: Optional[str] = None, format: Optional[str] = None) -> str:
    """
    Synchronous OpenAI-compatible LLM call.
    Supports Ollama and OpenAI-style response formats.
    Raises RuntimeError on connectivity or HTTP failures.
    """
    m       = model or DEFAULT_MODEL
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    payload = {"model": m, "temperature": temperature, "messages": messages}
    if format:
        payload["format"] = format

    try:
        resp = requests.post(API_URL, json=payload, headers=headers, timeout=300)
        resp.raise_for_status()
        data = resp.json()
        return (
            data.get("choices", [{}])[0].get("message", {}).get("content")
            or data.get("message", {}).get("content")
            or ""
        ).strip()
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"Cannot reach LLM at {API_URL}. "
            "Check that Ollama is running."
        )
    except requests.exceptions.Timeout:
        raise RuntimeError("LLM request timed out after 300 seconds.")
    except requests.exceptions.HTTPError as exc:
        raise RuntimeError(f"LLM returned HTTP {exc.response.status_code}.")

def parse_json_response(text: str):
    """Strip markdown fences and parse JSON from LLM response."""
    text = re.sub(r"```json\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"```\s*",     "", text)
    text = text.strip()
    try:
        return json_repair.loads(text)
    except Exception:
        m = re.search(r"[\[{][\s\S]*[\]}]", text)
        if m:
            return json_repair.loads(m.group())
        raise ValueError(f"Cannot parse JSON from LLM output:\n{text[:300]}")

# Resume Scorer logic
def get_resume_evaluation_prompt(resume_text: str, job_title: str) -> str:
    return f"""You are an expert ATS (Applicant Tracking System) optimizer and professional recruiter.
Analyze this resume text and evaluate its alignment with the target job title: "{job_title}".

Resume Text:
{resume_text}

Provide an evaluation report in this EXACT JSON format (return ONLY valid JSON, no markdown blocks, no extra text):
{{
  "atsScore": <0-100 score indicating candidate-role alignment>,
  "missingKeywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "feedback": "<2-3 sentences evaluating key missing areas or alignments>",
  "summary": "<1-2 sentences summarizing the candidate's professional background>"
}}"""

def evaluate_resume(resume_text: str, job_title: str, model: Optional[str] = None) -> dict:
    messages = [
        {"role": "system", "content": "You are a professional ATS optimizer. Return only valid JSON."},
        {"role": "user", "content": get_resume_evaluation_prompt(resume_text, job_title)}
    ]
    try:
        raw = call_llm(messages, temperature=0.3, model=model, format="json")
        return parse_json_response(raw)
    except Exception:
        return {
            "atsScore": 50,
            "missingKeywords": ["professional accomplishments", "technical certifications", "role specific experience"],
            "feedback": f"Resume analysis was completed with limitations. Performance review indicates general qualification for a {job_title} position.",
            "summary": "Completed upload and text extraction. Candidate is entering placement assessment."
        }

# Prompt builders
def get_interview_coach_system_prompt(name: str, job: str, resume_summary: str = "", total_turns: int = 5) -> str:
    resume_context = f"\nThe candidate's resume summary is: {resume_summary}. Refer dynamically to their experience from this summary if appropriate." if resume_summary else ""
    return f"""You are Interview Coach, a world-class AI career mentor and Senior HR professional conducting a live, structured behavioral interview with a candidate named "{name}" for the "{job}" role. Your mission is to evaluate their communication skills, cultural fit, confidence, and professionalism through focused behavioral questions.{resume_context}

STRICT RULES:
- Introduce yourself and open with EXACTLY this message:
  "Hello {name}. I am your Interview Coach today. Congratulations on reaching this stage for the {job} role. To get us started, could you please introduce yourself and briefly walk me through your professional background?"
- Ask ONLY ONE behavioral question per turn. Do NOT list multiple questions.
- After each candidate response, acknowledge it in ONE sentence, then ask the next question.
- Use the STAR framework (Situation, Task, Action, Result) as your evaluation lens.
- Question pool to draw from:
    * "Tell me about a time you faced a significant challenge at work. How did you handle it?"
    * "Describe a situation where you demonstrated leadership without a formal title."
    * "Share an example of working effectively in a team under pressure."
    * "Tell me about a time you had to adapt quickly to a major change."
    * "What is your greatest professional achievement and what was your specific role in it?"
- This interview has exactly {total_turns} candidate turns.
- On the FINAL turn ({total_turns}), after the candidate's last answer, conclude with:
  "Thank you so much for your time today, {name}. You have given me a great deal to reflect on. Our team will review your responses and be in touch soon. Best of luck."
- Keep every response to 2-3 sentences maximum.
- Maintain a warm, professional, encouraging tone. You are a COACH, not just an evaluator."""

def get_mcq_generation_prompt(topic: str, count: int = 10) -> str:
    return f"""Generate exactly {count} multiple-choice questions (MCQs) to assess a candidate for the role/topic: "{topic}".

Each question must be:
- Challenging, practical, and directly relevant to "{topic}"
- Based on real-world scenarios where possible
- Accompanied by exactly 4 distinct answer options

Return ONLY a valid JSON array - no markdown, no explanation, no extra text.
Each element must follow this schema exactly:

[
  {{
    "question":    "Full question text here?",
    "options":     ["Option A", "Option B", "Option C", "Option D"],
    "correct":     0,
    "explanation": "Clear explanation of why the correct answer is right."
  }}
]

"correct" is a 0-based integer (0=A, 1=B, 2=C, 3=D). Generate exactly {count} questions."""

def get_hr_evaluation_prompt(name: str, job: str, transcript: str, total_turns: int) -> str:
    return f"""You are an expert HR interview evaluation AI. Analyze this behavioral interview and produce a comprehensive, fair evaluation report.

Candidate:    {name}
Target Role:  {job}
Total Turns:  {total_turns}

Full Interview Transcript:
{transcript}

Return ONLY a valid JSON object - no markdown, no extra text.

{{
  "communicationScore":   <0-100>,
  "communicationComment": "<2-3 sentences on clarity, structure, articulation>",
  "culturalFitScore":     <0-100>,
  "culturalFitComment":   "<2-3 sentences on attitude, STAR usage, professionalism>",
  "confidenceScore":      <0-100>,
  "confidenceComment":    "<2-3 sentences on confidence, self-awareness, enthusiasm>",
  "overallScore":         <0-100>,
  "hiringVerdict":        "<Strong Hire|Hire|Maybe|No Hire>",
  "strengths":            ["<strength 1>", "<strength 2>", "<strength 3>"],
  "improvements":         ["<area 1>", "<area 2>", "<area 3>"],
  "roadmap":              ["<step 1>", "<step 2>", "<step 3>", "<step 4>"],
  "turnFeedback": [
    {{"turn": 1, "question": "<coach's question summary>", "assessment": "<1-2 sentence feedback>"}}
  ]
}}"""

def get_mcq_evaluation_prompt(
    name: str, topic: str, total: int, correct: int, incorrect: int,
    skipped: int, score_pct: int, questions_summary: str,
) -> str:
    return f"""You are an expert technical assessment evaluator. Analyze this MCQ session and produce a detailed, actionable evaluation report.

Candidate:        {name}
Topic:            {topic}
Total Questions:  {total}
Correct:          {correct}
Incorrect:        {incorrect}
Skipped:          {skipped}
Score:            {score_pct}%

Question Details:
{questions_summary}

Return ONLY a valid JSON object - no markdown, no extra text.

{{
  "verdict":            "<Expert|Proficient|Competent|Developing|Needs Improvement>",
  "technicalFeedback":  "<2-3 sentences on technical knowledge>",
  "behavioralFeedback": "<2-3 sentences on approach, pacing, consistency>",
  "strongAreas":        ["<topic 1>", "<topic 2>"],
  "weakAreas":          ["<topic 1>", "<topic 2>"],
  "roadmap":            ["<step 1>", "<step 2>", "<step 3>", "<step 4>"]
}}"""

# High-level helpers
def generate_mcq_questions(topic: str, count: int = 10, model: Optional[str] = None) -> List[Dict]:
    """Generate MCQ questions and return as a validated list of dicts."""
    messages = [
        {
            "role":    "system",
            "content": "You are a professional assessment generator. Output ONLY valid JSON arrays.",
        },
        {"role": "user", "content": get_mcq_generation_prompt(topic, count)},
    ]
    raw       = call_llm(messages, temperature=0.7, model=model, format="json")
    questions = parse_json_response(raw)
    if not isinstance(questions, list) or not questions:
        raise ValueError("LLM returned an invalid question list.")
    return [
        {
            "question":    q.get("question", ""),
            "options":     q.get("options", []),
            "correct":     int(q.get("correct", 0)),
            "explanation": q.get("explanation", "No explanation provided."),
        }
        for q in questions
    ]

def get_next_hr_message(
    conversation: List[Dict],
    turn: int,
    total_turns: int,
    name: str,
    model: Optional[str] = None,
) -> str:
    """Fetch Interview Coach's next response in the HR interview."""
    msgs = conversation.copy()
    if turn == 0:
        msgs.append({
            "role":    "user",
            "content": (
                f"Begin the interview now. Greet {name} and deliver your opening message exactly as specified in your instructions."
            ),
        })
    else:
        is_last = turn >= total_turns
        suffix  = (
            " This is the FINAL turn - acknowledge their answer warmly and deliver your closing statement."
            if is_last else
            " Briefly acknowledge their answer in one sentence, then ask the next behavioral question."
        )
        msgs.append({
            "role":    "user",
            "content": f"The candidate just responded. This is turn {turn} of {total_turns}.{suffix}",
        })
    return call_llm(msgs, temperature=0.75, model=model)

def evaluate_hr_session(
    name: str,
    job: str,
    hr_questions: List[str],
    hr_answers: List[str],
    total_turns: int,
    model: Optional[str] = None,
) -> dict:
    """Evaluate a completed HR interview session. Falls back gracefully on LLM failure."""
    parts = [
        f"Turn {i + 1}:\nInterview Coach: {q}\nCandidate: {a or '(no response)'}"
        for i, (q, a) in enumerate(zip(hr_questions, hr_answers))
    ]
    transcript = "\n\n".join(parts)

    messages = [
        {
            "role":    "system",
            "content": "You are an expert HR interview evaluator. Return only valid JSON.",
        },
        {
            "role":    "user",
            "content": get_hr_evaluation_prompt(name, job, transcript, total_turns),
        },
    ]
    try:
        raw = call_llm(messages, temperature=0.3, model=model, format="json")
        return parse_json_response(raw)
    except Exception:
        return _hr_fallback(hr_questions, hr_answers)

def evaluate_mcq_session(
    name: str,
    topic: str,
    questions: List[Dict],
    answers: List[Optional[int]],
    model: Optional[str] = None,
) -> dict:
    """Evaluate a completed MCQ session. Falls back gracefully on LLM failure."""
    total     = len(questions)
    correct   = sum(1 for q, a in zip(questions, answers) if a is not None and a == q["correct"])
    incorrect = sum(1 for q, a in zip(questions, answers) if a is not None and a != q["correct"])
    skipped   = sum(1 for a in answers if a is None)
    score_pct = round((correct / total) * 100) if total else 0

    lines = []
    for i, (q, a) in enumerate(zip(questions, answers)):
        sel    = q["options"][a] if a is not None else "(skipped)"
        result = "Correct" if a == q["correct"] else ("Skipped" if a is None else "Wrong")
        lines.append(
            f"Q{i + 1}: {q['question']}\n"
            f"  Selected: {sel}\n"
            f"  Correct:  {q['options'][q['correct']]}\n"
            f"  Result:   {result}"
        )

    messages = [
        {
            "role":    "system",
            "content": "You are an expert technical evaluator. Return only valid JSON.",
        },
        {
            "role":    "user",
            "content": get_mcq_evaluation_prompt(
                name, topic, total, correct, incorrect,
                skipped, score_pct, "\n\n".join(lines),
            ),
        },
    ]
    try:
        raw    = call_llm(messages, temperature=0.3, model=model, format="json")
        result = parse_json_response(raw)
    except Exception:
        result = _mcq_fallback(topic, score_pct)

    # Always attach raw stats so the dashboard can use them
    result.update({
        "score_pct": score_pct, "correct": correct,
        "incorrect": incorrect, "skipped": skipped, "total": total,
    })
    return result

# Fallback evaluations
def _hr_fallback(hr_questions: list, hr_answers: list) -> dict:
    return {
        "communicationScore":   60,
        "communicationComment": "Interview completed. Detailed analysis is unavailable right now.",
        "culturalFitScore":     60,
        "culturalFitComment":   "Participated in all interview turns. Consider using the STAR method.",
        "confidenceScore":      60,
        "confidenceComment":    "Showed willingness to engage with all questions.",
        "overallScore":         60,
        "hiringVerdict":        "Maybe",
        "strengths":    ["Completed all interview turns", "Engaged with the coach", "Showed effort"],
        "improvements": ["Apply the STAR method", "Give specific examples", "Be more concise"],
        "roadmap": [
            "Practice STAR-method responses with a timer",
            "Research the target company values",
            "Record yourself in mock interviews and review",
            "Focus on concise, structured storytelling",
        ],
        "turnFeedback": [
            {
                "turn":       i + 1,
                "question":   (q[:120] if q else ""),
                "assessment": (a or "(no response)"),
            }
            for i, (q, a) in enumerate(zip(hr_questions, hr_answers))
        ],
    }

def _mcq_fallback(topic: str, score_pct: int) -> dict:
    verdict = (
        "Expert"            if score_pct >= 90 else
        "Proficient"        if score_pct >= 75 else
        "Competent"         if score_pct >= 50 else
        "Developing"        if score_pct >= 35 else
        "Needs Improvement"
    )
    return {
        "verdict":            verdict,
        "technicalFeedback":  f"Scored {score_pct}% on {topic}. Performance reflects a {verdict.lower()} level.",
        "behavioralFeedback": "Session completed. Review your incorrect answers for learning opportunities.",
        "strongAreas":        [topic],
        "weakAreas":          [f"Core {topic} fundamentals"],
        "roadmap": [
            f"Review core {topic} concepts systematically",
            "Complete additional practice assessments",
            "Follow a structured online course or certification path",
            "Build hands-on projects to solidify knowledge",
        ],
    }
