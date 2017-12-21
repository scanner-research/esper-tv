from __future__ import print_function
from django.http import JsonResponse
from collections import defaultdict
from django.forms.models import model_to_dict
from pprint import pprint
from operator import itemgetter
import sys
import time
import math
import numpy as np
import traceback
from timeit import default_timer as now
import query.base_models as base_models

from query.datasets.prelude import *


def fprint(*args):
    print(*args)
    sys.stdout.flush()


def load_stdlib_models(dataset):
    m = ModelDelegator(dataset)
    m.import_all(globals())


def at_fps(qs, n=1):
    return qs.annotate(_tmp=F('number') % (
        Cast('video__fps', models.IntegerField()) / n)).filter(_tmp=0)


def bbox_to_dict(f):
    return {
        'id': f.id,
        'type': 'bbox',
        'bbox_x1': f.bbox_x1,
        'bbox_x2': f.bbox_x2,
        'bbox_y1': f.bbox_y1,
        'bbox_y2': f.bbox_y2,
        'bbox_score': f.bbox_score,
        'labeler': f.labeler.id
    }


def pose_to_dict(f):
    return {
        'id': f.id,
        'labeler': f.labeler.id,
        'type': 'pose',
        'keypoints': {
            'hand_left': f.hand_keypoints()[0].tolist(),
            'hand_right': f.hand_keypoints()[1].tolist(),
            'pose': f.pose_keypoints().tolist(),
            'face': f.face_keypoints().tolist()
        }
    }


def group_result(materialized_result):
    grouped_result = defaultdict(list)
    for r in materialized_result:
        grouped_result[(r['video'], r['start_frame'])].extend(r['objects'])

    flat_result = [{
        'video': t1,
        'start_frame': t2,
        'objects': r
    } for (t1, t2), r in grouped_result.iteritems()]
    return sorted(flat_result, key=itemgetter('video', 'start_frame'))


def simple_result(result, ty):
    return {
        'result': [{
            'type': 'flat',
            'elements': [r]
        } for r in result],
        'count': len(result),
        'type': ty
    }


def filter_poses(ty, fn, used_kps, poses=None):
    filtered = []
    if poses is None:
        poses = Pose.objects.all().order_by('id').select_related('person__frame',
                                                                 'person__frame__video')[:100000:10]
    for pose in poses:
        kps = getattr(pose, '{}_keypoints'.format(ty))()
        bad = False
        for k in used_kps:
            if kps[k][2] == 0:
                bad = True
                break
        if bad:
            continue

        if fn(kps):
            filtered.append(pose)
    return filtered


# TODO(wcrichto): allow pagination to make repeated requests to backend
LIMIT = 500
STRIDE = 1


def qs_to_result(result,
                 group=False,
                 segment=False,
                 stride=1,
                 shuffle=False,
                 custom_order=False,
                 frame_major=False):
    try:
        sample = result[0]
    except IndexError:
        return {'result': [], 'count': 0, 'type': ''}

    count = result.count()

    if shuffle:
        result = result.order_by('?')

    # TODO(wcrichto): do something if custom_order=True

    materialized_result = []
    cls = sample.__class__
    bases = sample.__class__.__bases__
    if bases[0] is base_models.Frame:
        if not shuffle and not custom_order:
            result = result.order_by('video', 'number')

        for frame in result[:LIMIT * stride:stride]:
            materialized_result.append({
                'video': frame.video.id,
                'start_frame': frame.id,
                'objects': []
            })

    elif bases[0] is base_models.Attribute:
        if not shuffle and not custom_order:
            result = result.order_by('person__frame__video', 'person__frame__number')

        if cls is Face:
            fn = bbox_to_dict
        elif cls is Pose:
            fn = pose_to_dict

        if frame_major:
            frames = set()
            for inst in result.values('person__frame__video',
                                      'person__frame')[:LIMIT * stride:stride]:
                frames.add((inst['person__frame__video'], inst['person__frame']))
            frames = list(frames)
            frames.sort(key=itemgetter(0, 1))
            for (video, frame) in frames:
                materialized_result.append({
                    'video':
                    video,
                    'start_frame':
                    frame,
                    'objects': [fn(inst) for inst in result.filter(person__frame=frame)]
                })

        else:
            for inst in result.select_related('person__frame')[:LIMIT * stride:stride]:
                r = {
                    'video': inst.person.frame.video.id,
                    'start_frame': inst.person.frame.id,
                    'objects': [fn(inst)]
                }
                materialized_result.append(r)

    elif bases[0] is base_models.Track:
        if not shuffle and not custom_order:
            result = result.order_by('video', 'min_frame')

        for t in result.annotate(duration=Track.duration_expr()).filter(duration__gt=0)[:LIMIT]:
            if cls is PersonTrack:
                model = Person
            else:
                model = None

            result = {
                'video': t.video.id,
                'track': t.id,
                'start_frame': Frame.objects.get(video=t.video, number=t.min_frame).id,
                'end_frame': Frame.objects.get(video=t.video, number=t.max_frame).id,
            }

            if model is not None and False:
                min_model = model.objects.filter(frame__number=t.min_frame, tracks=t)[0]
                result['objects'] = [pose_to_dict(Pose.objects.filter(person=min_model)[0])]
            else:
                result['objects'] = []

            materialized_result.append(result)

        materialized_result.sort(key=itemgetter('video', 'start_frame'))

    else:
        raise Exception("Unsupported class")

    ty_name = cls.__name__

    if group:
        materialized_result = group_result(materialized_result)
        ty_name = 'Frame grouped by {}'.format(ty_name)

    if segment:
        tracks = [r['track'] for r in materialized_result]
        assert (len(tracks) > 0)
        intervals = [(r['video'], r['start_frame'], r['end_frame']) for r in materialized_result]
        points = []
        for (video, start, end) in intervals:
            start_num = Frame.objects.get(id=start).number
            end_num = Frame.objects.get(id=end).number
            points.extend([(video, start_num, start, False), (video, end_num, end, True)])
        points.sort(key=itemgetter(0, 1, 3))

        pprint(points)
        sys.stdout.flush()

        intervals_active = 0
        boundaries = []
        i = 0
        intvl_id = 0
        while i < len(points) - 1:
            num_intervals = 1
            (_, _, frame, is_end) = points[i]
            while i < len(points) - 1:
                if points[i + 1][2] == frame:
                    num_intervals += 1
                    i += 1
                else:
                    break

            pprint((points[i], num_intervals))
            sys.stdout.flush()

            if not is_end:
                intervals_active += num_intervals
                boundaries.append((frame, points[i + 1][2], intvl_id))
            else:
                intervals_active -= num_intervals
                if intervals_active > 0:
                    boundaries.append((frame, points[i + 1][2], intvl_id))
                else:
                    intvl_id += 1

            i += 1

        groups = []
        materialized_result = []
        cur_intvl_id = boundaries[0][2]
        for (start, end, intvl_id) in boundaries:
            if intvl_id != cur_intvl_id:
                video = Video.objects.get(id=materialized_result[0]['video'])
                intvl_start = materialized_result[0]['start_frame']
                intvl_end = materialized_result[-1]['end_frame']
                format_time = lambda t: time.strftime('%H:%M:%S', time.gmtime(math.floor(t / video.fps)))

                groups.append({
                    'type':
                    'contiguous',
                    'label':
                    '{} -- {}'.format(
                        format_time(Frame.objects.get(id=intvl_start).number),
                        format_time(Frame.objects.get(id=intvl_end).number)),
                    'elements':
                    materialized_result
                })
                materialized_result = []
                cur_intvl_id = intvl_id

            f = Frame.objects.filter(id=start).select_related('video').get()
            materialized_result.append({
                'video':
                f.video.id,
                'start_frame':
                start,
                'end_frame':
                end,
                'objects': [
                    bbox_to_dict(face)
                    for face in Face.objects.filter(person__frame=f, person__tracks__in=tracks)
                ]
            })

        ty_name = '{} (segmented)'.format(ty_name)
    else:
        groups = [{'type': 'flat', 'label': '', 'elements': [r]} for r in materialized_result]

    return {'result': groups, 'count': count, 'type': ty_name}
