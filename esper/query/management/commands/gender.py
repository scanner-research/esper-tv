from django.core.management.base import BaseCommand
from faceDB.face_db import FaceDB
from faceDB.face import FaceCluster
from faceDB.util import *   # only required for saving cluster images
from carnie_helper import RudeCarnie
from query.models import Video, Face, Identity
import random
import json

def load_imgs(img_directory):
    imgs = []
    for root, subdirs, files in os.walk(img_directory):
        for file in files:
            if os.path.splitext(file)[1].lower() in ('.jpg', '.jpeg'):
                path = os.path.join(root, file)
                imgs.append(path)

    return imgs

# FIXME: Exit gracefully if same images being sent to clustering algorithm a
# second time...

class Command(BaseCommand):
    help = 'Find genders for all the detected faces'

    def add_arguments(self, parser):
        parser.add_argument('path')

    def handle(self, *args, **options):
        with open(options['path']) as f:
            paths = [s.strip() for s in f.readlines()]

        model_dir = '/usr/src/app/deps/rude-carnie/inception_gender_checkpoint'
        for i, path in enumerate(paths):
            confident = 0
            if path == '':
                return

            rc = RudeCarnie(model_dir=model_dir)
            video = Video.objects.filter(path=path).get()
            faces = Face.objects.filter(video=video).all()
            print("len of faces for path {}, is {}".format(path, len(faces)))
            faces = [f for f in faces if f.bbox.x2 - f.bbox.x1 >= 50]
            imgs = ['./assets/thumbnails/{}_{}.jpg'.format(video.id, f.id)
                    for f in faces]
            best = rc.get_gender(imgs, single_look=True)
            for comb in zip(imgs, best):
                print('{} : {}'.format(comb[0], comb[1]))

            # Update each of the faces.
            for i, face in enumerate(faces):
                if best[i] is None:
                    # couldn't get gender output for some reason
                    continue
                if best[i][1] < 0.90:
                    # gender detector not confident.
                    face.gender = 'U'
                else:
                    face.gender = best[i][0]
                    confident += 1

                face.save()

            print('confident = {}, not confident = {}'.format(confident,
                len(faces)-confident))
