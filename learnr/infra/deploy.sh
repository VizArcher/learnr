#!/bin/bash
set -e

# Prompt for Project ID if not set
if [ -z "$GOOGLE_CLOUD_PROJECT" ]; then
    echo "GOOGLE_CLOUD_PROJECT environment variable is not set."
    echo "Checking gcloud config for default project..."
    GOOGLE_CLOUD_PROJECT=$(gcloud config get-value project)
    if [ -z "$GOOGLE_CLOUD_PROJECT" ]; then
        echo "Error: Could not determine Google Cloud Project. Please set GOOGLE_CLOUD_PROJECT."
        exit 1
    fi
fi

echo "Using Project: $GOOGLE_CLOUD_PROJECT"

echo "1. Enabling required APIs..."
gcloud services enable storage.googleapis.com logging.googleapis.com --project "$GOOGLE_CLOUD_PROJECT"

BUCKET_NAME="learnr-uploads-$GOOGLE_CLOUD_PROJECT"

echo "2. Checking for GCS Bucket: gs://$BUCKET_NAME"
if ! gcloud storage buckets describe gs://$BUCKET_NAME --project "$GOOGLE_CLOUD_PROJECT" >/dev/null 2>&1; then
    echo "Creating bucket $BUCKET_NAME..."
    gcloud storage buckets create gs://$BUCKET_NAME --project "$GOOGLE_CLOUD_PROJECT" --location=US
else
    echo "Bucket $BUCKET_NAME already exists."
fi

# Determine default compute service account (used by Cloud Run)
PROJECT_NUM=$(gcloud projects describe "$GOOGLE_CLOUD_PROJECT" --format="value(projectNumber)")
COMPUTE_SA="${PROJECT_NUM}-compute@developer.gserviceaccount.com"

echo "3. Granting storage.objectCreator role to Compute Service Account ($COMPUTE_SA)..."
gcloud storage buckets add-iam-policy-binding gs://$BUCKET_NAME \
    --member="serviceAccount:$COMPUTE_SA" \
    --role="roles/storage.objectCreator"

echo "Deployment infrastructure setup complete!"
echo "Make sure to set your GEMINI_API_KEY and GOOGLE_CLOUD_PROJECT in your Cloud Run deployment."
