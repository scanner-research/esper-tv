from __future__ import print_function
from django.http import JsonResponse
from collections import defaultdict
from django.db.models import Min, Max, Q, F, Count, OuterRef, Subquery
from django.db.models.functions import Cast
from django.forms.models import model_to_dict
from pprint import pprint
from operator import itemgetter
import sys
import time
import math
import numpy as np
import traceback

from base_models import ModelDelegator
from query.datasets.stdlib import *


def search(params):
    m = ModelDelegator(params['dataset'])
    m.import_all(globals())

    def make_error(err):
        return JsonResponse({'error': err})

    # globals() is still local to a module, so we have to import models both in this context
    # and in the stdlib
    load_stdlib_models(params['dataset'])

    ############### vvv DANGER -- REMOTE CODE EXECUTION vvv ###############
    try:
        exec (params['code']) in globals(), locals()
        result = FN()
    except Exception as e:
        return make_error(traceback.format_exc())
    ############### ^^^ DANGER -- REMOTE CODE EXECUTION ^^^ ###############

    if not isinstance(result, dict):
        return make_error(
            'Result must be a dict {{result, count, type}}, received type {}'.format(type(result)))

    if not isinstance(result['result'], list):
        return make_error('Result must be a frame list')

    video_ids = set()
    frame_ids = set()
    labeler_ids = set()
    for group in result['result']:
        for obj in group['elements']:
            video_ids.add(obj['video'])
            frame_ids.add(obj['start_frame'])
            if 'end_frame' in obj:
                frame_ids.add(obj['end_frame'])

            for bbox in obj['objects']:
                labeler_ids.add(bbox['labeler'])

    def to_dict(qs):
        return {t.id: model_to_dict(t) for t in qs}

    videos = to_dict(Video.objects.filter(id__in=video_ids))
    frames = to_dict(Frame.objects.filter(id__in=frame_ids))
    labelers = to_dict(Labeler.objects.filter(id__in=labeler_ids))

    return JsonResponse({
        'success': {
            'dataset': params['dataset'],
            'count': result['count'],
            'result': result['result'],
            'type': result['type'],
            'videos': videos,
            'frames': frames,
            'labelers': labelers,
        }
    })
