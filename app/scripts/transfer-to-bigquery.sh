#!/bin/bash
TABLE=$1
gsutil cp /app/data/pg/$TABLE.csv gs://esper/tmp/$TABLE.csv
bq load --autodetect --source_format=CSV tvnews.$TABLE gs://esper/tmp/$TABLE.csv
gsutil rm gs://esper/tmp/$TABLE.csv
