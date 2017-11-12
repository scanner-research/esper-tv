from glob import glob
import base_models as base
import os
import sys
import importlib

for dataset_path in glob("query/datasets/*/"):
    dataset_name = dataset_path.split('/')[-2]
    with base.Dataset(dataset_name):
        importlib.import_module('query.datasets.{}.models'.format(dataset_name))
