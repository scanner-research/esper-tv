#!/bin/bash
bq query -q --format=json "select last(storage_byte_hours) from storageanalysis.storage" | jq '(.[0].f0_ | tonumber) / (1024 * 1024 * 1024 * 1024)'
