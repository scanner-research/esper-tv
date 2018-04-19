from glob import glob
from . import base_models as base
import os
import sys
import importlib

for dataset_path in glob("/app/query/datasets/*/"):
    dataset_name = dataset_path.split('/')[-2]
    if dataset_name == '__pycache__':
        continue

    with base.Dataset(dataset_name):
        importlib.import_module('query.datasets.{}.models'.format(dataset_name))
