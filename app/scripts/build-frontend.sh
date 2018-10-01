#!/bin/bash
set -e

pushd .

cd /opt/vgrid
npm install
npm run prepublish

cd /opt/vgrid_jupyter/js
npm install
npm run prepublish

cd /app
npm install
npm run prepublish

popd
