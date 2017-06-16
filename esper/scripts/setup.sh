#!/bin/bash

# Set up frontend and database
npm install
./node_modules/.bin/webpack --config webpack.config.js
python manage.py migrate

mkdir deps
pushd deps

# Get Pari's face clustering stuff
git clone https://github.com/scanner-research/face_recognizer
pushd face_recognizer/data
wget http://vis-www.cs.umass.edu/lfw/lfw.tgz
tar -xf lfw.tgz
rm lfw.tgz
popd

# Get rude_carnie gender recognition
git clone https://github.com/Parimarjan/rude-carnie.git
# tmp solution (this is not downloaded anywhere)
cp -r /tmp/inception_gender_checkpoint ./rude-carnie/

# Get facenet
git clone https://github.com/davidsandberg/facenet.git
pushd facenet
mkdir models
#model should be downloaded and placed here manually (has to be downloaded from google drive)
popd

# Get face recognition network
git clone https://github.com/cmusatyalab/openface
pushd openface
./models/get-models.sh
popd
popd

# Get face detection network
cp -r /opt/scanner/nets .
./nets/get_caffe_facenet.sh -f
