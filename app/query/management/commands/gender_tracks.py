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

    def handle(self, *args, **options):
        with open(options['path']) as f:
            paths = [s.strip() for s in f.readlines()]

        model_dir = '/app/deps/rude-carnie/inception_gender_checkpoint'
        rc = RudeCarnie(model_dir=model_dir)

        for path in paths:
            confident = 0
            if path == '':
                return
            video = Video.objects.filter(path=path).get()
            labelset = video.detected_labelset()
            tracks = Track.objects.filter(first_frame__labelset=labelset).all()

            for track in tracks:
                if track.gender != '0':
                    print(('skipping_track', track.id))
                    continue
                faces = Face.objects.filter(track=track)
                print((track.id))

                print(("len of faces for path {}, is {}".format(path, len(faces))))
                imgs = ['./assets/thumbnails/{}_{}.jpg'.format(labelset.id, f.id)
                        for f in faces]

                best = rc.get_gender(imgs)

                # Update each of the faces.
                male_sum = 0.0
                female_sum = 0.0
                for i, face in enumerate(faces):
                    if best[i] is None:
                        # couldn't get gender output for some reason
                        continue
                    if best[i][0] == 'M':
                        male_sum += best[i][1]
                    elif best[i][0] == 'F':
                        female_sum += best[i][1]
                track.gender = 'M' if male_sum>female_sum else 'F'
                track.save()
