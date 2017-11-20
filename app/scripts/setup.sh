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
#model should be downloaded and placed here manually (has to be downloaded from google drive)
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
python manage.py new_dataset default
python manage.py makemigrations
python manage.py migrate
