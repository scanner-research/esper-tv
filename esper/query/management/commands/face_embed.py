from django.core.management.base import BaseCommand
from query.models import Video, Face, Identity
from faceDB.open_face_helper import OpenFaceHelper
import random
import json
import tensorflow as tf
import facenet
import cv2
import os


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
    help = 'Cluster faces in videos'

    def add_arguments(self, parser):
        parser.add_argument('path')

    def handle(self, *args, **options):
        with open(options['path']) as f:
            paths = [s.strip() for s in f.readlines()]
        model_path = '/usr/src/app/deps/openface/models'
        of = OpenFaceHelper(model_path)
        print model_path

        #load facenet models and start tensorflow
        out_size=160


        batch_size = 1000


        for path in paths:
            if path == '':
                return
            print path
            video = Video.objects.filter(path=path).get()
            faces = Face.objects.filter(video=video).all()
            faces = [f for f in faces if f.bbox.x2 - f.bbox.x1 >= 30]
            print len(faces)
            #index in the face array NOT the face id
            for face_idx in range(len(faces)):
                curr_face = faces[face_idx]
                curr_img_path = './assets/thumbnails/{}_{}.jpg'.format(video.id, curr_face.id)
                try:
                    rep = of.get_rep(curr_img_path)
                except Exception:
                    continue
                curr_face.features=json.dumps(rep.tolist())
                curr_face.save()
                if (face_idx + 1) % 100 == 0:
                    print face_idx


                
