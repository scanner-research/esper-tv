#!/bin/bash

pip3 install flask
FLASK_APP=scripts/emergency-reset.py flask run --host=0.0.0.0 --port=9999
