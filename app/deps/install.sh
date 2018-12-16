#!/bin/bash
# Temporary solution to reinstall deps on container restart.

RUN_TESTS=${RUN_TESTS:=0}

# Fail fast
set -e

DEPS_DIR=/app/deps

pushd .

# Rekall
cd $DEPS_DIR
echo "Installing Rekall"
cd rekall
pip3 install --user -e .
if [ $RUN_TESTS == 1 ]; then
        python3 setup.py test
fi

# Model server
cd $DEPS_DIR
echo "Installing Model-Server"
cd esper-model-server
./extract_data.sh
pip3 install --user -r requirements.txt
if [ $RUN_TESTS == 1 ]; then
        pytest -v tests
fi

# Caption-Index
cd $DEPS_DIR
echo "Installing Caption-Index"
cd caption-index
pip3 install --user -e .
./get_models.sh
if [ $RUN_TESTS == 1 ]; then
        python3 setup.py test
fi

# Rs-Embed
cd $DEPS_DIR
echo "Installing Rs-Embed"
cd rs-embed
rustup update
rustup override set nightly
pip3 install --user .
if [ $RUN_TESTS == 1 ]; then
        #echo 'Skipping Rs-Embed tests... This is a TODO due to env issues'
        python3 setup.py test
fi

cd $DEPS_DIR
echo "Installing vgrid"
cd vgrid
npm install
npm link
npm run build

cd $DEPS_DIR
echo "Installing vgrid_jupyter"
cd vgrid_jupyter/js
npm link vgrid
npm install
npm run build
cd ..
pip3 install --user -e .
jupyter nbextension install vgrid_jupyter --py --symlink --user --overwrite
jupyter nbextension enable vgrid_jupyter --py --user

cd /app
npm link vgrid

echo "SUCCESS! All dependencies installed"

popd
