import scannerpy
from scannerpy.stdlib import kernel, writers
import tensorflow as tf
import align.detect_face
import cv2
from timeit import default_timer as now
import numpy as np

MODEL_DIR = '/app/deps/facenet/src/align'


class MTCNNKernel(kernel.TensorFlowKernel):
    def build_graph(self, sess):
        g = tf.Graph()
        g.as_default()
        print('Loading model...')
        self.pnet, self.rnet, self.onet = align.detect_face.create_mtcnn(self.sess, MODEL_DIR)
        print('Model loaded!')

    def execute(self, columns):
        threshold = [0.45, 0.6, 0.7]
        factor = 0.709
        vmargin = 0.2582651235637604
        hmargin = 0.3449094129917718
        out_size = 160
        detection_window_size_ratio = .2

        imgs = columns[0]
        print('Face detect on {} frames'.format(len(imgs)))
        start = now()
        detections = align.detect_face.bulk_detect_face(
            imgs, detection_window_size_ratio, self.pnet, self.rnet, self.onet, threshold, factor)

        batch_faces = []
        for img, bounding_boxes in zip(imgs, detections):
            if bounding_boxes == None:
                batch_faces.append([])
                continue
            frame_faces = []
            bounding_boxes = bounding_boxes[0]
            num_faces = bounding_boxes.shape[0]
            for i in range(num_faces):
                confidence = bounding_boxes[i][4]
                if confidence < .8:
                    continue

                img_size = np.asarray(img.shape)[0:2]
                det = np.squeeze(bounding_boxes[i][0:4])
                vmargin_pix = int((det[2] - det[0]) * vmargin)
                hmargin_pix = int((det[3] - det[1]) * hmargin)
                frame_faces.append(
                    self.protobufs.BoundingBox(
                        x1=np.maximum(det[0] - hmargin_pix / 2, 0),
                        y1=np.maximum(det[1] - vmargin_pix / 2, 0),
                        x2=np.minimum(det[2] + hmargin_pix / 2, img_size[1]),
                        y2=np.minimum(det[3] + vmargin_pix / 2, img_size[0])))

            batch_faces.append(frame_faces)

        return [[writers.bboxes([frame_faces], self.protobufs)[0] for frame_faces in batch_faces]]


KERNEL = MTCNNKernel
