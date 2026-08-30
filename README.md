# SpeakSense

An AI communication coach that helps students who struggle with public speaking
and social anxiety practice, get objective feedback, and track improvement over
time — combining speech analysis, body-language analysis, wearable stress data,
and AI-generated coaching into one loop: **Record → Analyze → Understand →
Practice → Improve.**

---

## Table of contents

- [What it does](#what-it-does)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Local development](#local-development)
- [Environment variables](#environment-variables)
- [API overview](#api-overview)
- [Deploying to Render](#deploying-to-render)
- [Wearable integration (Android bridge)](#wearable-integration-android-bridge)
- [n8n recap workflow](#n8n-recap-workflow)
- [Known limitations](#known-limitations)

---

## What it does

A user picks a scenario (mock interview, presentation, impromptu speech, or
self-introduction), records themselves answering a prompt, and SpeakSense
scores the attempt across several dimensions instead of a single black-box
"confidence" number:

- **Speech analysis** — word-level transcription (Whisper), then pacing (words
  per minute), pause length/frequency, filler-word rate, repetition, and
  vocabulary variety (type-token ratio).
- **Vocabulary coaching** — alternative word suggestions pulled from Datamuse,
  with Wolfram Alpha as a secondary source.
- **Video / body-language analysis** — eye contact, posture, gesture, and head
  movement, via OpenCV + MediaPipe face/pose landmarks.
- **Nervousness detection** — a locally trained scikit-learn model that scores
  nervousness from acoustic features extracted with `librosa`.
- **Wearable-aware coaching** — optional heart-rate context from a synced
  fitness band (see [the Android bridge](#wearable-integration-android-bridge)),
  used to tell a genuine stress spike apart from a motion artifact.
- **AI coaching feedback** — Gemini synthesizes all of the above into a
  written recap and a confidence score for the session.
- **Progress tracking** — a dashboard chart of words-per-minute, filler rate,
  and confidence score across sessions over time.
- **Daily practice challenges** — short, targeted drills based on what tripped
  the user up last time.
- **Semantic session search** — an Actian VectorAI vector store embeds each
  session's transcript (via `sentence-transformers`) so coaching can reference
  similar past attempts.

## Architecture

```
                         ┌─────────────────────┐
                         │  Next.js frontend    │
                         │  (record/dashboard/  │
                         │   practice pages)     │
                         └──────────┬───────────┘
                                    │ REST (JSON)
                                    ▼
                         ┌─────────────────────┐        ┌───────────────────┐
                         │  FastAPI backend     │◄──────►│  Postgres (Render/ │
                         │  (sessions, speech,  │        │  Supabase)         │
                         │  video, coaching,    │        └───────────────────┘
                         │  vocabulary,         │
                         │  wearables routers)   │        ┌───────────────────┐
                         └──┬────────┬────────┬─┘◄──────►│  Actian VectorAI   │
                            │        │        │           │  (semantic search) │
                            │        │        │           └───────────────────┘
              ┌─────────────┘        │        └─────────────┐
              ▼                      ▼                       ▼
     ┌─────────────────┐   ┌──────────────────┐   ┌────────────────────┐
     │ Gemini API        │   │ Whisper (local)   │   │ Supabase Storage    │
     │ (coaching recap)  │   │ + MediaPipe/OpenCV │   │ (session media)     │
     └─────────────────┘   │ (speech/video)     │   └────────────────────┘
                            └──────────────────┘

     ┌────────────────────┐        ┌─────────────────────┐
     │ Android Watch Bridge│──────► │ n8n (recap webhook)  │
     │ (Health Connect →   │  POST  │ → Slack/Email/Sheets │
     │  /api/wearables)     │        └─────────────────────┘
     └────────────────────┘
```

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14, React 18, TypeScript, Tailwind CSS, Recharts |
| Backend | FastAPI, SQLAlchemy, Pydantic, Uvicorn |
| Database | PostgreSQL |
| Vector store | Actian VectorAI (Docker), `sentence-transformers` embeddings |
| Speech | OpenAI Whisper (local), `librosa` for acoustic features |
| Vision | OpenCV (`opencv-python-headless`), MediaPipe |
| ML | scikit-learn (nervousness model, trained offline) |
| AI coaching | Google Gemini API |
| Vocabulary | Datamuse API, Wolfram Alpha API |
| Storage | Supabase Storage |
| Automation | n8n (webhook-triggered recap notifications) |
| Mobile bridge | Kotlin / Android, Health Connect, WorkManager |
| Infra | Docker Compose (local), Render (deploy) |

## Project structure

```
speak_sense/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, CORS, router wiring
│   │   ├── database.py          # SQLAlchemy engine/session
│   │   ├── models/               # User, SpeakingSession, SpeechMetrics,
│   │   │                          # VideoMetrics, WearableReading,
│   │   │                          # CoachingFeedback, WearableConnection,
│   │   │                          # DailyChallenge
│   │   ├── routers/              # sessions, speech, video, coaching,
│   │   │                          # vocabulary, wearables
│   │   ├── services/              # speech_analysis, video_analysis,
│   │   │                          # nervousness_detector, coaching_engine,
│   │   │                          # vocabulary_wolfram, wearable_adapter,
│   │   │                          # n8n_notify
│   │   ├── ml/                    # nervousness_model.pkl + training script
│   │   └── seed_demo_user.py     # creates the demo user the frontend expects
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── app/                      # page.tsx (home), record/, dashboard/, practice/
│   ├── components/speaksense/    # nav-bar, waveform, wearable-status
│   ├── components/ui/            # shared UI primitives
│   └── lib/                      # api.ts (fetch helper), constants.ts
├── android-bridge/               # Kotlin app: Health Connect → backend
├── n8n/                          # starter workflow JSON + setup guide
├── docker-compose.yml            # local Postgres + Actian VectorAI
└── render.yaml                   # Render Blueprint (db + backend + vectorai + frontend)
```

## Local development

**Prerequisites:** Docker, Python 3.11+, Node 18+.

1. **Start the datastores:**
   ```bash
   docker compose up -d
   ```
   This brings up Postgres on `localhost:5432` and Actian VectorAI on
   `localhost:6573` (REST), `6574` (gRPC — this is what the backend actually
   talks to), and `6575` (local dashboard).

2. **Backend:**
   ```bash
   cd backend
   cp .env.example .env      # fill in GEMINI_API_KEY, SUPABASE_*, etc.
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```
   Tables are created automatically on boot (`Base.metadata.create_all`).
   Seed the demo user once:
   ```bash
   python -m app.seed_demo_user
   ```
   API docs are then available at `http://localhost:8000/docs`.

3. **Frontend:**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
   Runs at `http://localhost:3000`, talking to the backend at
   `NEXT_PUBLIC_API_BASE_URL` (defaults to `http://localhost:8000`).

## Environment variables

All backend variables live in `backend/.env` locally (see `.env.example`) and
as Environment Variables on the Render service in production.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string |
| `ENVIRONMENT` | `development` / `production` |
| `SECRET_KEY` | App secret (auth/session signing) |
| `ALLOWED_ORIGINS` | Comma-separated CORS allow-list (frontend URL) |
| `GEMINI_API_KEY` | Google Gemini API key — powers coaching feedback |
| `WHISPER_MODEL` | Local Whisper model size (default `base`) |
| `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` / `SUPABASE_BUCKET` | Session media storage |
| `WOLFRAM_APP_ID` | Wolfram Alpha App ID (vocabulary secondary source) |
| `N8N_WEBHOOK_URL` | n8n webhook for post-coaching recap notifications (optional) |
| `ACTIAN_VECTORAI_URL` | Host:port of the Actian VectorAI gRPC endpoint |
| `ACTIAN_VECTORAI_COLLECTION` | Collection name for session embeddings |
| `EMBEDDING_MODEL` | `sentence-transformers` model used to embed transcripts |
| `NOISEFIT_API_BASE` / `HEALTH_CONNECT_ENABLED` | Wearable adapter config |

The frontend needs one: `NEXT_PUBLIC_API_BASE_URL`, pointing at the backend.

## API overview

All routes are prefixed `/api`.

| Router | Endpoints |
|---|---|
| `sessions` | `POST /sessions`, `GET /sessions/{id}`, `GET /sessions/{id}/full`, `GET /sessions/user/{user_id}`, `GET /sessions/user/{user_id}/progress` |
| `speech` | `POST /speech/{session_id}/analyze` |
| `video` | `POST /video/{session_id}/analyze`, `GET /video/{session_id}` |
| `coaching` | `POST /coaching/generate`, `GET /coaching/{session_id}` |
| `vocabulary` | `POST /vocabulary/suggest` |
| `wearables` | `POST /wearables/ingest`, `GET /wearables/user/{user_id}/status`, `POST /wearables/user/{user_id}/disconnect`, `GET /wearables/user/{user_id}/baseline-hr`, `GET /wearables/session/{session_id}/stress-index`, `POST /wearables/session/{session_id}/claim` |
| — | `GET /health` — liveness check |

Full interactive docs: `<backend-url>/docs`.

## Deploying to Render

`render.yaml` defines the whole stack as a Blueprint: `speaksense-db`
(Postgres), `speaksense-backend` (FastAPI), `speaksense-vectorai` (Actian
VectorAI as a private Docker service), and `speaksense-frontend` (Next.js) —
all on the Free plan by default.

**Fastest path (may prompt for a card):** Render dashboard → **New +** →
**Blueprint** → connect this repo → confirm all four resources show "Free" →
fill in the `sync: false` secrets (`GEMINI_API_KEY`, `WOLFRAM_APP_ID`,
`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `N8N_WEBHOOK_URL`) → Apply.

**Card-free path:** create each resource individually instead of via
Blueprint (New + → PostgreSQL, New + → Web Service ×2, New + → Private
Service), copying the settings out of `render.yaml` by hand and wiring the
cross-service URLs (`DATABASE_URL`, `ALLOWED_ORIGINS`,
`NEXT_PUBLIC_API_BASE_URL`, `ACTIAN_VECTORAI_URL`) into each service's
Environment tab yourself. If free Postgres still asks for a card, a free
Supabase Postgres instance works as a drop-in `DATABASE_URL` replacement.

After first deploy, seed the demo user via the backend's Shell tab:
```bash
python -m app.seed_demo_user
```

**Free-tier caveats:** free web services spin down after 15 minutes idle
(~1 minute cold start on next request); free Postgres auto-expires 30 days
after creation; the vector index has no persistent disk on the free plan, so
it resets on every backend redeploy; and 512MB RAM is tight for Whisper +
MediaPipe running in the same process — watch the backend logs for `Killed`
under load, and drop `WHISPER_MODEL` to `tiny` if it happens.

## Wearable integration (Android bridge)

Consumer bands like NoiseFit don't expose a public API, but their apps sync
into **Google Health Connect** on the phone. `android-bridge/` is a small
Kotlin app that reads heart-rate and step data from Health Connect and
forwards it to `POST /api/wearables/ingest`, tagged with a timestamp but no
session — the backend's `POST /wearables/session/{id}/claim` sweeps up
matching readings once a recording finishes. See `android-bridge/README.md`
for full setup.

## n8n recap workflow

After coaching feedback is generated, the backend POSTs a summary payload to
`N8N_WEBHOOK_URL` (see `backend/app/services/n8n_notify.py`) — n8n owns
whatever happens after that (Slack message, email, spreadsheet row). Import
`n8n/speaksense-recap-workflow.json` into a running n8n instance to get
started; full instructions in `n8n/README.md`. If the webhook is unreachable,
the backend logs a warning and continues — an n8n outage never breaks session
analysis.

## Known limitations

- No real authentication yet — the app operates against a single seeded demo
  user (`00000000-0000-0000-0000-000000000001`), matched across the frontend,
  backend, and Android bridge.
- The nervousness model is pre-trained and shipped as a `.pkl`; retraining
  requires running `backend/app/ml/train_nervousness_model.py` against your
  own labeled data.
- `motion_index` from the Android bridge is a coarse steps-per-minute proxy,
  not raw accelerometer data — treat it as a heuristic.
- Free-tier hosting trades away persistence (vector index) and uptime
  (cold starts, 30-day DB expiry) — fine for a demo, not for production.
