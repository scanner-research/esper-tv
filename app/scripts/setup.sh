#!/bin/bash

# Set up frontend
npm install
npm run build

# Download various models
/app/scripts/install-rudecarnie.sh
/app/scripts/install-facenet.sh
/app/scripts/install-openpose.sh

# Install Rust extensions
/app/scripts/install-rust.sh
pushd rust-scripts
./build.sh prod
popd

# TinyFace
cp -r /opt/scanner/nets .
./nets/get_caffe_facenet.sh -f

# Shell files
rm -rf /root/.bash_history
touch /root/.bash_history

# Create all database tables
python3 manage.py migrate
