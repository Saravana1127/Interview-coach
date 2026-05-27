# AI Placement Portal

> AI-powered mock interview simulator — decoupled FastAPI backend + Vanilla JS frontend.

---

## Project Structure

```
/
├── backend/
│   ├── main.py          ← FastAPI app + all REST endpoints
│   ├── ai_engine.py     ← LLM prompt templates + HTTP client
│   └── requirements.txt
│
├── frontend/
│   ├── index.html       ← Clean HTML (no inline scripts/styles)
│   ├── styles.css       ← Full design system
│   ├── app.js           ← Main state machine + API calls
│   ├── webrtc.js        ← Camera, STT, TTS module
│   └── proctoring.js    ← Anti-malpractice detection module
│
├── .env                 ← LLM connection settings
└── README.md
```

---

## Prerequisites

| Requirement | Minimum |
|---|---|
| Python | 3.10+ |
| Ollama **or** Open WebUI | Running locally |
| A pulled LLM model | e.g. `ollama pull llama3` |

---

## 1 — Configure the Environment

Copy the example and edit `.env`:

```env
# .env
OPENWEBUI_API_URL=http://localhost:11434/v1/chat/completions
MODEL_NAME=llama3
OPENWEBUI_API_KEY=            # leave blank for Ollama; paste key for Open WebUI
BACKEND_PORT=8000
```

---

## 2 — Install Backend Dependencies

```powershell
# From the project root
cd backend
pip install -r requirements.txt
```

---

## 3 — Start the Backend

```powershell
# From the project root  (NOT from inside /backend)
uvicorn backend.main:app --reload --port 8000
```

The backend will:
- Serve the **frontend** at `http://localhost:8000/`
- Serve the **API** at `http://localhost:8000/api/...`
- Show interactive API docs at `http://localhost:8000/docs`

> **No separate frontend server needed** — FastAPI serves `frontend/` as static files.

---

## 4 — Open the App

Navigate to **`http://localhost:8000`** in your browser.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/health` | Health check |
| `POST` | `/api/chat` | Raw LLM proxy (HR turn-by-turn) |
| `POST` | `/api/mcq/generate` | Generate MCQ questions |
| `POST` | `/api/hr/evaluate` | Evaluate HR interview |
| `POST` | `/api/mcq/evaluate` | Evaluate MCQ session |
| `POST` | `/api/proctoring/flag` | Log a proctoring event |

Full schemas available at `/docs`.

---

## Changing the LLM Model at Runtime

Open the Settings gear in the top-right corner:

- **Backend API Base URL** — change if running the backend on a different port
- **Model Name** — override the model for the current session

---

## Developing Frontend Separately (Optional)

If you want to use VS Code Live Server or any static file server for hot-reload:

1. Serve `frontend/` from any port (e.g. 5500).
2. Open Settings in the app and set **Backend API Base URL** to `http://localhost:8000`.
3. CORS is already enabled on the backend for all origins.

---

## Features

| Feature | Mode |
|---|---|
| 1-on-1 HR behavioral interview with **Sarah** (AI HR Manager) | HR |
| Webcam live preview | HR |
| Voice input (STT) + voice output (TTS) | HR |
| AI-generated role-specific MCQs | MCQ |
| Countdown timer + per-question time tracking | MCQ |
| Tab-switch / paste / mouse-leave detection | Both |
| 100-point evaluation with tier badge | Both |
| Personalised learning roadmap | MCQ |
| Turn-by-turn feedback | HR |
| Printable / shareable reports | Both |
