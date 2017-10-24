from flask import Flask, request, send_file
import os
import subprocess as sp
from google.cloud import storage
import shlex

FILE_DIR = '/tmp'

client = storage.Client()
bucket = client.get_bucket('esper')

app = Flask(__name__)


@app.route('/')
def index():
    path = request.args.get('path')
    frame = request.args.get('frame')
    id = request.args.get('id')

    basename = os.path.split(path)[1]
    video_path = '{}/{}'.format(FILE_DIR, basename)

    if not os.path.isfile(video_path):
        blob = bucket.get_blob(path)
        with open(video_path, 'wb') as f:
            blob.download_to_file(f)

    sp.check_call(shlex.split("ffmpeg -y -i {} -vf \"select=eq(n\\,{})\" -frames:v 1 {}/%05d.jpg".format(video_path, frame, FILE_DIR)))
    blob = bucket.blob('public/thumbnails/tvnews/frame_{}.jpg'.format(id))
    img_path = '{}/00001.jpg'.format(FILE_DIR)
    blob.upload_from_filename(img_path)

    return send_file(img_path)
