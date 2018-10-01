#!/bin/bash
set -e

pushd .

cd /opt/vgrid
git pull
npm install
npm run prepublish

cd /opt/vgrid_jupyter/js
git pull
npm install
npm link vgrid
npm run prepublish

cd /app
npm install
npm link vgrid
npm run prepublish

popd
