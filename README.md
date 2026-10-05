# ColdCraft 

AI cold-email generator for job hunting: paste a job URL or drop a screenshot → AI extracts the job, researches the company, finds a recruiter address, writes the email → you review and send via Gmail → follow-ups are scheduled and tracked.

## Architecture

```
Electron / React (frontend/src/features/*)
        │  X-API-Token
        ▼
FastAPI  api/v1/endpoints/*  ──►  services/*   (WHAT: business rules, DB)
                                   │   │
                       domain/state_machine   ├──►  ai/*            (providers, fallback, validation, prompts)
                                              └──►  integrations/*  (HOW: gmail, hunter, web)
Celery worker + beat (optional)  ──►  services/*   (same code path as the API)
```

```
backend/app/
├── api/v1/endpoints/   applications · email · followups · profile · research · health
├── services/           application · research · email · followup · profile · application_pipeline (orchestration only)
├── integrations/       gmail · hunter · linkedin · web
├── ai/
│   ├── providers/      base · groq · gemini · openai
│   ├── client.py       ordered fallback, per-error retry, JSON repair
│   ├── schemas.py      Pydantic models every AI response must satisfy
│   └── composer · extractor · researcher · prompts
├── prompts/            <name>/vN.txt — versioned, recorded on every generated email
├── domain/             state_machine.py
├── core/               config · security · middleware · uploads · errors · database
└── tasks/              celery_app · jobs
backend/alembic/        migrations (0001 baseline, 0002 states + encrypted tokens)
backend/tests/          unit/ + integration/  (160 tests)
```

## Application lifecycle

`DRAFT → RESEARCHING → READY → SENT → FOLLOW_UP_DUE → FOLLOW_UP_SENT → REPLIED → INTERVIEW`
plus `REJECTED` / `WITHDRAWN`. Allowed transitions live in one table in `domain/state_machine.py`; anything else raises HTTP 409.

## Setup

```powershell
cp .env.example .env            # fill in keys (see comments inside)
cp frontend/.env.example frontend/.env

cd backend
python -m venv .venv ; .venv\Scripts\activate
pip install -r requirements-dev.txt
alembic upgrade head            # also runs automatically when the API starts
python seed.py                  # optional dev data
```

### Run
```powershell
# Terminal 1 — API (also runs the lightweight in-process follow-up scheduler)
cd backend ; uvicorn app.main:app --reload --port 8000
# Terminal 2 — frontend
cd frontend ; npm install ; npm run dev          # or: npm run electron:dev
```

### Optional: Celery worker + beat (needs Redis)
```powershell
# set INPROCESS_SCHEDULER=false in .env first so the two schedulers don't both run
celery -A app.tasks.celery_app worker --loglevel=info --pool=solo   # --pool=solo on Windows
celery -A app.tasks.celery_app beat   --loglevel=info
```
Tasks: research company · find recruiter · generate email · send email · send follow-up · check due follow-ups (every N min) · check Gmail replies (every 30 min).

### Tests
```powershell
cd backend ; pytest                # AI, Gmail, web and DB are all faked — no keys or network needed
cd frontend ; npx tsc --noEmit
```

## Migrations
```powershell
alembic revision --autogenerate -m "describe change"
alembic upgrade head
alembic downgrade -1
```
**Upgrading an existing v2.0 database:** just start the API (or run `alembic upgrade head`). Migration 0001 is a no-op for tables that already exist; 0002 renames statuses (`draft/researched → READY`, `sent → SENT`, `replied → REPLIED`, `closed → WITHDRAWN`, `failed → DRAFT`) and **encrypts your stored Gmail token**. Back up `coldcraft.db` first.

## Security notes
- `SECRET_KEY`, `API_TOKEN`, `TOKEN_ENCRYPTION_KEY` are **required** when `APP_ENV=production` (the app refuses to start without them). In dev, `SECRET_KEY` is random per run.
- Gmail OAuth tokens are Fernet-encrypted at rest. In dev the key is auto-generated into `backend/.coldcraft_fernet.key` (git-ignored) — that protects against casual DB leaks, not against someone with access to both files. For stronger protection, supply `TOKEN_ENCRYPTION_KEY` from the OS credential store.
- `API_TOKEN` is a shared secret sent as `X-API-Token`. In the web/Electron bundle it ships inside the JS, so treat it as protection against *other local processes/web pages*, not against someone inspecting the app.
- Rate limiting is in-memory per process; screenshots are validated by decoding them (type, size, pixel cap); job URLs resolving to private/loopback addresses are refused.
