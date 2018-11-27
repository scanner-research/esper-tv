import os
import json
import shutil
import cv2
import sys
import math
# import tensorflow as tf
import numpy as np
# import align.detect_face
# import facenet
import requests
import tempfile
import _pickle as pickle
import urllib.request as request
from collections import namedtuple
from google_images_download import google_images_download

DATA_DIR = '/app/data'

TMP_DOWNLOAD_DIR = '/tmp/google_img_download'
if not os.path.exists(TMP_DOWNLOAD_DIR):
    os.makedirs(TMP_DOWNLOAD_DIR)

IMG_CACHE_DIR = '/app/data/google_images'
if not os.path.exists(IMG_CACHE_DIR):
    os.makedirs(IMG_CACHE_DIR)
    

# MTCNN_MODEL_DIR = '/app/deps/facenet/src/align'
# FACENET_MODEL_DIR = '/app/deps/facenet/models/20170512-110547'

# BoundingBox = namedtuple('BoundingBox', ['x1', 'x2', 'y1', 'y2'])

KB = 1024


def file_size(filename):
    st = os.stat(filename)
    return st.st_size


def fetch_images(name, outdir=IMG_CACHE_DIR, n=25, query_extras=None,
                 force=False):
    """Fetch images from Google"""
    out_subdir =  os.path.join(outdir, name)
    if os.path.exists(out_subdir):
        if not force:
            print('Using cached', out_subdir)
            return out_subdir
        else:
            shutil.rmtree(out_subdir)

    query = '"%s"' % name
    if query_extras:
        query += ' %s' % query_extras

    response = google_images_download.googleimagesdownload()
    response.download({
        'keywords': query, 'limit': n,
        'output_directory': TMP_DOWNLOAD_DIR, 'format': 'jpg', 'size': 'medium'
    })

    tmp_dir = os.path.join(TMP_DOWNLOAD_DIR, query)
    for ent in os.listdir(tmp_dir):
        img_path = os.path.join(tmp_dir, ent)
        im = cv2.imread(img_path)
        if im is None:
            os.remove(img_path)

    shutil.move(tmp_dir, out_subdir)
    return out_subdir


# class MTCNN(object):

#     def __init__(self):
#         self.graph = tf.Graph()
#         self.graph.as_default()

#         tf_config = tf.ConfigProto(allow_soft_placement=True)
#         self.session = tf.Session(config=tf_config)
#         self.session.as_default()

#         print('Loading model...')
#         self.pnet, self.rnet, self.onet = \
#             align.detect_face.create_mtcnn(self.session, MTCNN_MODEL_DIR)
#         print('Model loaded!')


#     def face_detect(self, imgs):
#         threshold = [0.45, 0.6, 0.7]
#         factor = 0.709
#         vmargin = 0.2582651235637604
#         hmargin = 0.3449094129917718
#         detection_window_size_ratio = .2

#         detections = align.detect_face.bulk_detect_face(
#             imgs, detection_window_size_ratio, self.pnet, self.rnet, self.onet,
#             threshold, factor)

#         batch_faces = []
#         for img, bounding_boxes in zip(imgs, detections):
#             if bounding_boxes is None:
#                 batch_faces.append([])
#                 continue
#             frame_faces = []
#             bounding_boxes = bounding_boxes[0]
#             num_faces = bounding_boxes.shape[0]
#             for i in range(num_faces):
#                 confidence = bounding_boxes[i][4]
#                 if confidence < .8:
#                     continue

#                 img_size = np.asarray(img.shape)[0:2]
#                 det = np.squeeze(bounding_boxes[i][0:4])
#                 vmargin_pix = int((det[2] - det[0]) * vmargin)
#                 hmargin_pix = int((det[3] - det[1]) * hmargin)
#                 frame_faces.append(
#                     BoundingBox(
#                         x1=np.maximum(det[0] - hmargin_pix / 2, 0),
#                         y1=np.maximum(det[1] - vmargin_pix / 2, 0),
#                         x2=np.minimum(det[2] + hmargin_pix / 2, img_size[1]),
#                         y2=np.minimum(det[3] + vmargin_pix / 2, img_size[0])))

#             batch_faces.append(frame_faces)
#         return batch_faces

#     def close(self):
#         self.session.close()


# class FaceNetEmbed(object):

#     def __init__(self):
#         self.in_size = 160
#         self.graph = tf.Graph()
#         self.graph.as_default()

#         tf_config = tf.ConfigProto(allow_soft_placement=True)
#         self.session = tf.Session(config=tf_config)
#         self.session.as_default()

#         meta_file, ckpt_file = facenet.get_model_filenames(FACENET_MODEL_DIR)
#         g = tf.Graph()
#         g.as_default()
#         saver = tf.train.import_meta_graph(os.path.join(FACENET_MODEL_DIR, meta_file))
#         saver.restore(self.session, os.path.join(FACENET_MODEL_DIR, ckpt_file))

#         self.images_placeholder = tf.get_default_graph().get_tensor_by_name('input:0')
#         self.embeddings = tf.get_default_graph().get_tensor_by_name('embeddings:0')
#         self.phase_train_placeholder = tf.get_default_graph().get_tensor_by_name('phase_train:0')

#     def embed(self, img):
#         [fh, fw] = img.shape[:2]
#         if fh == 0 or fw == 0:
#             return np.zeros(128, dtype=np.float32).tobytes()
#         else:
#             img = cv2.resize(img, (self.in_size, self.in_size))
#             img = facenet.prewhiten(img)
#             embs = self.session.run(
#                 self.embeddings,
#                 feed_dict={
#                     self.images_placeholder: [img],
#                     self.phase_train_placeholder: False
#                 })
#             return embs[0]


# _face_detector = None
# _face_embeddor = None
# def _get_models():
#     global _face_detector, _face_embeddor
#     if _face_detector is None:
#         print('Loading face detection model')
#         _face_detector = MTCNN()
#     if _face_embeddor is None:
#         print('Loading face embedding model')
#         _face_embeddor = FaceNetEmbed()
#     return _face_detector, _face_embeddor


# def detect_faces_in_images(raw_images):
#     face_detector, _ = _get_models()

#     detected_faces = face_detector.face_detect(raw_images)
#     result = []
    
#     for img, detections in zip(raw_images, detected_faces):
#         if len(detections) == 0:
#             result.append([])
#         else:
#             cropped_images = []
#             for box in detections:
#                 x1 = int(math.floor(box.x1))
#                 x2 = int(math.ceil(box.x2))
#                 y1 = int(math.floor(box.y1))
#                 y2 = int(math.ceil(box.y2))
#                 cropped_image = img[y1:y2, x1:x2, :]
#                 if cropped_image.size > 0:  
#                     cropped_images.append(cropped_image)
#             result.append(cropped_images)
#     return result
    

# def embed_images(cropped_images, one_face_per_img=True):
#     _, face_embeddor = _get_models()
#     embs = []
#     for img_list in cropped_images:
#         if one_face_per_img and len(img_list) > 1:
#             continue
#         for img in img_list:
#             if img.size == 0:
#                 continue
#             emb = face_embeddor.embed(img)
#             embs.append(emb)

#     if len(embs) == 0:
#         raise RuntimeError('No embeddings were created')

#     return embs


# def embed_directory(name_path, one_face_per_img=True):
#     """Compute a mean embedding of all of the images in the directory"""
#     if not os.path.isdir(name_path):
#         return RuntimeError('Directory not found')
#     print('Reading images in:', name_path)

#     raw_images = []
#     image_paths = []
#     for img in os.listdir(name_path):
#         img_path = os.path.join(name_path, img)
#         if not os.path.isfile(img_path):
#             continue
#         if file_size(img_path) < 5 * KB:
#             continue
#         im = cv2.imread(img_path)
#         if im is None:
#             continue
#         raw_images.append(im)
#         image_paths.append(img_path)

#     return np.mean(
#         embed_images(detect_faces_in_images(raw_images), one_face_per_img), 
#         axis=0)

MODEL_SERVER_PORT = 9999
MODEL_SERVER_URL = 'http://localhost:{}/'.format(MODEL_SERVER_PORT)


def detect_faces_in_images(dir_path):
    faces = requests.get(MODEL_SERVER_URL + 'face-detect', params={'path': dir_path}).json()
    result = {}
    for img_path, bboxes in faces.items():
        result[img_path] = []
        for bbox in bboxes:
            x1 = int(bbox['x1'])
            x2 = int(bbox['x2'])
            y1 = int(bbox['y1'])
            y2 = int(bbox['y2'])
            img = cv2.imread(img_path)
            cropped_image = img[y1:y2, x1:x2, :]
            if cropped_image.size > 0:  
                result[img_path].append(cropped_image)
    return result
    

def embed_images(images):
    embs = []
    for img in images:
        emb = requests.post(
            MODEL_SERVER_URL + 'face-embed', 
            params={'height': img.shape[0], 'width': img.shape[1]},
            data=img.tostring()
        ).json()
        embs.append(np.array(emb))
    if len(embs) == 0:
        raise RuntimeError('No embeddings were created')
    return embs


def embed_directory(dir_path, one_face_per_img=True):
    """Compute a mean embedding of all of the images in the directory"""
    faces = requests.get(MODEL_SERVER_URL + 'face-detect', params={'path': dir_path}).json()
    embeddings = []
    for img_path, bboxes in faces.items():
        if one_face_per_img and len(bboxes) > 1:
            continue
        for bbox in bboxes:
            emb = requests.get(MODEL_SERVER_URL + 'face-embed', params={'path': img_path, **bbox}).json()
            embeddings.append(np.array(emb))
    return np.mean(embeddings, axis=0)


def name_to_embedding(name, n=25, cache=True, one_face_per_img=True):
    """Go directly from a name to face embedding"""
    if cache:
        google_imgs_dir = fetch_images(name, outdir=IMG_CACHE_DIR, n=n,
                                       query_extras='', force=False)
        return embed_directory(google_imgs_dir, one_face_per_img)
    else:
        tmp_dir = tempfile.mkdtemp('img_download')
        try:
            google_imgs_dir = fetch_images(name, outdir=tmp_dir, n=n,
                                           query_extras='', force=True)
            return embed_directory(google_imgs_dir, one_face_per_img)
        finally:
            if os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir)


def urls_to_embedding(urls):
    """Fetch images at the urls and embed faces"""
    tmp_dir = tempfile.mkdtemp('img_download')
    try:
        for i, url in enumerate(urls):
            img_path = os.path.join(tmp_dir, '{}.jpg'.format(i))
            request.urlretrieve(url, img_path)
        return embed_directory(tmp_dir)
    finally:
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir)

