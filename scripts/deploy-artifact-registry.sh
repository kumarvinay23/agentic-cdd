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

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f .env.docker ]]; then
  # shellcheck disable=SC1091
  set -a
  source .env.docker
  set +a
fi

GCP_PROJECT_ID="${GCP_PROJECT_ID:?Set GCP_PROJECT_ID in .env.docker or the environment}"
GCP_REGION="${GCP_REGION:-us-central1}"
AR_REPOSITORY="${AR_REPOSITORY:-agetic-cdd}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://127.0.0.1:4600}"

REGISTRY_HOST="${GCP_REGION}-docker.pkg.dev"
API_REMOTE="${REGISTRY_HOST}/${GCP_PROJECT_ID}/${AR_REPOSITORY}/agetic-cdd-api:${IMAGE_TAG}"
WEB_REMOTE="${REGISTRY_HOST}/${GCP_PROJECT_ID}/${AR_REPOSITORY}/agetic-cdd-web:${IMAGE_TAG}"

MODE="local"
BUILD_API=1
BUILD_WEB=1

for arg in "$@"; do
  case "$arg" in
    --cloud) MODE="cloud" ;;
    --api-only) BUILD_WEB=0 ;;
    --web-only) BUILD_API=0 ;;
    -h|--help)
      sed -n '1,20p' "$0"
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

if [[ "$BUILD_API" -eq 1 ]]; then
  echo "Building API image → ${API_REMOTE}"
  docker build -f Dockerfile.api -t "${API_REMOTE}" -t "agetic-cdd-api:${IMAGE_TAG}" .
  echo "Pushing ${API_REMOTE}"
  docker push "${API_REMOTE}"
fi

if [[ "$BUILD_WEB" -eq 1 ]]; then
  echo "Building Web image → ${WEB_REMOTE}"
  docker build -f Dockerfile.web \
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
echo "Deploy pre-compiled containers locally:"
echo "  export API_IMAGE=${API_REMOTE}"
echo "  export WEB_IMAGE=${WEB_REMOTE}"
echo "  docker compose --env-file .env.docker pull"
echo "  docker compose --env-file .env.docker up -d"
