from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count
from django.forms.models import model_to_dict
from query.models import *
import numpy as np

class Command(BaseCommand):
    help = 'Run a script'

    def handle(self, *args, **options):
        videos = Video.objects.annotate(Count('face'))
        for video in videos:
            num_faces = video.face__count
            frame_counts = np.zeros((video.num_frames))
            for face in Face.objects.filter(video=video):
                frame_counts[face.frame] += 1
            print np.mean(frame_counts), np.std(frame_counts)
