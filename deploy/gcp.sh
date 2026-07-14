#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-jisong-cloud-492111}"
REGION="${REGION:-asia-northeast1}"
SERVICE="${SERVICE:-rihp-rag}"
REPOSITORY="${REPOSITORY:-rihp-rag}"
RUNTIME_SA_NAME="${RUNTIME_SA_NAME:-rihp-rag-runtime}"
IMAGE_TAG="${IMAGE_TAG:-$(date -u +%Y%m%d-%H%M%S)}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/web:${IMAGE_TAG}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACTION="${1:-all}"

runtime_sa="${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

infra() {
  gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    aiplatform.googleapis.com \
    --project "$PROJECT_ID"

  if ! gcloud iam service-accounts describe "$runtime_sa" --project "$PROJECT_ID" >/dev/null 2>&1; then
    gcloud iam service-accounts create "$RUNTIME_SA_NAME" \
      --project "$PROJECT_ID" --display-name "RIHP Policy Finder Cloud Run"
  fi
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${runtime_sa}" --role="roles/aiplatform.user" --quiet >/dev/null
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${runtime_sa}" --role="roles/serviceusage.serviceUsageConsumer" --quiet >/dev/null

  if ! gcloud artifacts repositories describe "$REPOSITORY" \
    --project "$PROJECT_ID" --location "$REGION" >/dev/null 2>&1; then
    gcloud artifacts repositories create "$REPOSITORY" \
      --project "$PROJECT_ID" --location "$REGION" --repository-format docker \
      --description "RIHP Policy Finder containers"
  fi
}

build() {
  python3 "$ROOT/scripts/build_site.py"
  python3 "$ROOT/scripts/build_exports.py"
  python3 "$ROOT/scripts/build_haystack_documents.py"
  gcloud builds submit "$ROOT" --project "$PROJECT_ID" --region "$REGION" --tag "$IMAGE"
}

deploy_service() {
  gcloud run deploy "$SERVICE" --project "$PROJECT_ID" --region "$REGION" \
    --image "$IMAGE" --service-account "$runtime_sa" --allow-unauthenticated \
    --cpu 1 --memory 1Gi --concurrency 20 --timeout 180s \
    --min 0 --max 2 --min-instances 0 --max-instances 2 \
    --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},RAG_GENERATION_ENABLED=true,RAG_MAX_TOKENS=700,RAG_RATE_LIMIT=12,RAG_RATE_WINDOW_SECONDS=600,VERTEX_EMBEDDING_LOCATION=us-central1,VERTEX_EMBEDDING_MODEL=text-multilingual-embedding-002,VERTEX_EMBEDDING_DIMENSIONS=256"
}

case "$ACTION" in
  infra) infra ;;
  build) build ;;
  service) deploy_service ;;
  all) infra; build; deploy_service ;;
  *) echo "사용법: $0 {infra|build|service|all}" >&2; exit 2 ;;
esac

printf 'PROJECT=%s\nREGION=%s\nSERVICE=%s\nIMAGE=%s\n' "$PROJECT_ID" "$REGION" "$SERVICE" "$IMAGE"
