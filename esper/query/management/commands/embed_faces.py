from django.core.management.base import BaseCommand
from query.models import Video, Face, Identity
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
        model_path = '/usr/src/app/deps/facenet/models/20170216-091149/'
        print model_path

        #load facenet models and start tensorflow
        out_size=160
        meta_file, ckpt_file = facenet.get_model_filenames(model_path)
        g = tf.Graph()
        g.as_default()
        sess = tf.Session()
        sess.as_default()
        saver = tf.train.import_meta_graph(os.path.join(model_path, meta_file))
        saver.restore(sess, os.path.join(model_path, ckpt_file))

        images_placeholder =  tf.get_default_graph().get_tensor_by_name('input:0')
        embeddings = tf.get_default_graph().get_tensor_by_name('embeddings:0')
        phase_train_placeholder =  tf.get_default_graph().get_tensor_by_name('phase_train:0')
        batch_size = 1000


        for path in paths:
            if path == '':
                return
            print path
            video = Video.objects.filter(path=path).get()
            faces = Face.objects.filter(video=video).all()
            faces = [f for f in faces if f.bbox.x2 - f.bbox.x1 >= 30]
            frames = [f.frame for f in faces]

            print len(faces)
            whitened_batch = []
            face_indexes = []
            #index in the face array NOT the face id
            for face_idx in range(len(faces)):
                curr_img = cv2.imread('./assets/thumbnails/{}_{}.jpg'.format(video.id, faces[face_idx].id))
                if curr_img is None:
                    continue
                face_indexes.append(face_idx)
                curr_img = cv2.resize(curr_img, (out_size, out_size))
                curr_img = facenet.prewhiten(curr_img)
                whitened_batch.append(curr_img)
                if len(whitened_batch) == batch_size:
                    print face_idx+1
                    feed_dict = {images_placeholder:whitened_batch, phase_train_placeholder:False}
                    embs = sess.run(embeddings, feed_dict=feed_dict)
                    for i in range(len(face_indexes)):
                        faces[face_indexes[i]].features = json.dumps(embs[i].tolist())
                        faces[face_indexes[i]].save()
                    #reset for the next batch
                    first_face_idx = face_idx+1
                    whitened_batch = []
                    face_indexes = []
            if len(whitened_batch) > 0:
                feed_dict = {images_placeholder:whitened_batch, phase_train_placeholder:False}
                embs = sess.run(embeddings, feed_dict=feed_dict)
                for i in range(len(face_indexes)):
                    faces[face_indexes[i]].feature = json.dumps(embs[i].tolist())
                    faces[face_indexes[i]].save()
