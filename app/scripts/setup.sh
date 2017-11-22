#!/bin/bash

# Set up frontend and database
npm install
npm run build
python manage.py migrate

mkdir deps
pushd deps

# Get rude_carnie gender recognition
git clone https://github.com/MattPerron/rude-carnie.git
# tmp solution (this is not downloaded anywhere)
cp -r /tmp/inception_gender_checkpoint ./rude-carnie/

# Get facenet
git clone https://github.com/davidsandberg/facenet.git
pushd facenet
mkdir models
pushd models
gsutil cp gs://esper/models/20170512-110547.zip .
unzip 20170512-110547.zip
rm 20170512-110547.zip
popd
popd

cp -r /opt/openpose/models openpose-models
pushd openpose-models
./getModels.sh
popd

popd

# Get face detection network
cp -r /opt/scanner/nets .
./nets/get_caffe_facenet.sh -f

# Setup default dataset
python manage.py migrate
