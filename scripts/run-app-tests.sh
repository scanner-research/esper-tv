#!/bin/bash

# Run tests in app/tests (need to be in the app directory)
cd app
python3 -m unittest discover test
