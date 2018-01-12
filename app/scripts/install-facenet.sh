#!/bin/bash

mkdir -p /app/deps
pushd /app/deps
git clone https://github.com/davidsandberg/facenet.git
pushd facenet
mkdir models
pushd models
wget -q https://storage.googleapis.com/esper/models/20170512-110547.zip
unzip -q 20170512-110547.zip
rm 20170512-110547.zip
popd
popd
popd
