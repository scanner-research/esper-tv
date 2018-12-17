#!/bin/bash

RUN_TESTS=${RUN_TESTS:=0}

# Fail fast
set -e

DEPS_DIR=/app/deps

pushd .

# Rekall
cd $DEPS_DIR
echo "Installing Rekall"
cd rekall
pip3 install --upgrade --force-reinstall --user -e .
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
rustup update
rustup override set nightly
pip3 install --upgrade --force-reinstall --user .
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
pip3 install --upgrade --force-reinstall --user .
if [ $RUN_TESTS == 1 ]; then
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
pip3 install --upgrade --force-reinstall --user -e .

jupyter nbextension enable --py --user widgetsnbextension
jupyter contrib nbextension install --user --skip-running-check
jupyter nbextensions_configurator enable --user
jupyter nbextension enable hide_input/main
jupyter nbextension enable toc2/main
jupyter nbextension enable code_prettify/autopep8
jupyter nbextension enable execute_time/ExecuteTime

jupyter nbextension install vgrid_jupyter --py --symlink --user --overwrite
jupyter nbextension enable vgrid_jupyter --py --user

cd /app
npm link vgrid

echo "SUCCESS! All dependencies installed"

popd
