from django.core.management.base import BaseCommand
from faceDB.face_db import FaceDB
from faceDB.face import FaceCluster
from faceDB.util import *   # only required for saving cluster images
from carnie_helper import RudeCarnie
from query.models import *
import random
import json

class Command(BaseCommand):
    help = 'Find genders for all the detected faces'

    def add_arguments(self, parser):
        parser.add_argument('path')

    def handle_video(self, path, rude_carnie):
        print(path)
        video = Video.objects.filter(path=path).get()
        labelset = video.detected_labelset()
        faces = Face.objects.filter(frame__labelset=labelset).all()
        faces = [f for f in faces if f.gender == '0']
        print((len(faces)))
        
        imgs = ['./assets/thumbnails/{}_{}.png'.format(labelset.id, f.id) for f in faces]
        male_ids = []
        female_ids = []
        if len(imgs) == 0:
            return
        genders = rude_carnie.get_gender_batch(imgs)
        for face, gender in zip(faces, genders):
            if gender[0] == 'M':
                male_ids.append(face.id)
            elif gender[0] == 'F':
                female_ids.append(face.id)
        Face.objects.filter(id__in=male_ids).update(gender='M')
        Face.objects.filter(id__in=female_ids).update(gender='F')


    def handle(self, *args, **options):
        with open(options['path']) as f:
            paths = [s.strip() for s in f.readlines()]

        model_dir = '/app/deps/rude-carnie/inception_gender_checkpoint'
        rc = RudeCarnie(model_dir=model_dir)

        for path in paths:
            self.handle_video(path, rc)


