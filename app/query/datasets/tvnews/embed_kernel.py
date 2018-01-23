import scannerpy
from scannerpy.stdlib import kernel, parsers
import tensorflow as tf
import facenet
import cv2
import json
import os
import numpy as np

model_path = '/app/deps/facenet/models/20170512-110547/'


class EmbedFaceKernel(kernel.TensorFlowKernel):
    def build_graph(self, sess):
        meta_file, ckpt_file = facenet.get_model_filenames(model_path)
        g = tf.Graph()
        g.as_default()
        saver = tf.train.import_meta_graph(os.path.join(model_path, meta_file))
        saver.restore(sess, os.path.join(model_path, ckpt_file))

        self.images_placeholder = tf.get_default_graph().get_tensor_by_name('input:0')
        self.embeddings = tf.get_default_graph().get_tensor_by_name('embeddings:0')
        self.phase_train_placeholder = tf.get_default_graph().get_tensor_by_name('phase_train:0')

    def execute(self, columns):
        [img, bboxes] = columns
        [h, w] = img.shape[:2]

        # TODO(wcrichto): make this batched

        out_size = 160
        bboxes = parsers.bboxes(bboxes, self.protobufs)
        outputs = ''
        for bbox in bboxes:
            # NOTE: if using output of mtcnn, not-normalized, so removing de-normalization factors here
            face_img = img[int(bbox.y1):int(bbox.y2), int(bbox.x1):int(bbox.x2)]
            [fh, fw] = face_img.shape[:2]
            if fh == 0 or fw == 0:
                outputs += np.zeros(128, dtype=np.float32).tobytes()
            else:
                face_img = cv2.resize(face_img, (out_size, out_size))
                face_img = facenet.prewhiten(face_img)
                embs = self.sess.run(
                    self.embeddings,
                    feed_dict={
                        self.images_placeholder: [face_img],
                        self.phase_train_placeholder: False
                    })

                outputs += embs[0].tobytes()

        return [outputs]


KERNEL = EmbedFaceKernel
