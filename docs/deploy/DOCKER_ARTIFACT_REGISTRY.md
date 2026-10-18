# Docker & Artifact Registry deploy

Agentic CDD ships as two container images:

| Image | Dockerfile | Port | Role |
|-------|------------|------|------|
| `agetic-cdd-api` | `Dockerfile.api` | `4600` | FastAPI `/api/v1` |
| `agetic-cdd-web` | `Dockerfile.web` | `3000` | Next.js UI |

Pinned Python deps live in [`apps/api/requirements.txt`](../../apps/api/requirements.txt) (exported from `uv.lock`).

For the full Google Cloud topology (Cloud Run vs GCE, storage, secrets, CI/CD), see **[GCP_ARCHITECTURE.md](./GCP_ARCHITECTURE.md)**.

---

## 1. Local Docker — rebuild from current code and redeploy

After code changes, prefer the helper script. It rebuilds images from the
working tree, force-recreates containers, and runs smoke tests:

```bash
# From repo root (once)
cp .env.docker.example .env.docker
# Edit .env.docker — set AGETIC_CDD_JWT_SECRET (and WEB_PORT if 3000 is busy)

chmod +x scripts/deploy-local-docker.sh
./scripts/deploy-local-docker.sh              # api + web
./scripts/deploy-local-docker.sh --api-only   # faster when only Python changed
./scripts/deploy-local-docker.sh --no-cache   # ignore Docker layer cache
./scripts/deploy-local-docker.sh --down       # stop
```

Check:

- API health: http://127.0.0.1:4600/api/v1/health  
- Web UI: http://127.0.0.1:3002/login (or `WEB_PORT` from `.env.docker`)

Default seed admin (override in `.env.docker`): `admin@ageticcdd.com` / `adminpass`

Deal / VDR files persist in the named volume `agetic_cdd_deals`.

### Manual compose (equivalent)

```bash
docker compose --env-file .env.docker up -d --build --force-recreate
```

### Pull pre-built images from Artifact Registry

```bash
# Set API_IMAGE / WEB_IMAGE in .env.docker to the full AR paths first
docker compose --env-file .env.docker pull
docker compose --env-file .env.docker up -d --force-recreate
```

### Run a single pre-compiled API container

```bash
docker run --rm -p 4600:4600 \
  -e AGETIC_CDD_JWT_SECRET='change-me-long-secret' \
  -e AGETIC_CDD_APP_ENV=production \
  -e AGETIC_CDD_HOST=0.0.0.0 \
  -v agetic_cdd_deals:/data/deals \
  agetic-cdd-api:latest
```

---

## 2. Build and deploy images to Google Artifact Registry

### One-time GCP setup

```bash
export GCP_PROJECT_ID=your-gcp-project-id
export GCP_REGION=us-central1

gcloud config set project "$GCP_PROJECT_ID"
gcloud services enable \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com

# Create the Docker repository (also auto-created by the deploy script)
gcloud artifacts repositories create agetic-cdd \
  --repository-format=docker \
  --location="$GCP_REGION" \
  --description="Agentic CDD container images"

gcloud auth configure-docker "${GCP_REGION}-docker.pkg.dev"
```

### Option A — Local Docker build + push

```bash
cp .env.docker.example .env.docker
# Set GCP_PROJECT_ID, IMAGE_TAG, NEXT_PUBLIC_API_URL, secrets

chmod +x scripts/deploy-artifact-registry.sh
./scripts/deploy-artifact-registry.sh
```

Images land at:

```text
${REGION}-docker.pkg.dev/${PROJECT}/agetic-cdd/agetic-cdd-api:${TAG}
${REGION}-docker.pkg.dev/${PROJECT}/agetic-cdd/agetic-cdd-web:${TAG}
```

### Option B — Cloud Build (remote compile + push)

```bash
./scripts/deploy-artifact-registry.sh --cloud
```

Or directly:

```bash
gcloud builds submit --config=cloudbuild.yaml \
  --substitutions=_REGION=us-central1,_AR_REPOSITORY=agetic-cdd,_TAG=latest,_NEXT_PUBLIC_API_URL=https://api.example.com \
  .
```

### Pull & run the Artifact Registry images locally

```bash
# In .env.docker:
# API_IMAGE=us-central1-docker.pkg.dev/PROJECT/agetic-cdd/agetic-cdd-api:latest
# WEB_IMAGE=us-central1-docker.pkg.dev/PROJECT/agetic-cdd/agetic-cdd-web:latest

gcloud auth configure-docker us-central1-docker.pkg.dev
docker compose --env-file .env.docker pull
docker compose --env-file .env.docker up -d
```

---

## Regenerating `requirements.txt`

Whenever API dependencies change in `apps/api/pyproject.toml` / `uv.lock`:

```bash
cd apps/api
uv export --no-dev --no-emit-project --no-hashes --format requirements-txt > requirements.txt
```

---

## Notes

- **Secrets:** never bake `.env` / Gemini keys into the image; pass them at runtime via Compose / Cloud Run / GKE secrets.
- **Web API URL:** `NEXT_PUBLIC_API_URL` is a *build-time* Next.js public var — rebuild the web image when the public API hostname changes.
- **Production CORS:** set `AGETIC_CDD_CORS_ORIGINS` to your real HTTPS UI origin(s) when `AGETIC_CDD_APP_ENV=production`.
