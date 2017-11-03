from scannerpy import ProtobufGenerator, Config, Database, Job
from query.base_models import ModelDelegator
from django.db.models import Min, Max, Count, F
import os
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import pandas as pd
import qgrid

plt.rc("axes.spines", top=False, right=False)
sns.set_style('white')

m = ModelDelegator(os.environ.get('DATASET'))
Video, Frame, Face, FaceTrack, FaceFeatures, Labeler, Gender = \
    m.Video, m.Frame, m.Face, m.FaceTrack, m.FaceFeatures, m.Labeler, m.Gender

cfg = Config()
proto = ProtobufGenerator(cfg)
