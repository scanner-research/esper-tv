#!/bin/bash
set -e

pushd esper_jupyter
pip3 install -e .
jupyter nbextension install esper_jupyter --py --symlink --sys-prefix
jupyter nbextension enable esper_jupyter --py --sys-prefix
popd

python3 /app/scripts/set-jupyter-password.py
