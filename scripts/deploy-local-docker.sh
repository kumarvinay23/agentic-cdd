#!/usr/bin/env bash
# Rebuild Agentic CDD images from the current working tree and redeploy locally.
#
# Docker layer cache is fine for unchanged deps; source COPY layers invalidate
# when apps/api/src or apps/web change. Use --no-cache to force a full rebuild.
#
# Usage:
#   cp .env.docker.example .env.docker   # once; set AGETIC_CDD_JWT_SECRET
#   ./scripts/deploy-local-docker.sh              # build + up + smoke test
#   ./scripts/deploy-local-docker.sh --api-only
#   ./scripts/deploy-local-docker.sh --web-only
#   ./scripts/deploy-local-docker.sh --no-cache
#   ./scripts/deploy-local-docker.sh --down        # stop stack only

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${ENV_FILE:-.env.docker}"
NO_CACHE=0
BUILD_API=1
BUILD_WEB=1
DOWN_ONLY=0
SKIP_VERIFY=0

for arg in "$@"; do
  case "$arg" in
    --no-cache) NO_CACHE=1 ;;
    --api-only) BUILD_WEB=0 ;;
    --web-only) BUILD_API=0 ;;
    --down) DOWN_ONLY=1 ;;
    --skip-verify) SKIP_VERIFY=1 ;;
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

if [[ ! -f "$ENV_FILE" ]]; then
  if [[ -f .env.docker.example ]]; then
    echo "Creating ${ENV_FILE} from .env.docker.example"
    cp .env.docker.example "$ENV_FILE"
  else
    echo "Missing ${ENV_FILE} (and no .env.docker.example)." >&2
    exit 1
  fi
fi

# Compose accepts unquoted values with spaces; bash `source` does not.
# Read only the keys this script needs.
env_get() {
  local key="$1" default="${2:-}" line value
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

API_PORT="$(env_get API_PORT 4600)"
WEB_PORT="$(env_get WEB_PORT 3000)"
IMAGE_TAG="$(env_get IMAGE_TAG latest)"
GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

COMPOSE=(docker compose --env-file "$ENV_FILE")

if [[ "$DOWN_ONLY" -eq 1 ]]; then
  echo "Stopping local stack..."
  "${COMPOSE[@]}" down
  exit 0
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon is not reachable. Start Docker Desktop and retry." >&2
  exit 1
fi

# Always target local image names so compose does not pull a stale AR image.
export API_IMAGE="agetic-cdd-api:${IMAGE_TAG}"
export WEB_IMAGE="agetic-cdd-web:${IMAGE_TAG}"
export GIT_SHA BUILD_TIME

BUILD_ARGS=(build)
[[ "$NO_CACHE" -eq 1 ]] && BUILD_ARGS+=(--no-cache)
BUILD_ARGS+=(--pull)
BUILD_ARGS+=(--build-arg "GIT_SHA=${GIT_SHA}")
BUILD_ARGS+=(--build-arg "BUILD_TIME=${BUILD_TIME}")

SERVICES=()
[[ "$BUILD_API" -eq 1 ]] && SERVICES+=(api)
[[ "$BUILD_WEB" -eq 1 ]] && SERVICES+=(web)

if [[ ${#SERVICES[@]} -eq 0 ]]; then
  echo "Nothing to build (both --api-only and --web-only?)." >&2
  exit 1
fi

echo "Rebuilding from working tree (git=${GIT_SHA} at ${BUILD_TIME})..."
echo "  Images: ${SERVICES[*]} → ${API_IMAGE} / ${WEB_IMAGE}"
"${COMPOSE[@]}" "${BUILD_ARGS[@]}" "${SERVICES[@]}"

echo "Recreating containers with freshly built images..."
UP_SERVICES=("${SERVICES[@]}")
# If only one service was rebuilt, still ensure its dependency is up.
if [[ "$BUILD_WEB" -eq 1 && "$BUILD_API" -eq 0 ]]; then
  UP_SERVICES=(api web)
fi
"${COMPOSE[@]}" up -d --force-recreate --remove-orphans "${UP_SERVICES[@]}"

wait_http() {
  local url="$1"
  local name="$2"
  local attempts="${3:-60}"
  local i=0
  echo -n "Waiting for ${name} (${url})"
  while (( i < attempts )); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo " OK"
      return 0
    fi
    echo -n "."
    sleep 2
    i=$((i + 1))
  done
  echo
  echo "${name} did not become ready in time." >&2
  "${COMPOSE[@]}" ps
  "${COMPOSE[@]}" logs --tail=80 "${SERVICES[@]}"
  return 1
}

if [[ "$SKIP_VERIFY" -eq 1 ]]; then
  echo "Skipped smoke tests (--skip-verify)."
  exit 0
fi

echo
echo "Smoke tests..."
if [[ "$BUILD_API" -eq 1 ]]; then
  wait_http "http://127.0.0.1:${API_PORT}/api/v1/health" "API"
  HEALTH="$(curl -fsS "http://127.0.0.1:${API_PORT}/api/v1/health")"
  echo "  health: ${HEALTH}"
  # Prove the image contains the current API package (not a stale layer).
  docker exec agetic-cdd-api python -c \
    "from agetic_cdd_api.report_builder_base import coerce_percent_points; \
     v=coerce_percent_points(0.872743, family='grr', unit='%'); \
     assert abs(v-87.2743)<1e-4, v; \
     print('  api code check: coerce_percent_points(grr)=', round(v, 2))"
fi

if [[ "$BUILD_WEB" -eq 1 ]]; then
  wait_http "http://127.0.0.1:${WEB_PORT}/login" "Web"
  WEB_CODE="$(curl -fsS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${WEB_PORT}/login")"
  echo "  web /login → HTTP ${WEB_CODE}"
fi

echo
echo "Local Docker deploy complete."
echo "  API:  http://127.0.0.1:${API_PORT}/api/v1/health"
echo "  Web:  http://127.0.0.1:${WEB_PORT}/login"
echo "  Stop: ./scripts/deploy-local-docker.sh --down"
