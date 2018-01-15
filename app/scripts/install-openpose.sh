#!/bin/bash

mkdir -p /app/deps/openpose-models
pushd /app/deps/openpose-models
curl -s https://codeload.github.com/CMU-Perceptual-Computing-Lab/openpose/tar.gz/master | \
    tar -xz --strip=2 openpose-master/models
./getModels.sh
popd
