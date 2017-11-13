from scannerpy import ProtobufGenerator, Config, Database, Job, BulkJob, DeviceType
from query.base_models import ModelDelegator
from django.db.models import Min, Max, Count, F
import os
import subprocess as sp
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import pandas as pd
import qgrid
import progressbar

plt.rc("axes.spines", top=False, right=False)
sns.set_style('white')

m = ModelDelegator(os.environ.get('DATASET'))
m.import_all(globals())

cfg = Config()
proto = ProtobufGenerator(cfg)

def progress_bar(n):
    return progressbar.ProgressBar(max_value=n, widgets=[
        progressbar.Percentage(), ' ',
        '(', progressbar.SimpleProgress(), ')',
        ' ', progressbar.Bar(), ' ',
        progressbar.AdaptiveETA(),
    ])
