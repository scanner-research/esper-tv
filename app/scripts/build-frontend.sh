#!/bin/bash

pushd .

cd /opt/vgrid
npm run prepublish

cd /opt/vgrid_jupyter/js
npm run prepublish

cd /app
npm run prepublish

popd
