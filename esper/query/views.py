from django.shortcuts import render
from django.http import JsonResponse
from django.forms.models import model_to_dict
from models import *
from timeit import default_timer as now
import sys
from google.protobuf.json_format import MessageToJson
import json
from collections import defaultdict
from scannerpy import Database

def index(request):
    return render(request, 'index.html')

def videos(request):
    id = request.GET.get('id', None)
    if id is None:
        videos = Video.objects.all()
    else:
        videos = [Video.objects.filter(id=id).get()]
    return JsonResponse({'videos': [model_to_dict(v) for v in videos]})

def frames(request):
    video_id = request.GET.get('video_id', None)
    handlabeled = request.GET.get('video_id', False)
    video = Video.objects.filter(id=video_id).get()
    labelset = video.handlabeled_labelset() if handlabeled else video.detected_labelset()
    return JsonResponse({
        'frames':[model_to_dict(f) for f in Frame.objects.filter(labelset=labelset)]
    })

def faces(request):
    video_id = request.GET.get('video_id', None)
    if video_id is None:
        return JsonResponse({}) # TODO
    video = Video.objects.filter(id=video_id).get()
    labelset = video.detected_labelset()
    bboxes = defaultdict(list)
    faces = Face.objects.filter(frame__labelset=labelset).all()
    for face in faces:
        bbox = json.loads(MessageToJson(face.bbox))
        face_json = model_to_dict(face)
        print face_json
        del face_json['features']
        face_json['bbox'] = bbox
        bboxes[face.frame.number].append(face_json);
    return JsonResponse({'faces': bboxes})

def identities(request):
    # FIXME: Should we be sending faces for each identity too?
    # FIXME: How do I see output of this when calling from js?
    identities = Identity.objects.all()
    return JsonResponse({'ids': [model_to_dict(id) for id in identities]})

def handlabeled(request):
    params = json.loads(request.body)
    video = Video.objects.filter(id=params['video']).get()
    labelset = video.handlabeled_labelset()
    for frame_num, faces in params['faces'].iteritems():
        frame = Frame(labelset=labelset, number=frame_num)
        frame.save()

        for face_params in faces:
            with Database() as db:
                # gross, there should be a better way than this
                bbox = db.protobufs.BoundingBox()
            bbox.x1 = face_params['bbox']['x1']
            bbox.y1 = face_params['bbox']['y1']
            bbox.x2 = face_params['bbox']['x2']
            bbox.y2 = face_params['bbox']['y2']
            face_params['bbox'] = bbox
            face = Face(**face_params)
            face.frame = frame
            face.save()

    return JsonResponse({'success': True})
