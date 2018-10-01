#!/bin/bash
set -e

pushd .

cd /opt/vgrid
git pull
npm install
npm run build

cd /opt/vgrid_jupyter/js
git pull
npm install
npm link vgrid
npm run build

cd /app
npm install
npm link vgrid
npm run build

popd
