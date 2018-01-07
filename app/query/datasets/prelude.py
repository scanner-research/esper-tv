from scannerpy import ProtobufGenerator, Config, Database, Job, BulkJob, DeviceType, ColumnType, ScannerException
from storehouse import StorageConfig, StorageBackend
from query.base_models import ModelDelegator, Track, BoundingBox
from query.datasets.stdlib import *
from django.db import connections
from django.db.models.query import QuerySet
from django.db.models import Min, Max, Count, F, OuterRef, Subquery, Sum, Avg, Func
from django.db.models.functions import Cast, Extract
from django.utils import timezone
from django_bulk_update.manager import BulkUpdateManager
from IPython.core.getipython import get_ipython
from timeit import default_timer as now
import datetime
import _strptime  # https://stackoverflow.com/a/46401422/356915
import django.db.models as models
import os
import subprocess as sp
import numpy as np
import pandas as pd
import sys
import sqlparse
import logging
import dill
import json
import multiprocessing as mp
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from tqdm import tqdm

# Import all models for current dataset
m = ModelDelegator(os.environ.get('DATASET'))
m.import_all(globals())

# Access to Scanner protobufs
cfg = Config()
proto = ProtobufGenerator(cfg)

# Logging config
log = logging.getLogger('esper')
log.setLevel(logging.DEBUG)
if not log.handlers:

    class CustomFormatter(logging.Formatter):
        def format(self, record):
            level = record.levelname[0]
            time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')[2:]
            if len(record.args) > 0:
                record.msg = '({})'.format(
                    ', '.join([str(x) for x in [record.msg] + list(record.args)]))
                record.args = ()
            return '{level} {time} {filename}:{lineno:03d}] {msg}'.format(
                level=level, time=time, **record.__dict__)

    handler = logging.StreamHandler()
    handler.setFormatter(CustomFormatter())
    log.addHandler(handler)

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

# Setup Storehouse
ESPER_ENV = os.environ.get('ESPER_ENV')
BUCKET = os.environ.get('BUCKET')
DATA_PATH = os.environ.get('DATA_PATH')
if ESPER_ENV == 'google':
    storage_config = StorageConfig.make_gcs_config(BUCKET)
else:
    storage_config = StorageConfig.make_posix_config()
storage = StorageBackend.make_from_config(storage_config)


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


def unzip(l):
    return tuple(zip(*l))


def group_by_frame(objs, fn_key, fn_sort, output_dict=False, include_frame=True):
    d = defaultdict(list)
    for obj in objs:
        d[fn_key(obj)].append(obj)

    for l in d.values():
        l.sort(key=fn_sort)

    if output_dict:
        return dict(d)
    else:
        l = sorted(d.iteritems(), key=itemgetter(0))
        if not include_frame:
            l = [f for _, f in l]
        return l


def ingest_if_missing(db, videos):
    needed = [video.path for video in videos if not db.has_table(video.path)]
    if len(needed) > 0:
        _, failed = db.ingest_videos([(p, p) for p in needed])
        assert (len(failed) == 0)


def shape(l):
    if type(l) is list or type(l) is tuple:
        return 'list({})'.format(shape(l[0]))
    else:
        return type(l).__name__


def par_for(f, l, process=False, workers=None):
    Pool = ProcessPoolExecutor if process else ThreadPoolExecutor
    with Pool(max_workers=mp.cpu_count() if workers is None else workers) as executor:
        return list(tqdm(executor.map(f, l), total=len(l)))


def master_addr():
    ip = sp.check_output(
        '''
    kubectl get pods -l 'app=scanner-master' -o json | \
    jq '.items[0].spec.nodeName' -r | \
    xargs -I {} kubectl get nodes/{} -o json | \
    jq '.status.addresses[] | select(.type == "ExternalIP") | .address' -r
    ''',
        shell=True).strip()

    port = sp.check_output(
        '''
    kubectl get svc/scanner-master -o json | \
    jq '.spec.ports[0].nodePort' -r
    ''',
        shell=True).strip()

    return '{}:{}'.format(ip, port)


class Timer:
    def __init__(self, s):
        self.s = s
        log.debug('-- START: {}'.format(s))

    def __enter__(self):
        self.start = now()

    def __exit__(self, a, b, c):
        log.debug('-- END: {} -- {:.3f}s'.format(self.s, now() - self.start))


PICKLE_CACHE_DIR = '/app/.cache'


class PickleCache:
    def __init__(self):
        if not os.path.isdir(PICKLE_CACHE_DIR):
            os.mkdir(PICKLE_CACHE_DIR)

    def _fname(self, k):
        return '{}/{}.pkl'.format(PICKLE_CACHE_DIR, k)

    def has(self, k):
        return os.path.isfile(self._fname(k))

    def set(self, k, v):
        with open(self._fname(k), 'w') as f:
            dill.dump(v, f)

    def get(self, k):
        if not self.has(k):
            raise Exception('Missing cache key {}'.format(k))

        with open(self._fname(k), 'r') as f:
            return dill.load(f)


pcache = PickleCache()


class QuerySetMixin:
    def explain(self):
        # TODO(wcrichto): doesn't work for queries with strings
        cursor = connections[self.db].cursor()
        cursor.execute('EXPLAIN ANALYZE %s' % str(self.query))
        print("\n".join(([t for (t, ) in cursor.fetchall()])))

    def print_sql(self):
        q = str(self.query)
        print(sqlparse.format(q, reindent=True))

    def exists(self):
        try:
            next(self)
            return True
        except self.model.DoesNotExist:
            return False


QuerySet.__bases__ += (QuerySetMixin, )


class BulkUpdateManagerMixin:
    def batch_create(self, objs, batch_size=1000):
        for i in range(0, len(objs), batch_size):
            self.bulk_create(objs[i:(i + batch_size)])


BulkUpdateManager.__bases__ += (BulkUpdateManagerMixin, )


def model_repr(model):
    def field_repr(field):
        return '{}: {}'.format(field.name, getattr(model, field.name))

    return '{}({})'.format(
        model.__class__.__name__,
        ', '.join([
            field_repr(field) for field in model._meta.get_fields(include_hidden=False)
            if not field.is_relation
        ]))


models.Model.__repr__ = model_repr
