from scannerpy import ProtobufGenerator, Config, Database, Job, BulkJob, DeviceType
from query.base_models import ModelDelegator, Track
from django.db.models import Min, Max, Count, F, OuterRef, Subquery
from django.db.models.functions import Cast
import django.db.models as models
import os
import subprocess as sp
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import pandas as pd
import qgrid
import progressbar
import sys

plt.rc("axes.spines", top=False, right=False)
sns.set_style('white')

m = ModelDelegator(os.environ.get('DATASET'))
m.import_all(globals())

cfg = Config()
proto = ProtobufGenerator(cfg)

def progress_bar(n):
    return progressbar.ProgressBar(max_value=n, widgets=[
        progressxbar.Percentage(), ' ',
        '(', progressbar.SimpleProgress(), ')',
        ' ', progressbar.Bar(), ' ',
        progressbar.AdaptiveETA(),
    ])

# http://code.activestate.com/recipes/577058/
def query_yes_no(question, default="yes"):
    """Ask a yes/no question via raw_input() and return their answer.

    "question" is a string that is presented to the user.
    "default" is the presumed answer if the user just hits <Enter>.
        It must be "yes" (the default), "no" or None (meaning
        an answer is required of the user).

    The "answer" return value is True for "yes" or False for "no".
    """
    valid = {"yes": True, "y": True, "ye": True,
             "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        sys.stdout.write(question + prompt)
        choice = raw_input().lower()
        if default is not None and choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' "
                             "(or 'y' or 'n').\n")
