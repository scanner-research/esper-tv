from django.shortcuts import render
from django.http import JsonResponse
from django.forms.models import model_to_dict
from models import *
from timeit import default_timer as now

def index(request):
    return render(request, 'index.html')

def videos(request):
    return JsonResponse({'videos': [model_to_dict(v) for v in Video.objects.all()]})

def faces(request):
    t = now()
    id = request.GET.get('id', None)
    video = Video.objects.filter(id=id).get()
    bboxes = [[] for _ in range(video.num_frames)]
    faces = Face.objects.filter(video=video)
    for face in faces:
        bbox = [int(face.bbox.x1), int(face.bbox.y1),
                int(face.bbox.x2), int(face.bbox.y2)]
        bboxes[face.frame].append(bbox);
    return JsonResponse({'faces': bboxes})
