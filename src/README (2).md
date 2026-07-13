# KundliGPT replica — AI Vedic astrologer, end to end

A working clone of the KundliGPT architecture. It does the thing that actually
makes KundliGPT good: it **computes the birth chart itself with Swiss Ephemeris**
and feeds the model dense, exact, structured chart data to reason over — instead
of renting pre-written horoscope blurbs from a third-party astrology API.

## What's new in this version

- **Google Maps place search.** Enter a Google Maps API key (Maps JavaScript +
  Places enabled) under *Keys & settings*, click *Enable place search*, then type
  a city in the birth-place field. Selecting a place auto-fills latitude and
  longitude.
- **Accurate historical timezone.** On place selection the app derives the UTC
  offset that actually applied on the birth date (base offset + DST) from the
  IANA tz database — more correct for old charts than a "current offset" lookup,
  and no Google Time Zone API needed. You can still override it manually.
- **In-app Claude API key.** Optional field under *Keys & settings*; used for that
  session. If `ANTHROPIC_API_KEY` is set on the server, the field can be left
  blank. (Keys live in the browser's localStorage — keep them server-side for
  production.)
- **Remembers the last 5 entries.** Recent birth-detail sets appear as clickable
  chips above the form (stored client-side). The server also keeps an LRU cache
  of the last 5 natal computations.

## The five steps (and where each lives)

| Step | What | File |
|------|------|------|
| 1 | **Swiss Ephemeris compute layer** — sidereal (Lahiri) planetary positions, ascendant, whole-sign houses, nakshatras, padas, dignities | `astro/ephemeris.py` |
| 2 | **Structured context serializer** — turns the chart into a dense block the LLM reasons over | `astro/chart.py` |
| 3 | **Chart-grounded interpretation prompt** — model interprets, never calculates | `prompts.py` |
| 4 | **Vimshottari Dasha timing engine** — Mahadasha/Antardasha with exact dates + current transits | `astro/dasha.py`, `astro/transits.py` |
| 5 | **Conversation memory + product layer** — sessions, pinned chart, free-question metering, chat, recent-entries cache, key handling | `app.py` |
| + | **Geocoding helper** — historical UTC offset from coordinates + birth date | `astro/geo.py` |

## Install &amp; run

Requires Python 3.10+.

```bash
cd kundli_app
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Then pick a model provider (the LLM is the only swappable part of the pipeline).

Option A — Claude (default):
```bash
export ANTHROPIC_API_KEY=sk-ant-...
uvicorn app:app --reload
```

Option B — Groq free tier (open-source models, no credit card):
```bash
export LLM_PROVIDER=groq
export GROQ_API_KEY=gsk_...            # from console.groq.com/keys
uvicorn app:app --reload
```

Open http://localhost:8000, enter birth details, generate the chart, and chat.
Windows PowerShell: `$env:LLM_PROVIDER="groq"; $env:GROQ_API_KEY="gsk_..."`.

## Switching the model

Pluggable three ways, in order of precedence:

1. Per session, from the UI — under *Keys &amp; settings* choose a provider
   (Claude / Groq), optionally a model, optionally a key. Active model shows
   under the chat box.
2. Per request — `POST /api/chart` accepts `provider`, `model`, `api_key`.
3. Server default — `LLM_PROVIDER=anthropic|groq`.

| Env var | Purpose | Default |
|---------|---------|---------|
| `LLM_PROVIDER` | default provider (`anthropic`/`groq`) | `anthropic` |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | Claude key / model | — / `claude-opus-4-8` |
| `GROQ_API_KEY` / `GROQ_MODEL` | Groq key / model | — / `llama-3.3-70b-versatile` |

Adding another OpenAI-compatible provider is ~6 lines: a new entry in
`PROVIDERS` in `llm.py` with its `base_url`, `env_key`, and `default_model`.

**Accuracy note:** the chart (positions, dasha, transits) is pure Python and is
identical regardless of provider — only interpretation quality depends on the
model. `llama-3.3-70b-versatile` is the strong free-tier pick;
`llama-3.1-8b-instant` is faster but weaker at synthesis and non-English output.

## Why this beats an AstrologyAPI.com + Claude build

- **Grounding, not paraphrase.** The model receives exact degrees, house lords,
  dasha dates and live transits — facts to reason over — rather than generic
  prose to reword. This is ~80% of the perceived quality gap.
- **Real timing.** The Vimshottari engine produces the "when does this period
  begin/end" answers users find uncanny. Most off-the-shelf API tiers don't
  expose this richly.
- **Division of labour.** The LLM never computes placements (where it makes
  mistakes); it's handed correct placements and asked only to interpret.

## Verified

The deterministic core is checked against references:
- Lahiri ayanamsa = 23.857° for 2000-01-01 (correct)
- Sun sidereal position for 2000-01-01 (correct, Sagittarius 16.5°)
- Gandhi's chart resolves to **Libra ascendant** (matches published charts)
- Vimshottari timeline spans exactly 120 years with the correct lord sequence

## Production notes / what to harden

- **Geocoding + historical timezone:** add a geocoder (Nominatim/Google) and
  `timezonefinder` + historical TZ data so users type a city instead of lat/long
  and offset. Pre-1947 India and DST edge cases shift the ascendant.
- **Persistence:** sessions are in-memory; move to Redis/Postgres.
- **Auth + billing:** wire real accounts and Razorpay/Stripe for the Pro tier.
- **More yogas / divisional charts:** D9 Navamsa, D10, classical yogas can be
  computed from the same raw positions and added to the context block.
- **Streaming:** switch `/api/chat` to SSE streaming for a snappier feel.
- **Model:** defaults to `claude-opus-4-8`; set `MODEL` in `app.py` to
  `claude-sonnet-4-6` to cut cost.

## Layout

```
kundli_app/
├── app.py                 # FastAPI: chart + chat endpoints, memory, metering
├── llm.py                 # pluggable provider layer (Claude / Groq)
├── prompts.py             # Step 3 interpretation prompt
├── requirements.txt
├── astro/
│   ├── ephemeris.py       # Step 1 Swiss Ephemeris compute
│   ├── chart.py           # Step 2 assemble + serialize
│   ├── dasha.py           # Step 4 Vimshottari timing
│   ├── transits.py        # Step 4 current transits
│   └── geo.py             # historical timezone from coordinates + date
└── static/
    └── index.html         # chat UI + North-Indian kundli chart
```
