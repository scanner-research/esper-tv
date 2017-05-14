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
    return JsonResponse({'videos': [model_to_dict(v) for v in Video.objects.all()]})

def faces(request, video_id):
    t = now()
    if video_id is None:
        return JsonResponse({}) # TODO
    video = Video.objects.filter(id=video_id).get()
    bboxes = defaultdict(list)
    faces = Face.objects.filter(video=video).all()
    for face in faces:
        bbox = json.loads(MessageToJson(face.bbox))
        face_json = model_to_dict(face)
        face_json['bbox'] = bbox
        bboxes[face.frame].append(face_json);
    return JsonResponse({'faces': bboxes})
