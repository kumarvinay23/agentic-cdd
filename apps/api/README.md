# Agentic CDD API

FastAPI backend exposing `/api/v1` (DiligenceIQ-compatible contracts).

## Setup

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run

```bash
agetic-cdd-api
# or
uvicorn agetic_cdd_api.app:app --reload --port 4600
```

Health: [http://127.0.0.1:4600/api/v1/health](http://127.0.0.1:4600/api/v1/health)

## Auth (W1)

Seed admin (created on startup):

- Email: `admin@ageticcdd.com`
- Password: `adminpass`

Endpoints: `/api/v1/auth/register` · `/login` · `/refresh` · `/logout` · `/me`
