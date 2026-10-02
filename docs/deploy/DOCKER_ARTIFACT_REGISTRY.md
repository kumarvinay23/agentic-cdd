# Docker & Artifact Registry deploy

Agentic CDD ships as two container images:

| Image | Dockerfile | Port | Role |
|-------|------------|------|------|
| `agetic-cdd-api` | `Dockerfile.api` | `4600` | FastAPI `/api/v1` |
| `agetic-cdd-web` | `Dockerfile.web` | `3000` | Next.js UI |

Pinned Python deps live in [`apps/api/requirements.txt`](../../apps/api/requirements.txt) (exported from `uv.lock`).

For the full Google Cloud topology (Cloud Run vs GCE, storage, secrets, CI/CD), see **[GCP_ARCHITECTURE.md](./GCP_ARCHITECTURE.md)**.

---

## 1. Deploy a pre-compiled Docker container

### A. Build once (or pull from Artifact Registry)

```bash
# From repo root
cp .env.docker.example .env.docker
# Edit .env.docker — set AGETIC_CDD_JWT_SECRET (and GCP_* if pushing)

# Build local images
docker compose --env-file .env.docker build

# Or pull already-published images from Artifact Registry
# (set API_IMAGE / WEB_IMAGE in .env.docker to the full AR paths first)
docker compose --env-file .env.docker pull
```

### B. Run the pre-built stack

```bash
docker compose --env-file .env.docker up -d
```

Check:

- API health: http://127.0.0.1:4600/api/v1/health  
- Web UI: http://127.0.0.1:3000/login  

Default seed admin (override in `.env.docker`): `admin@ageticcdd.com` / `adminpass`

Stop:

```bash
docker compose --env-file .env.docker down
```

Deal / VDR files persist in the named volume `agetic_cdd_deals`.

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
