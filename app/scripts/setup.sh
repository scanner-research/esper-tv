#!/bin/bash

# Set up frontend
npm install
npm run build

# Download various models
/app/scripts/install-rudecarnie.sh
/app/scripts/install-facenet.sh
/app/scripts/install-openpose.sh

# TinyFace
cp -r /opt/scanner/nets .
./nets/get_caffe_facenet.sh -f

# Create all database tables
python3 manage.py migrate
