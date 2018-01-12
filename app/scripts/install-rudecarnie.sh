#!/bin/bash

mkdir -p /app/deps
pushd /app/deps
git clone https://github.com/scanner-research/rude-carnie.git
pushd rude-carnie
wget -q https://storage.googleapis.com/esper/models/21936-20171110T010513Z-001.zip
unzip -q 21936-20171110T010513Z-001.zip
rm 21936-20171110T010513Z-001.zip
popd
popd
