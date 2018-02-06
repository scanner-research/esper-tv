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


def access(obj, path):
    fields = path.split('__')
    for f in fields:
        obj = getattr(obj, f)
    return obj


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
        'labeler_id': f.labeler.id,
    }


def gender_to_dict(f):
    d = bbox_to_dict(f.face)
    d['gender_id'] = f.gender.id
    return d


def identity_to_dict(f):
    d = bbox_to_dict(f.face)
    d['identity_id'] = f.identity.id
    return d


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
LIMIT = 100
STRIDE = 1


def qs_to_result(result,
                 group=False,
                 segment=False,
                 stride=1,
                 shuffle=False,
                 custom_order=False,
                 frame_major=True):
    #count = result.count()
    count = 0

    if shuffle:
        result = result.order_by('?')

    materialized_result = []
    cls = result.model
    bases = cls.__bases__
    if bases[0] is base_models.Frame:
        # if not shuffle and not custom_order:
        #     result = result.order_by('video', 'number')

        for frame in result[:LIMIT * stride:stride]:
            materialized_result.append({
                'video': frame.video.id,
                'start_frame': frame.number,
                'objects': []
            })

    elif bases[0] is base_models.Attribute:
        if cls is FaceGender or cls is FaceIdentity:
            frame_path = 'face__person__frame'
            if cls is FaceGender:
                result = result.select_related('face', 'gender')
            else:
                result = result.select_related('face', 'identity')
        else:
            frame_path = 'person__frame'
        result = result.select_related(frame_path)

        # if not shuffle and not custom_order:
        #     result = result.order_by(frame_path + '__video', frame_path + '__number')

        if cls is Face:
            fn = bbox_to_dict
        elif cls is FaceGender:
            fn = gender_to_dict
        elif cls is FaceIdentity:
            fn = identity_to_dict
        elif cls is Pose:
            fn = pose_to_dict

        if frame_major:
            frames = set()
            frame_ids = set()
            with Timer('a'):
                result.values(frame_path + '__video', frame_path + '__number',
                              frame_path + '__id').print_sql()
                sys.stdout.flush()

                for inst in list(
                        result.values(frame_path + '__video', frame_path + '__number',
                                      frame_path + '__id')[:LIMIT * stride:stride]):
                    frames.add((inst[frame_path + '__video'], inst[frame_path + '__number'],
                                inst[frame_path + '__id']))
                    frame_ids.add(inst[frame_path + '__id'])
            sys.stdout.flush()

            with Timer('b'):
                all_results = collect(
                    list(result.filter(**{
                        frame_path + '__in': list(frame_ids)
                    })), lambda t: access(t, frame_path + '__id'))
            sys.stdout.flush()

            frames = list(frames)
            frames.sort(key=itemgetter(0, 1))
            for (video, frame_num, frame_id) in frames:
                materialized_result.append({
                    'video': video,
                    'start_frame': frame_num,
                    'objects': [fn(inst) for inst in all_results[frame_id]]
                })

        else:
            for inst in result[:LIMIT * stride:stride]:
                r = {
                    'video': inst.person.frame.video.id,
                    'start_frame': inst.person.frame.number,
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
                'start_frame': t.min_frame,
                'end_frame': t.max_frame,
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
            points.extend([(video, start, False), (video, end, True)])
        points.sort(key=itemgetter(0, 1, 2))

        pprint(points)
        sys.stdout.flush()

        # TODO(wcrichto): this is probably broken after change from frame id -> frame number

        intervals_active = 0
        boundaries = []
        i = 0
        intvl_id = 0
        while i < len(points) - 1:
            num_intervals = 1
            (_, _, frame, is_end) = points[i]
            while i < len(points) - 1:
                if points[i + 1][1] == frame:
                    num_intervals += 1
                    i += 1
                else:
                    break

            pprint((points[i], num_intervals))
            sys.stdout.flush()

            if not is_end:
                intervals_active += num_intervals
                boundaries.append((frame, points[i + 1][1], intvl_id))
            else:
                intervals_active -= num_intervals
                if intervals_active > 0:
                    boundaries.append((frame, points[i + 1][1], intvl_id))
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
