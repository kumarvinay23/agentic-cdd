# Agentic CDD

AI multi-agent Commercial Due Diligence platform.

**Brand:** Agentic CDD · **Layout target:** DiligenceIQ-identical · **Engine:** B3 full stack

## Monorepo (W0+)

```
apps/web   Next.js UI (port 3000)
apps/api   FastAPI /api/v1 (port 4600)
src/       Legacy Jinja portfolio prototype (deprecated after W2)
CONTEXT.md Product & system source of truth
```

## Quick start

### API

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn agetic_cdd_api.app:app --reload --port 4600
```

Health: http://127.0.0.1:4600/api/v1/health

### Web

```bash
cd apps/web
cp .env.example .env.local
npm install
npm run dev
```

Sign in chrome: http://127.0.0.1:3000/login  
Status: http://127.0.0.1:3000/status

### Legacy prototype (optional)

```bash
# from repo root
source .venv/bin/activate
pip install -e ".[dev]"
agetic-cdd --port 8010
```

## Delivery waves

See `CONTEXT.md` → **Locked product decisions** / **Delivery waves (B3 full product)**.  
W0 = scaffold + login chrome + health.  
W1 = auth (register/login/JWT) + org tenancy — **done**.  
W2 = portfolio dashboard + create dealroom — **done**.  
W3 = deal dashboard + VDR upload — **done**.

### Local login (W1)

| | |
|---|---|
| Email | `admin@ageticcdd.com` |
| Password | `adminpass` |

Or create an account at `/register`.
