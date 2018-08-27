#!/bin/bash

gcloud container clusters create archive-download \
       --zone us-east1-b --machine-type "n1-standard-2" --disk-size "100" --num-nodes 50 \
       --network redis --enable-autoscaling --min-nodes 1 --max-nodes 50 \
       --enable-ip-alias
