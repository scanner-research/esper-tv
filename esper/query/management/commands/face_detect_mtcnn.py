from django.core.management.base import BaseCommand
from query.models import Video, Face, LabelSet
from scannerpy import ProtobufGenerator, Config
import os
import cv2
import math
import numpy as np
import tensorflow as tf
import align.detect_face

cfg = Config()
proto = ProtobufGenerator(cfg)

class Command(BaseCommand):
    help = 'Detect faces in videos'

    def add_arguments(self, parser):
        parser.add_argument('path')

    def handle(self, *args, **options):
        with open(options['path']) as f:
            paths = [s.strip() for s in f.readlines()]

        # Only run the detector over videos we haven't yet processed
        filtered = []
        for path in paths:
            video = Video.objects.filter(path=path)
            if len(video) == 0: continue
            video = video[0]
            if len(LabelSet.objects.all()) == 0:
                break
            labelset = video.detected_labelset()
            if len(Face.objects.filter(labelset=labelset)) > 0: continue
            filtered.append(path)

        # Run the detector via Scanner
        threshold = [0.45, 0.6, 0.7]
        factor = 0.709
        vmargin = 0.2582651235637604
        hmargin = 0.3449094129917718
        out_size = 160
        minsize = 20

        g1 = tf.Graph()
        g1.as_default()
        sess1 = tf.Session(config=tf.ConfigProto(log_device_placement=False))
        sess1.as_default()
        pnet, rnet, onet = align.detect_face.create_mtcnn(sess1, None)

        # Save the results to the database
        for path in paths:
            video = Video.objects.filter(path=path).get()
            labelset = LabelSet()
            labelset.name = "detected"
            labelset.video = video
            labelset.save()
            print path
            invid = cv2.VideoCapture(path)
            max_frame = int(invid.get(cv2.CAP_PROP_FRAME_COUNT))
            stride = int(math.ceil(video.fps)/3)
            print stride

            
            for frame_id in range(0, max_frame, stride):
                invid.set(cv2.CAP_PROP_POS_FRAMES, frame_id)
                retval, img = invid.read()
                if retval==False:
                    break
                bounding_boxes, _ = align.detect_face.detect_face(img, minsize, pnet, rnet, onet, threshold, factor)
                num_faces = bounding_boxes.shape[0]
                for i in range(num_faces):
                    f = Face()
                    f.labelset = labelset
                    f.frame = frame_id
                    det = bounding_boxes[i][0:4]
                    confidence = bounding_boxes[i][4]
                    img_size = np.asarray(img.shape)[0:2]
                    det = np.squeeze(det)
                    bb = np.zeros(4, dtype=np.int32)
                    vmargin_pix = int((det[2]-det[0])*vmargin)
                    hmargin_pix = int((det[3]-det[1])*hmargin)
                    bb[0] = np.maximum(det[0]-hmargin_pix/2, 0)
                    bb[1] = np.maximum(det[1]-vmargin_pix/2, 0)
                    bb[2] = np.minimum(det[2]+hmargin_pix/2, img_size[1])
                    bb[3] = np.minimum(det[3]+vmargin_pix/2, img_size[0])

                    bbox = proto.BoundingBox()
                    
                    bbox.score = confidence
                    bbox.x1 = bb[0]
                    bbox.x2 = bb[2]
                    bbox.y1 = bb[1]
                    bbox.y2 = bb[3]

                    f.bbox = bbox
                    f.save()

                    cropped = img[bb[1]:bb[3],bb[0]:bb[2],:]
                    thumbnail_path = 'assets/thumbnails/{}_{}.jpg'.format(labelset.id, f.id)
                    cv2.imwrite(thumbnail_path, cropped)
                print frame_id
