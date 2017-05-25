from django.core.management.base import BaseCommand
from faceDB.face_db import FaceDB
from faceDB.face import FaceCluster
from faceDB.util import *   # only required for saving cluster images
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

class Command(BaseCommand):
    help = 'Cluster faces in videos'

    def add_arguments(self, parser):
        parser.add_argument('path')

    def handle(self, *args, **options):
        with open(options['path']) as f:
            paths = [s.strip() for s in f.readlines()]

        face_db = FaceDB(
            open_face_model_dir = '/usr/src/app/deps/openface/models',
            db_name = 'ignore',
            num_clusters = 10,
            cluster_algs = ['ignore'],
            verbose = False,
            merge_threshold=0.90)

        negative_imgs = load_imgs('./deps/face_recognizer/data/lfw')
        random.seed(1234)
        negative_imgs = random.sample(negative_imgs, 750)
        face_db.add_negative_features(negative_imgs)
        # TODO: test this when past clusters are present.

        # All the past clusters in the db.
        identities = Identity.objects.all()
        print("len of old identities = ", len(identities))
        clusters = {}

        # FIXME: face.features is a list. Need to store that properly in
        # django.
        for id in identities:
            faces = Face.objects.filter(identity=id)
            for face in faces:
                face.features = json.loads(face.features)
            assert len(faces[0].features) == 128, 'test'
            clusters[id.name] = FaceCluster(
                    id.name, faces, svm = id.classifier, merge_threshold=0.90)

        for path in paths:
            video = Video.objects.filter(path=path).get()
            faces = Face.objects.filter(video=video).all()
            faces = [f for f in faces if f.bbox.x2 - f.bbox.x1 >= 50]
            print("len of faces for {} is {}".format(path, len(faces)))
            imgs = ['./assets/thumbnails/{}_{}.jpg'.format(video.id, f.id)
                    for f in faces]

            (ids, added_clusters, fdb_faces), indices = \
                    face_db.add_detected_faces('test_vid', imgs, clusters)

            # All the ids where add_detected_faces failed to find faces
            # should just be deleted
            # FIXME: This messses up things.
            # for old_index, face in enumerate(faces):
                # if old_index not in indices:
                    # face.delete()
                    # os.remove(imgs[old_index])

            print("num of unaligned faces are: ", len(imgs) -
                    len(indices))

            for name, cluster in added_clusters.iteritems():
                id = Identity()
                id.name = name
                id.cohesion = cluster.cohesion_score or 0
                id.classifier = pickle.dumps(cluster.svm)
                id.save()

            for (name, index, fdb_face) in zip(ids, indices, fdb_faces):
                face = faces[index]
                assert len(fdb_face.features) == 128, 'features length'
                face.features = json.dumps(list(fdb_face.features))
                face.identity = Identity.objects.filter(name=name).get()
                face.save()
