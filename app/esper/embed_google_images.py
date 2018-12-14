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


BoundingBox = namedtuple('BoundingBox', ['x1', 'x2', 'y1', 'y2'])

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


def detect_faces(input_path):
    faces = requests.get(MODEL_SERVER_URL + 'face-detect', 
                         params={'path': input_path}).json()
    result = []
    for img_path, bboxes in faces.items():
        height, width, _ = cv2.imread(img_path).shape
        for bbox in bboxes:
            x1 = bbox['x1'] / width
            x2 = bbox['x2'] / width
            y1 = bbox['y1'] / height
            y2 = bbox['y2'] / height 
            if y2 > y1 and x2 > x1:
                result.append((
                    img_path,
                    BoundingBox(x1=x1, x2=x2, y1=y1, y2=y2)
                ))
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

