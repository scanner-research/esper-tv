from django.shortcuts import render
from django.http import JsonResponse
from django.forms.models import model_to_dict
from models import *

def index(request):
    return render(request, 'index.html')

def videos(request):
    return JsonResponse({'videos': [model_to_dict(v) for v in Video.objects.all()]})
