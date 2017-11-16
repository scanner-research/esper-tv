#!/bin/bash

gcloud sql instances export esper-public-dev gs://esper/tmp-dump.sql
cat <<EOF | psql -h 104.196.237.12 postgres will
DROP DATABASE esper;
CREATE DATABASE esper;
EOF
gcloud sql instances import esper-shared gs://esper/tmp-dump.sql --database=esper
