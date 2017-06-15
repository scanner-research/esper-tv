from django.shortcuts import render
from django.http import JsonResponse
from django.forms.models import model_to_dict
from models import *
from timeit import default_timer as now
import sys
from google.protobuf.json_format import MessageToJson
import json
from collections import defaultdict

def index(request):
    return render(request, 'index.html')

def videos(request):
    id = request.GET.get('id', None)
    if id is None:
        videos = Video.objects.all()
    else:
        videos = [Video.objects.filter(id=id).get()]
    return JsonResponse({'videos': [model_to_dict(v) for v in videos]})

def faces(request):
    t = now()
    video_id = request.GET.get('video_id', None)
    if video_id is None:
        return JsonResponse({}) # TODO
    video = Video.objects.filter(id=video_id).get()
    bboxes = defaultdict(list)
    faces = Face.objects.filter(video=video).all()
    for face in faces:
        bbox = json.loads(MessageToJson(face.bbox))
        face_json = model_to_dict(face)
        del face_json['features']
        face_json['bbox'] = bbox
        bboxes[face.frame].append(face_json);
    return JsonResponse({'faces': bboxes})

def identities(request):
    # FIXME: Should we be sending faces for each identity too?
    # FIXME: How do I see output of this when calling from js?
    identities = Identity.objects.all()
    return JsonResponse({'ids': [model_to_dict(id) for id in identities]})
