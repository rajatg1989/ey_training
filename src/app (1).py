"""
KundliGPT-style backend — ties all five steps together.

  Step 1  astro/ephemeris.py   Swiss Ephemeris compute layer
  Step 2  astro/chart.py       structured context serializer
  Step 3  prompts.py           chart-grounded interpretation prompt
  Step 4  astro/dasha.py       Vimshottari timing engine
  Step 5  this file            conversation memory + product layer

Run:
  pip install -r requirements.txt
  export ANTHROPIC_API_KEY=sk-ant-...        # default provider
  # or use Groq's free tier instead:
  #   export LLM_PROVIDER=groq
  #   export GROQ_API_KEY=gsk-...
  uvicorn app:app --reload
Then open http://localhost:8000
"""
from __future__ import annotations

import os
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from astro.chart import build_full_chart, serialize_context
from prompts import build_system_prompt
from llm import complete, LLMError, list_providers, DEFAULT_PROVIDER

FREE_QUESTION_LIMIT = 3
MAX_HISTORY_TURNS = 20             # conversation memory window

app = FastAPI(title="KundliGPT replica")

# In-memory session store. Swap for Redis/Postgres in production.
# session_id -> {system, chart, history, questions_used, provider, model, api_key}
SESSIONS: dict[str, dict] = {}


# ---------- Schemas ----------

class BirthDetails(BaseModel):
    name: str = ""
    place: str = ""
    year: int
    month: int
    day: int
    hour: int
    minute: int
    lat: float
    lon: float
    tz_offset_hours: Optional[float] = None   # auto-derived if omitted
    api_key: Optional[str] = None             # optional per-session key
    provider: Optional[str] = None            # "anthropic" | "groq" (else server default)
    model: Optional[str] = None               # optional model override


class TimezoneRequest(BaseModel):
    lat: float
    lon: float
    year: int
    month: int
    day: int
    hour: int = 12
    minute: int = 0


class ChatRequest(BaseModel):
    session_id: str
    message: str
    language: str = "English"


# ---------- Endpoints ----------

@app.post("/api/timezone")
def derive_timezone(req: TimezoneRequest):
    """Resolve the historical UTC offset for coordinates + birth date.
    Called by the Google Places autocomplete flow to prefill the offset field."""
    from astro.geo import offset_for
    return offset_for(req.lat, req.lon, req.year, req.month, req.day,
                      req.hour, req.minute)


@app.get("/api/providers")
def providers():
    """Metadata for the UI model picker."""
    return {"default": DEFAULT_PROVIDER, "providers": list_providers()}


@app.post("/api/chart")
def create_chart(birth: BirthDetails):
    """Step 1+2+4: compute chart, build dasha, serialize context, open a session."""
    data = birth.model_dump()
    api_key = data.pop("api_key", None)
    provider = data.pop("provider", None)
    model = data.pop("model", None)

    # Auto-derive the timezone offset from coordinates + birth date if not given.
    if data.get("tz_offset_hours") is None:
        from astro.geo import offset_for
        derived = offset_for(data["lat"], data["lon"], data["year"], data["month"],
                             data["day"], data["hour"], data["minute"])
        data["tz_offset_hours"] = derived["offset_hours"]

    try:
        chart = build_full_chart(data)
    except Exception as e:
        raise HTTPException(400, f"Could not compute chart: {e}")

    context = serialize_context(chart)
    session_id = uuid.uuid4().hex
    SESSIONS[session_id] = {
        "system": build_system_prompt(context),
        "chart": chart,
        "history": [],
        "questions_used": 0,
        "api_key": api_key,
        "provider": provider,
        "model": model,
    }
    return {
        "session_id": session_id,
        "chart": chart,
        "tz_offset_used": data["tz_offset_hours"],
        "provider": provider or DEFAULT_PROVIDER,
        "free_questions_remaining": FREE_QUESTION_LIMIT,
    }


@app.post("/api/chat")
def chat(req: ChatRequest):
    """Step 3+5: chart-grounded interpretation with conversation memory + metering."""
    sess = SESSIONS.get(req.session_id)
    if not sess:
        raise HTTPException(404, "Session not found. Generate a chart first.")

    if sess["questions_used"] >= FREE_QUESTION_LIMIT:
        raise HTTPException(402, {
            "error": "free_limit_reached",
            "message": "You've used your 3 free questions. Upgrade to Pro for unlimited readings.",
        })

    user_msg = req.message.strip()
    if not user_msg:
        raise HTTPException(400, "Empty message")

    # conversation memory: keep last N turns, chart stays pinned in the system prompt
    history = sess["history"][-MAX_HISTORY_TURNS * 2:]
    messages = history + [{"role": "user", "content": user_msg}]

    system = sess["system"]
    if req.language and req.language.lower() != "english":
        system += f"\n\nIMPORTANT: Reply in {req.language}."

    try:
        answer = complete(
            system, messages, max_tokens=1200,
            provider=sess.get("provider"),
            model=sess.get("model"),
            api_key=sess.get("api_key"),
        )
    except LLMError as e:
        raise HTTPException(500, str(e))        # missing key / unknown provider
    except Exception as e:
        raise HTTPException(502, f"Model error: {e}")

    # persist turn (memory) and meter
    sess["history"].append({"role": "user", "content": user_msg})
    sess["history"].append({"role": "assistant", "content": answer})
    sess["questions_used"] += 1

    return {
        "answer": answer,
        "free_questions_remaining": max(0, FREE_QUESTION_LIMIT - sess["questions_used"]),
    }


@app.get("/api/chart/{session_id}")
def get_chart(session_id: str):
    sess = SESSIONS.get(session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    return sess["chart"]


# ---------- Static frontend ----------

@app.get("/")
def index():
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")
