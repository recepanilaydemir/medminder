#!/bin/bash
# =============================================================================
# MedMinder — Deploy to Google Cloud Run
# =============================================================================
# Usage: ./deploy.sh
#
# This script builds the Docker image in Cloud Build and deploys it to
# Cloud Run. Run it after pushing changes to GitHub.
# =============================================================================

set -e

PROJECT="medminder-500400"
REGION="us-central1"
IMAGE="us-central1-docker.pkg.dev/${PROJECT}/medminder-repo/medminder:latest"
SERVICE="medminder"

echo "🔨 Building Docker image in Cloud Build..."
gcloud builds submit --tag "$IMAGE" --project="$PROJECT"

echo ""
echo "🚀 Deploying to Cloud Run..."
TOKEN=$(gcloud auth print-access-token)
curl -s -X PATCH \
  "https://run.googleapis.com/v2/projects/${PROJECT}/locations/${REGION}/services/${SERVICE}" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"template\": {
      \"containers\": [{
        \"image\": \"${IMAGE}\",
        \"ports\": [{\"containerPort\": 8000}],
        \"resources\": {\"limits\": {\"memory\": \"2Gi\", \"cpu\": \"2\"}},
        \"env\": [{\"name\": \"CORS_ORIGINS\", \"value\": \"*\"}],
        \"startupProbe\": {
          \"httpGet\": {\"path\": \"/api/health\", \"port\": 8000},
          \"initialDelaySeconds\": 3,
          \"periodSeconds\": 5,
          \"timeoutSeconds\": 5,
          \"failureThreshold\": 24
        }
      }],
      \"scaling\": {\"minInstanceCount\": 0, \"maxInstanceCount\": 3},
      \"timeout\": \"300s\",
      \"executionEnvironment\": \"EXECUTION_ENVIRONMENT_GEN2\"
    }
  }"

echo ""
echo "✅ Deployed! Visit: https://medminder-gm4j2lhxiq-uc.a.run.app"
