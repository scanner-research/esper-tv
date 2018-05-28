#!/bin/bash
TABLE=$1
echo "\copy (SELECT * FROM $TABLE) TO '/app/data/pg/$TABLE.csv' WITH CSV HEADER;" | psql -h db esper will
