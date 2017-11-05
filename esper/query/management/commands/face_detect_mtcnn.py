from django.core.management.base import BaseCommand
from query.models import Video, Face, Frame
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

    def detect_faces_batch(self, frame_ids, batch, minsize, pnet, rnet, onet, threshold, factor, vmargin, hmargin, video, frame_map):
        detections = align.detect_face.bulk_detect_face(batch, minsize, pnet, rnet, onet, threshold, factor)
        face_obj_batch = []
        print(len(frame_ids))
        for (frame_id, bounding_boxes, img) in zip(frame_ids, detections, batch):
            
            if bounding_boxes == None:
                continue
            bounding_boxes = bounding_boxes[0]
            num_faces = bounding_boxes.shape[0]
            for i in range(num_faces):
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
                if confidence < .8:
                    continue
                normalized_bbox = proto.BoundingBox()
                
                normalized_bbox.score = confidence
                normalized_bbox.x1 = bb[0]/float(video.width)
                normalized_bbox.x2 = bb[2]/float(video.width)
                normalized_bbox.y1 = bb[1]/float(video.height)
                normalized_bbox.y2 = bb[3]/float(video.height)

                if (normalized_bbox.x2-normalized_bbox.x1 < 0.04):
                    continue

                f = Face()
                f.labeler = mtcnn_labeler
                f.frame = frame_map[frame_id] 
                f.bbox = normalized_bbox
                f.bbox_x1 = bb[0]/float(video.width)
                f.bbox_x2 = bb[2]/float(video.width)
                f.bbox_y1 = bb[1]/float(video.height)
                f.bbox_y2 = bb[3]/float(video.height)
                f.bbox_score = confidence 

                face_obj_batch.append(f)
        Face.objects.bulk_create(face_obj_batch)
            

    def handle(self, *args, **options):
        with open(options['path']) as f:
            paths = [s.strip() for s in f.readlines()]

        # Only run the detector over videos we haven't yet processed
        filtered = []
        for path in paths:
            video = Video.objects.filter(path=path)
            if len(video) == 0: continue
            video = video[0]
            if Face.objects.filter(frame__video=video).count() == 0:
                break

        # Run the detector via Scanner
        threshold = [0.45, 0.6, 0.7]
        factor = 0.709
        vmargin = 0.2582651235637604
        hmargin = 0.3449094129917718
        out_size = 160
        minsize = 20
        batchsize = 200 

        g1 = tf.Graph()
        g1.as_default()
        sess1 = tf.Session(config=tf.ConfigProto(log_device_placement=False))
        sess1.as_default()
        pnet, rnet, onet = align.detect_face.create_mtcnn(sess1, None)

        # Save the results to the database
        for path in paths:
            video = Video.objects.filter(path=path).get()
            max_frame = video.num_frames
            stride = int(math.ceil(video.fps)/2)

            frames = Frame.objects.filter(video=video)
            frame_map = {}

            for frame in frames:
                frame_map[frame.number] = frame

            batch_images = []
            frame_ids = []
            for frame_id in range(0, max_frame, stride):
                #invid.set(cv2.CAP_PROP_POS_FRAMES, frame_id)
                #retval, img = invid.read()
                #if retval==False:
                #    break
                img = cv2.imread("assets/thumbnails/{}/frame_{}.jpg".format(os.environ['DATASET'], frame_map[frame_id].id))
                assert img is not None
                batch_images.append(img)
                frame_ids.append(frame_id)
                if len(batch_images) == batchsize:
                    self.detect_faces_batch(frame_ids, batch_images, minsize, pnet, rnet, onet, threshold, factor, vmargin, hmargin, video, frame_map)
                    batch_images = []
                    frame_ids = []
                #print frame_id

            if len(frame_ids) > 0:
                self.detect_faces_batch(frame_ids, batch_images, minsize, pnet, rnet, onet, threshold, factor,  vmargin, hmargin, video, frame_map)
