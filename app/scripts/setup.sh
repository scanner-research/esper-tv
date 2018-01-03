#!/bin/bash

# Set up frontend and database
npm install
npm run build
python manage.py migrate

# Download various models

mkdir deps
pushd deps

## rude-carnie
git clone https://github.com/MattPerron/rude-carnie.git
pushd rude-carnie
gsutil cp gs://esper/models/21936-20171110T010513Z-001.zip .
unzip 21936-20171110T010513Z-001.zip
rm 21936-20171110T010513Z-001.zip
popd

## Facenet
git clone https://github.com/davidsandberg/facenet.git
pushd facenet
mkdir models
pushd models
gsutil cp gs://esper/models/20170512-110547.zip .
unzip 20170512-110547.zip
rm 20170512-110547.zip
popd
popd

## OpenPose
mkdir openpose-models
pushd openpose-models
curl https://codeload.github.com/CMU-Perceptual-Computing-Lab/openpose/tar.gz/master | tar -xz --strip=2 openpose-master/models
./getModels.sh
popd

## Spacy
python -m spacy download en

popd

## TinyFace
cp -r /opt/scanner/nets .
./nets/get_caffe_facenet.sh -f

# Create all database tables
python manage.py migrate
