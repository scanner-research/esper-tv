from django.http import JsonResponse
from collections import defaultdict
import django.db.models as models
from django.forms.models import model_to_dict
from pprint import pprint
from operator import itemgetter
import sys
import time
import math
import numpy as np
import traceback
import datetime

from query.datasets.stdlib import *
import query.datasets.tvnews.embed_google_images as embed_google_images


def search(params):
    m = ModelDelegator(params['dataset'])
    m.import_all(globals())

    def make_error(err):
        return JsonResponse({'error': err})

    # globals() is still local to a module, so we have to import models both in this context
    # and in the stdlib
    load_stdlib_models(params['dataset'])

    try:
        fprint('Executing')
        ############### vvv DANGER -- REMOTE CODE EXECUTION vvv ###############
        _globals = {}
        _locals = {}
        for k in globals():
            _globals[k] = globals()[k]
        for k in locals():
            _locals[k] = locals()[k]
        exec ((params['code']), _globals, _locals)
        result = _locals['FN']()
        ############### ^^^ DANGER -- REMOTE CODE EXECUTION ^^^ ###############

        if not isinstance(result, dict):
            return make_error(
                'Result must be a dict {{result, count, type}}, received type {}'.format(
                    type(result)))

        if not isinstance(result['result'], list):
            return make_error('Result must be a frame list')

        video_ids = set()
        frame_ids = set()
        labeler_ids = set([Labeler.objects.get(name='handlabeled-face').id])
        gender_ids = set()
        for group in result['result']:
            for obj in group['elements']:
                video_ids.add(obj['video'])
                frame_ids.add(obj['min_frame'])
                if 'max_frame' in obj:
                    frame_ids.add(obj['max_frame'])

                if 'objects' in obj:
                    for bbox in obj['objects']:
                        labeler_ids.add(bbox['labeler_id'])
                        if 'gender_id' in bbox:
                            gender_ids.add(bbox['gender_id'])

        def to_dict(qs):
            return {t['id']: t for t in list(qs.values())}

        videos = to_dict(Video.objects.filter(id__in=video_ids))
        frames = to_dict(Frame.objects.filter(id__in=frame_ids))
        labelers = to_dict(Labeler.objects.filter(id__in=labeler_ids))
        genders = to_dict(Gender.objects.all())

        return JsonResponse({
            'success': {
                'dataset': params['dataset'],
                'count': result['count'],
                'result': result['result'],
                'type': result['type'],
                'videos': videos,
                'frames': frames,
                'labelers': labelers,
                'genders': genders
            }
        })
    except Exception:
        return make_error(traceback.format_exc())
