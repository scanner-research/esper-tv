from scannerpy import ProtobufGenerator, Config, Database, Job, BulkJob, DeviceType
from query.base_models import ModelDelegator, Track, BoundingBox
from query.datasets.stdlib import *
from django.db import connections
from django.db.models.query import QuerySet
from django.db.models import Min, Max, Count, F, OuterRef, Subquery, Sum, Avg, Func
from django.db.models.functions import Cast, Extract
from django.utils import timezone
import datetime
from IPython.core.getipython import get_ipython
import django.db.models as models
import os
import subprocess as sp
import numpy as np
import pandas as pd
import sys
import sqlparse

# Import all models for current dataset
m = ModelDelegator(os.environ.get('DATASET'))
m.import_all(globals())

# Access to Scanner protobufs
cfg = Config()
proto = ProtobufGenerator(cfg)

# Only run if we're in an IPython notebook
if get_ipython() is not None:
    # Render all DataFrames via qgrid
    import qgrid
    qgrid.set_grid_option('minVisibleRows', 1)
    qgrid.enable()

    # Matplotlib/seaborn config
    import matplotlib.pyplot as plt
    import seaborn as sns
    plt.rc("axes.spines", top=False, right=False)
    sns.set_style('white')


def progress_bar(n):
    import progressbar
    return progressbar.ProgressBar(
        max_value=n,
        widgets=[
            progressxbar.Percentage(),
            ' ',
            '(',
            progressbar.SimpleProgress(),
            ')',
            ' ',
            progressbar.Bar(),
            ' ',
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
    valid = {"yes": True, "y": True, "ye": True, "no": False, "n": False}
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
            sys.stdout.write("Please respond with 'yes' or 'no' " "(or 'y' or 'n').\n")


def bbox_area(f):
    return (f.bbox_x2 - f.bbox_x1) * (f.bbox_y2 - f.bbox_y1)


def bbox_midpoint(f):
    return np.array([(f.bbox_x1 + f.bbox_x2) / 2, (f.bbox_y1 + f.bbox_y2) / 2])


def bbox_dist(f1, f2):
    return np.linalg.norm(bbox_midpoint(f1) - bbox_midpoint(f2))


def bbox_iou(f1, f2):
    x1 = max(f1.bbox_x1, f2.bbox_x1)
    x2 = min(f1.bbox_x2, f2.bbox_x2)
    y1 = max(f1.bbox_y1, f2.bbox_y1)
    y2 = min(f1.bbox_y2, f2.bbox_y2)

    if x1 > x2 or y1 > y2: return 0

    intersection = (x2 - x1) * (y2 - y1)
    return intersection / (bbox_area(f1) + bbox_area(f2) - intersection)


# TODO(wcrichto): doesn't work for queries with strings
class QuerySetMixin:
    def explain(self):
        cursor = connections[self.db].cursor()
        cursor.execute('EXPLAIN ANALYZE %s' % str(self.query))
        print("\n".join(([t for (t, ) in cursor.fetchall()])))

    def print_sql(self):
        q = str(self.query)
        print(sqlparse.format(q, reindent=True))


QuerySet.__bases__ += (QuerySetMixin, )
