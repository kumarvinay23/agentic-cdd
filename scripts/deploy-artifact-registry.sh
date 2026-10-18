#!/usr/bin/env bash
# Build Agentic CDD container images and push them to Google Artifact Registry.
#
# Prerequisites:
#   - Docker Desktop / Engine running
#   - gcloud CLI authenticated (`gcloud auth login`)
#   - APIs enabled: artifactregistry, cloudbuild (for cloud path)
#
# Usage:
#   cp .env.docker.example .env.docker   # fill GCP_PROJECT_ID, secrets
#   ./scripts/deploy-artifact-registry.sh              # local docker build + push
#   ./scripts/deploy-artifact-registry.sh --cloud       # Cloud Build remote build + push
#   ./scripts/deploy-artifact-registry.sh --api-only
#   ./scripts/deploy-artifact-registry.sh --web-only
#   ./scripts/deploy-artifact-registry.sh --no-cache   # ignore Docker layer cache
#
# For local-only rebuild/redeploy (no GCP), use:
#   ./scripts/deploy-local-docker.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${ENV_FILE:-.env.docker}"

# Compose accepts unquoted values with spaces; bash `source` does not.
env_get() {
  local key="$1" default="${2:-}" line value
  if [[ ! -f "$ENV_FILE" ]]; then
    printf '%s' "$default"
    return
  fi
  line="$(grep -E "^[[:space:]]*${key}=" "$ENV_FILE" | tail -n 1 || true)"
  if [[ -z "$line" ]]; then
    printf '%s' "$default"
    return
  fi
  value="${line#*=}"
  value="${value%$'\r'}"
  if [[ "$value" == \"*\" && "$value" == *\" ]]; then
    value="${value:1:${#value}-2}"
  elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
    value="${value:1:${#value}-2}"
  fi
  printf '%s' "$value"
}

# Prefer already-exported env; otherwise read from .env.docker
: "${GCP_PROJECT_ID:=$(env_get GCP_PROJECT_ID)}"
: "${GCP_REGION:=$(env_get GCP_REGION us-central1)}"
: "${AR_REPOSITORY:=$(env_get AR_REPOSITORY agetic-cdd)}"
: "${IMAGE_TAG:=$(env_get IMAGE_TAG latest)}"
: "${NEXT_PUBLIC_API_URL:=$(env_get NEXT_PUBLIC_API_URL http://127.0.0.1:4600)}"

GCP_PROJECT_ID="${GCP_PROJECT_ID:?Set GCP_PROJECT_ID in .env.docker or the environment}"
GCP_REGION="${GCP_REGION:-us-central1}"
AR_REPOSITORY="${AR_REPOSITORY:-agetic-cdd}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://127.0.0.1:4600}"
GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

REGISTRY_HOST="${GCP_REGION}-docker.pkg.dev"
API_REMOTE="${REGISTRY_HOST}/${GCP_PROJECT_ID}/${AR_REPOSITORY}/agetic-cdd-api:${IMAGE_TAG}"
WEB_REMOTE="${REGISTRY_HOST}/${GCP_PROJECT_ID}/${AR_REPOSITORY}/agetic-cdd-web:${IMAGE_TAG}"

MODE="local"
BUILD_API=1
BUILD_WEB=1
NO_CACHE=0

for arg in "$@"; do
  case "$arg" in
    --cloud) MODE="cloud" ;;
    --api-only) BUILD_WEB=0 ;;
    --web-only) BUILD_API=0 ;;
    --no-cache) NO_CACHE=1 ;;
    -h|--help)
      sed -n '1,22p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 1
      ;;
  esac
done

ensure_repo() {
  if ! gcloud artifacts repositories describe "${AR_REPOSITORY}" \
      --location="${GCP_REGION}" \
      --project="${GCP_PROJECT_ID}" >/dev/null 2>&1; then
    echo "Creating Artifact Registry repository '${AR_REPOSITORY}' in ${GCP_REGION}..."
    gcloud artifacts repositories create "${AR_REPOSITORY}" \
      --repository-format=docker \
      --location="${GCP_REGION}" \
      --project="${GCP_PROJECT_ID}" \
      --description="Agentic CDD container images"
  fi
}

configure_docker_auth() {
  gcloud auth configure-docker "${REGISTRY_HOST}" --quiet
}

if [[ "$MODE" == "cloud" ]]; then
  ensure_repo
  echo "Submitting Cloud Build (remote build + push to Artifact Registry)..."
  SUBST="_REGION=${GCP_REGION},_AR_REPOSITORY=${AR_REPOSITORY},_TAG=${IMAGE_TAG},_NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}"
  gcloud builds submit \
    --project="${GCP_PROJECT_ID}" \
    --config=cloudbuild.yaml \
    --substitutions="${SUBST}" \
    .
  echo "Done."
  echo "  API: ${API_REMOTE}"
  echo "  Web: ${WEB_REMOTE}"
  exit 0
fi

ensure_repo
configure_docker_auth

DOCKER_BUILD_FLAGS=()
[[ "$NO_CACHE" -eq 1 ]] && DOCKER_BUILD_FLAGS+=(--no-cache)
DOCKER_BUILD_FLAGS+=(--pull)
DOCKER_BUILD_FLAGS+=(--build-arg "GIT_SHA=${GIT_SHA}")
DOCKER_BUILD_FLAGS+=(--build-arg "BUILD_TIME=${BUILD_TIME}")

echo "Building from working tree (git=${GIT_SHA} at ${BUILD_TIME})..."

if [[ "$BUILD_API" -eq 1 ]]; then
  echo "Building API image → ${API_REMOTE}"
  docker build -f Dockerfile.api \
    "${DOCKER_BUILD_FLAGS[@]}" \
    -t "${API_REMOTE}" -t "agetic-cdd-api:${IMAGE_TAG}" .
  echo "Pushing ${API_REMOTE}"
  docker push "${API_REMOTE}"
fi

if [[ "$BUILD_WEB" -eq 1 ]]; then
  echo "Building Web image → ${WEB_REMOTE}"
  docker build -f Dockerfile.web \
    "${DOCKER_BUILD_FLAGS[@]}" \
    --build-arg "NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}" \
    -t "${WEB_REMOTE}" -t "agetic-cdd-web:${IMAGE_TAG}" .
  echo "Pushing ${WEB_REMOTE}"
  docker push "${WEB_REMOTE}"
fi

echo
echo "Images in Artifact Registry:"
[[ "$BUILD_API" -eq 1 ]] && echo "  ${API_REMOTE}"
[[ "$BUILD_WEB" -eq 1 ]] && echo "  ${WEB_REMOTE}"
echo
echo "Deploy locally from this rebuild (recommended):"
echo "  ./scripts/deploy-local-docker.sh"
echo
echo "Or pull the AR tags into compose:"
echo "  export API_IMAGE=${API_REMOTE}"
echo "  export WEB_IMAGE=${WEB_REMOTE}"
echo "  docker compose --env-file .env.docker pull"
echo "  docker compose --env-file .env.docker up -d --force-recreate"
