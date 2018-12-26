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
import os
import query.base_models as base_models
import importlib
from typing import Any, Dict, List, Union
from django.db.models.query import QuerySet
from django.db.models import F
from django.db.models.functions import Cast
import django.db.models as models
from query.base_models import Track
from query.models import \
    Face, FaceGender, FaceIdentity, Labeler, Video, Frame, Gender, Segment, Tag, Object, \
    Topic, Identity
import django.apps
import os


BUCKET = os.environ.get('BUCKET')


def collect(l, kfn):
    d = defaultdict(list)
    for x in l:
        d[kfn(x)].append(x)
    return dict(d)


def access(obj: Any, path: str) -> Any:
    fields = path.split('__')
    for f in fields:
        obj = getattr(obj, f)
    return obj


def fprint(*args) -> None:
    print(*args)
    sys.stdout.flush()


def bbox_to_dict(f: Any) -> Dict:
    d = {
        'id': f.id,
        'type': 'bbox',
        'bbox_x1': f.bbox_x1,
        'bbox_x2': f.bbox_x2,
        'bbox_y1': f.bbox_y1,
        'bbox_y2': f.bbox_y2,
    }

    if hasattr(f, 'background'):
        d['background'] = f.background
    elif hasattr(f, 'labeler'):
        d['labeler_id'] = f.labeler.id

    return d

def gender_to_dict(f: Any) -> Dict:
    d = bbox_to_dict(f.face)
    d['gender_id'] = f.gender.id

    # TODO(wcrichto): this is a hack
    if hasattr(f, 'identity') and f.identity is not None:
        d['identity_id'] = f.identity

    return d


def identity_to_dict(f: Any) -> Dict:
    d = bbox_to_dict(f.face)
    d['identity_id'] = f.identity.id
    return d


def pose_to_dict(f: Any) -> Dict:
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


def simple_result(result: Dict) -> Dict:
    return {
        'result': [{
            'type': 'flat',
            'elements': [r]
        } for r in result],
        'count': len(result),
    }


def filter_poses(ty, fn, used_kps, poses=None):
    filtered = []
    if poses is None:
        poses = Pose.objects.all().order_by('id').select_related('frame',
                                                                 'frame__video')[:100000:10]
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


def qs_to_result(result: QuerySet,
                 stride: int = 1,
                 group: bool = False,
                 shuffle: bool = False,
                 deterministic_order: bool = False,
                 custom_order_by_id: List[int] = None,
                 frame_major: bool = True,
                 show_count: bool = False,
                 limit: int = 100,
                 color: str = "red") -> Dict:

    count = result.count() if show_count else 0

    if shuffle:
        result = result.order_by('?')

    materialized_result = []
    cls = result.model
    bases = cls.__bases__
    if bases[0] is base_models.Frame:
        if custom_order_by_id is not None:
            result = sorted(result, key=lambda x: custom_order_by_id.index(x.id))
        elif not shuffle and deterministic_order:
            result = result.order_by('video', 'number')
        for frame in result[:limit * stride:stride]:
            materialized_result.append({
                'video': frame.video.id,
                'min_frame': frame.number,
                'objects': []
            })

    elif cls is Face or cls is FaceGender or cls is FaceIdentity or cls is Object:
        if cls is FaceGender or cls is FaceIdentity:
            frame_path = 'face__frame'
            if cls is FaceGender:
                result = result.select_related('face', 'gender')
            else:
                result = result.select_related('face', 'identity')
        else:
            frame_path = 'frame'
        result = result.select_related(frame_path)

        if not shuffle and deterministic_order:
            result = result.order_by(frame_path + '__video', frame_path + '__number')

        if cls is Face or cls is Object:
            fn = bbox_to_dict
        elif cls is FaceGender:
            fn = gender_to_dict
        elif cls is FaceIdentity:
            fn = identity_to_dict
        elif cls is Pose:
            fn = pose_to_dict

        if frame_major:
            frame_ids = set()

            def get_all_results():
                all_results = collect(
                    list(result.filter(**{frame_path + '__in': list(frame_ids)})),
                    lambda t: access(t, frame_path + '__id'))
                return all_results

            if custom_order_by_id is None:
                frames = set()
                for inst in list(
                        result.values(
                            frame_path + '__video', frame_path + '__number',
                            frame_path + '__id').annotate(m=F('id') % stride).filter(m=0)[:limit]):
                    frames.add((inst[frame_path + '__video'], inst[frame_path + '__number'],
                                inst[frame_path + '__id']))
                    frame_ids.add(inst[frame_path + '__id'])

                all_results = get_all_results()
                frames = list(frames)
                frames.sort(key=itemgetter(0, 1))

            else:
                frames = {}
                id_to_position = defaultdict(lambda: float('inf'))
                for i, id_ in enumerate(custom_order_by_id):
                    id_to_position[id_] = i
                for inst in list(
                        result.values(
                            'id', frame_path + '__video', frame_path + '__number',
                            frame_path + '__id').annotate(m=F('id') % stride).filter(m=0)):
                    frame_key = (inst[frame_path + '__video'], inst[frame_path + '__number'],
                                 inst[frame_path + '__id'])
                    frames[frame_key] = min(id_to_position[inst['id']], frames[frame_key]
                                            if frame_key in frames else float('inf'))
                    frame_ids.add(inst[frame_path + '__id'])
                all_results = get_all_results()
                frames = sorted([x for x in frames.items()], key=lambda x: x[1])
                frames = [x[0] for x in frames[:limit]]

            for (video, frame_num, frame_id) in frames:
                materialized_result.append({
                    'video': video,
                    'min_frame': frame_num,
                    'objects': [fn(inst) for inst in all_results[frame_id]]
                })


        else:
            for inst in result[:limit * stride:stride]:
                r = {
                    'video': inst.frame.video.id,
                    'min_frame': inst.frame.number,
                    'objects': [fn(inst)]
                }
                materialized_result.append(r)

    elif bases[0] is base_models.Track:
        if not shuffle and deterministic_order:
            result = result.order_by('video', 'min_frame')

        for t in result.annotate(duration=Track.duration_expr()).filter(duration__gt=0)[:limit]:
            result = {
                'video': t.video.id,
                'track': t.id,
                'min_frame': t.min_frame,
                'max_frame': t.max_frame,
            }
            if cls is Segment:
                result['things'] = [thing.id for thing in t.things.all()]

            materialized_result.append(result)
        if custom_order_by_id is not None:
            materialized_result.sort(key=lambda x: custom_order_by_id.index(x['track']))
        else:
            materialized_result.sort(key=itemgetter('video', 'min_frame'))

    elif bases[0] is base_models.Video:
        if custom_order_by_id is not None:
            raise NotImplementedError()

        if not shuffle and deterministic_order:
            result = result.order_by('id')

        for v in result[:limit]:
            materialized_result.append({'video': v.id, 'min_frame': 0})

    else:
        raise Exception("Unsupported class")

    ty_name = cls.__name__
    if group:
        by_video = collect(materialized_result, itemgetter('video'))
        videos = collect(Video.objects.filter(id__in=by_video.keys()).all(),
                attrgetter('id'))
        groups = [{
            'type': 'contiguous',
            'label': video,
            'num_frames': videos[video][0].num_frames,
            'elements': [{
                'video': video,
                'segments': sorted(by_video[video], key=itemgetter('min_frame')),
                'color': color
            }]
        } for video in sorted(by_video.keys())]
    else:
        groups = [{'type': 'flat', 'label': '', 'elements': [r]} for r in materialized_result]

    return {'result': groups, 'count': count, 'type': ty_name}


def group_results(agg_results):
    """List of tuples of the form (label, result)"""
    groups = []
    count = 0
    ty_name = None
    for label, result in agg_results:
        ty_name = result['type']
        count += result['count']
        elements = [x['elements'][0] for x in result['result']]
        groups.append({'type': 'flat', 'label': label, 'elements': elements})

    return {'result': groups, 'count': count, 'type': ty_name}


class _UnlabeledFace(object):
    @property
    def objects(self):
        labeled_ids = set(
            x['face__id']
            for x in FaceIdentity.objects.all().distinct('face__id').values('face__id'))
        return Face.objects.exclude(id__in=labeled_ids)


UnlabeledFace = _UnlabeledFace()


def esper_js_globals():
    import esper.queries.queries as queries

    def get_fields(cls):
        fields = cls._meta.get_fields()
        return [f.name for f in fields if isinstance(f, models.Field)]

    schema = []
    for m in django.apps.apps.get_models():
        schema.append([m.__name__, get_fields(m)])

    return {
        'bucket': BUCKET,
        'schema': schema,
        'queries': queries.queries,
    }


def result_with_metadata(result):
    video_ids = set()
    frame_ids = set()
    labeler_ids = set([Labeler.objects.get(name='handlabeled-face').id])
    gender_ids = set()
    for group in result['result']:
        for obj in group['elements']:
            video_ids.add(obj['video'])

            if 'segments' in obj:
                for segment in obj['segments']:
                    frame_ids.add(segment['min_frame'])
                    if 'max_frame' in segment:
                        frame_ids.add(segment['max_frame'])
            else:
                if 'min_time' in obj:
                    video = Video.objects.get(id=obj['video'])
                    obj['min_frame'] = int(obj['min_time'] * video.fps)

                    if 'max_time' in obj:
                        obj['max_frame'] = int(obj['max_time'] * video.fps)

                frame_ids.add(obj['min_frame'])
                if 'max_frame' in obj:
                    frame_ids.add(obj['max_frame'])

                if 'objects' in obj:
                    for bbox in obj['objects']:
                        if 'labeler_id' in bbox:
                            labeler_ids.add(bbox['labeler_id'])

                        if 'gender_id' in bbox:
                            gender_ids.add(bbox['gender_id'])

    def to_dict(qs):
        return {t['id']: t for t in list(qs.values())}

    videos = to_dict(Video.objects.filter(id__in=video_ids))
    frames = to_dict(Frame.objects.filter(id__in=frame_ids))
    labelers = to_dict(Labeler.objects.filter(id__in=labeler_ids))
    genders = to_dict(Gender.objects.all())
    topics = to_dict(Topic.objects.all())
    identities = to_dict(Identity.objects.all())

    return {
        'groups': result['result'],
        'tables': {
            'videos': videos,
            'frames': frames,
            'labelers': labelers,
        },
        'categories': {
            'genders': genders,
            'topics': topics,
            'identities': identities
        }
    }


def esper_widget(result, **kwargs):
    import vgrid_jupyter
    if not 'select_mode' in kwargs:
        kwargs['select_mode'] = 1
    if not 'disable_playback' in kwargs:
        kwargs['disable_playback'] = False
    return vgrid_jupyter.VGridWidget(
        result=result_with_metadata(result), jsglobals=esper_js_globals(), settings=kwargs)
