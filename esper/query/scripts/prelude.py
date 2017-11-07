from scannerpy import ProtobufGenerator, Config, Database, Job
from query.base_models import ModelDelegator
from django.db.models import Min, Max, Count, F
import os
import subprocess as sp
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import pandas as pd
import qgrid

plt.rc("axes.spines", top=False, right=False)
sns.set_style('white')

m = ModelDelegator(os.environ.get('DATASET'))
for model in m._dataset.all_models():
    globals()[model] = getattr(m, model)

cfg = Config()
proto = ProtobufGenerator(cfg)
