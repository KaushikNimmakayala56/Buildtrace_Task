#!/bin/bash

set -e

# Check required env vars, use defaults if not set
if [ -z "$PROJECT_ID" ]; then
    PROJECT_ID="buildtrace-challenge-476923"
    export PROJECT_ID
    echo "Using default PROJECT_ID: $PROJECT_ID"
fi

if [ -z "$BUCKET" ]; then
    BUCKET="gs://bt-challenge-buildtrace-challenge-476923"
    export BUCKET
    echo "Using default BUCKET: $BUCKET"
fi

if [ -z "$TOPIC_ID" ]; then
    TOPIC_ID="bt-jobs"
    export TOPIC_ID
    echo "Using default TOPIC_ID: $TOPIC_ID"
fi

SERVICE_NAME="buildtrace-worker"
REGION="us-central1"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "Building Docker image..."
gcloud builds submit --tag ${IMAGE_NAME} --project ${PROJECT_ID} --region=us-central1

echo "Deploying to Cloud Run..."
gcloud run deploy ${SERVICE_NAME} \
    --image ${IMAGE_NAME} \
    --region ${REGION} \
    --platform managed \
    --min-instances 0 \
    --max-instances 100 \
    --concurrency 10 \
    --memory 512Mi \
    --timeout 300s \
    --allow-unauthenticated \
    --set-env-vars PROJECT_ID=${PROJECT_ID},BUCKET=${BUCKET},TOPIC_ID=${TOPIC_ID} \
    --project ${PROJECT_ID}

SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region ${REGION} --project ${PROJECT_ID} --format 'value(status.url)')

echo ""
echo "Deployment complete!"
echo "Service URL: ${SERVICE_URL}"
echo ""
echo "To create Pub/Sub push subscription, run:"
echo "gcloud pubsub subscriptions create bt-jobs-sub --topic ${TOPIC_ID} --push-endpoint ${SERVICE_URL}/worker --project ${PROJECT_ID}"

