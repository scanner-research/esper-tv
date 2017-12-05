#!/bin/bash

SERVICE_ACCOUNT=$(gcloud sql instances describe esper-shared --format=json | jq -r '.serviceAccountEmailAddress')

gcloud sql instances export esper-public-dev gs://esper/tmp-dump.sql --database=esper
gsutil acl ch -u $SERVICE_ACCOUNT:W gs://esper
gsutil acl ch -u $SERVICE_ACCOUNT:R gs://esper/tmp-dump.sql
cat <<EOF | psql -h 104.196.237.12 postgres will
DROP DATABASE esper;
CREATE DATABASE esper;
EOF
gcloud sql instances import esper-shared gs://esper/tmp-dump.sql --database=esper
gsutil rm gs://esper/tmp-dump.sql
