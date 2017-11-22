#!/bin/bash

# Transfers GCS access logs into BigQuery.
# See: https://cloud.google.com/storage/docs/access-logs

wget http://storage.googleapis.com/pub/cloud_storage_usage_schema_v0.json
wget http://storage.googleapis.com/pub/cloud_storage_storage_schema_v0.json
bq load --skip_leading_rows=1 storageanalysis.usage \
   "gs://esper/logs/_usage*" \
   ./cloud_storage_usage_schema_v0.json
bq load --skip_leading_rows=1 storageanalysis.storage \
   "gs://esper/logs/_storage*" \
   ./cloud_storage_storage_schema_v0.json
gsutil -m rm -r gs://esper/logs
