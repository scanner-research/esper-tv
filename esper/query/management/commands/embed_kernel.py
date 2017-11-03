import scannerpy
from scannerpy.stdlib import pykernel, parsers
import tensorflow as tf
import facenet
import cv2
import json

model_path = '/app/deps/facenet/models/20170512-110547/'

class TensorFlowKernel:
    def __init__(self, config, protobufs):
        # TODO: wrap this in "with device"
        config = tf.ConfigProto(allow_soft_placement = True)
        self.sess = tf.Session(config=config)
        self.graph = self.build_graph(self.sess)
        self.protobufs = protobufs

    def close(self):
        self.sess.close()

    def build_graph(self):
        raise NotImplementedError

    def execute(self):
        raise NotImplementedError

class EmbedFaceKernel(TensorFlowKernel):

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

        out_size = 160
        bboxes = parsers.bboxes(bboxes, self.protobufs)
        outputs = ''
        for bbox in bboxes:
            face_img = img[int(h*bbox.y1):int(h*bbox.y2), int(w*bbox.x1):int(w*bbox.x2)]
            face_img = cv2.resize(face_img, (out_size, out_size))
            face_img = facenet.prewhiten(face_img)
            embs = self.sess.run(self.embeddings, feed_dict={
                self.images_placeholder: [face_img],
                self.phase_train_placeholder: False})

            outputs += embs[0].tobytes()

        return [outputs]

KERNEL = EmbedFaceKernel
