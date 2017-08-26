from django.shortcuts import render
from django.http import JsonResponse
from django.forms.models import model_to_dict
from models import *
from timeit import default_timer as now
import sys
from google.protobuf.json_format import MessageToJson
import json
from collections import defaultdict
from scannerpy import Config
from django.db import connection
import logging
import time
import django.db.models as models
import math

logger = logging.getLogger(__name__)

# TODO(wcrichto): find a better way to do this
Config()
from scanner.types_pb2 import BoundingBox

DIFF_BBOX_THRESHOLD = 0.35
# 24 frames/sec - so this requires more than a sec overlap
FRAME_OVERLAP_THRESHOLD = 25

def index(request):
    return render(request, 'index.html')


def videos(request):
    id = request.GET.get('id', None)
    if id is None:
        videos = Video.objects.all()
    else:
        videos = [Video.objects.filter(id=id).get()]
    return JsonResponse({
        'videos':
        [dict(model_to_dict(v).items() + {'stride': v.get_stride()}.items()) for v in videos]
    })


def frames(request):
    video_id = request.GET.get('video_id', None)
    handlabeled = request.GET.get('video_id', False)
    video = Video.objects.filter(id=video_id).get()
    labelset = video.handlabeled_labelset() if handlabeled else video.detected_labelset()
    resp = JsonResponse({
        'frames':[dict(model_to_dict(f, exclude='labels').items() + {'labels' : f.label_ids()}.items()) \
                for f in Frame.objects.filter(labelset=labelset).prefetch_related('labels').all()] ,
        'labels':[model_to_dict(s) for s in FrameLabel.objects.all()]
    })
    return resp


def frame_and_faces(request):
    video_id = request.GET.get('video_id', None)
    video = Video.objects.filter(id=video_id).prefetch_related('labelset_set').get()
    labelsets = video.labelset_set.all()
    frame_and_face_dict = {}
    ret_dict = {}
    for ls in labelsets:
        frames = Frame.objects.filter(labelset=ls).prefetch_related(
            'faces', 'labels').order_by('number').all()
        ls_dict = {}
        for frame in frames:
            frame_dict = {}
            frame_dict['labels'] = frame.label_ids()
            faces = frame.faces.all()
            face_list = []
            for face in faces:
                bbox = json.loads(MessageToJson(face.bbox))
                face_json = model_to_dict(face)
                del face_json['features']
                face_json['bbox'] = bbox
                face_list.append(face_json)
            frame_dict['faces'] = face_list
            ls_dict[frame.number] = frame_dict
        frame_and_face_dict[2 if ls.name == 'handlabeled' else 1] = ls_dict
    ret_dict['frames'] = frame_and_face_dict
    frame_labels = FrameLabel.objects.all()
    label_dict = {}
    for label in frame_labels:
        label_dict[label.id] = label.name
    ret_dict['labels'] = label_dict
    return JsonResponse(ret_dict)


def faces(request):
    video_id = request.GET.get('video_id', None)
    if video_id is None:
        return JsonResponse({})  # TODO
    video = Video.objects.filter(id=video_id).get()
    labelsets = LabelSet.objects.filter(video=video)
    all_bboxes = {}
    for labelset in labelsets:
        bboxes = defaultdict(list)
        faces = Face.objects.filter(frame__labelset=labelset).select_related('frame').all()
        for face in faces:
            bbox = json.loads(MessageToJson(face.bbox))
            face_json = model_to_dict(face)
            del face_json['features']
            face_json['bbox'] = bbox
            bboxes[face.frame.number].append(face_json)
        # 1 is Autolabeled 2 is handlabled ugly but works until
        # we use something more than a string in the model
        set_id = 1 if labelset.name == 'detected' else 2
        all_bboxes[set_id] = bboxes
    return JsonResponse({'faces': all_bboxes})


def identities(request):
    # FIXME: Should we be sending faces for each identity too?
    # FIXME: How do I see output of this when calling from js?
    identities = Identity.objects.all()
    return JsonResponse({'ids': [model_to_dict(id) for id in identities]})


def handlabeled(request):
    params = json.loads(request.body)
    video = Video.objects.filter(id=params['video']).get()
    labelset = video.handlabeled_labelset()
    frame_nums = map(int, params['frames'].keys())

    min_frame = min(frame_nums)
    max_frame = max(frame_nums)
    #old frames, create new_frames
    old_frames = Frame.objects.filter(
        labelset=labelset, number__lte=max_frame, number__gte=min_frame).all()
    labelsModel = Frame.labels.through
    if len(old_frames) > 0:
        Face.objects.filter(frame__in=old_frames).delete()
        labelsModel.objects.filter(frame__in=old_frames).delete()

    old_frame_nums = [old_frame.number for old_frame in old_frames]
    missing_frame_nums = [num for num in frame_nums if num not in old_frame_nums]
    new_frames = [Frame(labelset=labelset, number=num) for num in missing_frame_nums]
    Frame.objects.bulk_create(new_frames)
    tracks = defaultdict(list)
    for frame_num, frames in params['frames'].iteritems():
        for face_params in frames['faces']:
            track_id = face_params['track']
            if track_id is not None:
                tracks[track_id].append(frame_num)

    id_to_track = {}
    all_frames = Frame.objects.filter(
        labelset=labelset, number__lte=max_frame, number__gte=min_frame).all()
    curr_video_tracks = Track.objects.filter(video=video).all()
    for track in curr_video_tracks:
        id_to_track[track.id] = track
    for track_id, frames in tracks.iteritems():
        if track_id < 0:
            track = Track(video=video)
            track.save()
            id_to_track[track_id] = track

    new_faces = []
    new_labels = []
    for frame in all_frames:
        for face_params in params['frames'][str(frame.number)]['faces']:
            bbox = BoundingBox()
            bbox.x1 = face_params['bbox']['x1']
            bbox.y1 = face_params['bbox']['y1']
            bbox.x2 = face_params['bbox']['x2']
            bbox.y2 = face_params['bbox']['y2']
            face_params['bbox'] = bbox
            track_id = face_params['track']
            if track_id is not None:
                face_params['track'] = id_to_track[track_id]
            face = Face(**face_params)
            face.frame = frame
            new_faces.append(face)
        for label_id in params['frames'][str(frame.number)]['labels']:
            new_labels.append(labelsModel(frame=frame, framelabel_id=int(label_id)))

    Face.objects.bulk_create(new_faces)
    labelsModel.objects.bulk_create(new_labels)

    return JsonResponse({'success': True})

def _overlap(a, b):
    '''
    @a, b: are ranges with start/end as a[0], a[1]
    '''
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))

def _bbox_dist(bbox1, bbox2):
    return math.sqrt((bbox2.x1 - bbox1.x1)**2 + (bbox2.x2 - bbox1.x2)**2 + (bbox2.y1 - bbox1.y2)**2 \
                      + (bbox2.y2 - bbox1.y2)**2)

def _get_face_min_frames(labeler='tinyfaces'):
    '''
    @labeler: str, name of labeler.
    There can be multiple Face concepts refering to the same face track - so select the ones from a
    particular labeler.
    @ret: dict, with keys id, min_frame, max_frame.
    '''
    return Face.objects.filter(labeler__name=labeler) \
    .values('id').annotate(min_frame=models.Min('faceinstance__frame__number'),
        max_frame=models.Max('faceinstance__frame__number'))

def _get_face_query(min_frame_numbers):
    '''
    @min_frame_numebers:
    '''
    # TODO: can generalize this more by taking in args for each of the values, and labeler etc. But
    # for now, don't have a use case for that. Maybe we can also use str formating to construct
    # these queries / and then eval them?
    return [Face.objects.filter(id=f['id'],
            faceinstance__frame__number=f['min_frame']).values(
            'id', 'faceinstance__frame__id', 'faceinstance__frame__video__id',
            'faceinstance__bbox').get() for f in min_frame_numbers if
            f['min_frame'] is not None]

def _get_face_clips(results):
    '''
    @results: zipped value having results, min_frame_numbers (as returned from
    _get_face_query, and _get_face_min_frames).
    @ret: dict
    '''
    clips = defaultdict(list)
    for result, f in results:
        clips[result['faceinstance__frame__video__id']].append({
            'concept':
            result['id'],
            'frame':
            result['faceinstance__frame__id'],
            'start':
            f['min_frame'],
            'end':
            f['max_frame'],
            'bboxes': [json.loads(MessageToJson(result['faceinstance__bbox']))]
        })

    return dict(clips)

def _get_face_label_mismatches(result1, result2, mistakes, overlaps=[]):

    # keep track of overlaps being added now - so does not modify the passed in overlaps
    cur_overlaps = []
    for i, (result, f) in enumerate(result1):
        # this check is useful for the scenario when we do an outer loop over results2, can
        # avoid the samples that have already been considered.
        if i in overlaps:
            continue
        mistake = True
        bbox = result['faceinstance__bbox']

        for j, (result2, f2) in enumerate(result2):
            if f2['min_frame'] > f['max_frame'] or f2['max_frame'] < f['min_frame']:
                continue

            # first check if the frames overlap - as the two labelers might have marked
            # frames differently
            a = (f['min_frame'], f['max_frame'])
            b = (f2['min_frame'], f2['max_frame'])
            o = _overlap(a,b)
            if _overlap(a,b) > FRAME_OVERLAP_THRESHOLD:
                # we don't want same frame to be considered when looping over result2
                # first.
                cur_overlaps.append(j)
                # frames overlap, now check if bboxes are close enough.
                if _bbox_dist(bbox, result2['faceinstance__bbox']) < DIFF_BBOX_THRESHOLD:
                    mistake = False
                else:
                    mistake = True
                    # add it to mistakes
                    mistakes.append((result2, f2))
                    break

        if mistake:
            mistakes.append((result, f))
        return cur_overlaps

def search(request):
    concept = request.GET.get('concept')
    # TODO(wcrichto): Unify video and face cases?
    # TODO(wcrichto): figure out stupid fucking groupwise aggregation issue. Right now we're
    # an individual query for every concept, which is a Bad Idea.

    # TODO (pari): remove the logging stuff
    if concept == 'video':
        min_frame_numbers = Video.objects.values('id').annotate(
            min_frame=models.Min('frame__number'), max_frame=models.Max('frame__number'))
        qs = [
            Video.objects.filter(id=f['id'], frame__number=f['min_frame']).distinct().values(
                'id', 'frame__id').get() for f in min_frame_numbers
        ]
        clips = defaultdict(list)
        for result, f in zip(qs, min_frame_numbers):
            clips[result['id']].append({
                'frame': result['frame__id'],
                'bboxes': [],
                'start': f['min_frame'],
                'end': f['max_frame']
            })
        clips = dict(clips)

    elif concept == 'face':
        # otherwise this list would also include Faces from other labelers.
        min_frame_numbers = _get_face_min_frames(labeler='tinyfaces')
        qs = _get_face_query(min_frame_numbers)

        print qs
        sys.stdout.flush()
        clips = _get_face_clips(zip(qs, min_frame_numbers))

    # Mismatched labels.
    elif concept == 'face_diffs':
        min_frame_numbers = _get_face_min_frames(labeler='tinyfaces')
        min_frame_numbers2 = _get_face_min_frames(labeler='dummy')

        qs = _get_face_query(min_frame_numbers)
        qs2 = _get_face_query(min_frame_numbers2)

        mistakes = []
        overlaps = _get_face_label_mismatches(zip(qs, min_frame_numbers), zip(qs2, min_frame_numbers2),
                    mistakes)
        _ = _get_face_label_mismatches(zip(qs2, min_frame_numbers2), zip(qs, min_frame_numbers),
                mistakes, overlaps=overlaps)
        clips = _get_face_clips(mistakes)

    videos = {v.id: model_to_dict(v) for v in Video.objects.filter(pk__in=clips.keys())}

    return JsonResponse({'clips': clips, 'videos': videos})
