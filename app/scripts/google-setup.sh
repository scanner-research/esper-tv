#!/bin/bash

# This is for Docker's use only. Don't run this yourself.

if [[ ! -z $GOOGLE_PROJECT ]]; then
   gcloud config set project ${GOOGLE_PROJECT}
   gcloud auth activate-service-account --key-file=$GOOGLE_APPLICATION_CREDENTIALS
fi
