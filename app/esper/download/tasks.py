from celery import Celery
from tqdm import tqdm
import os
import subprocess as sp

app = Celery('archive-download', broker='redis://10.0.0.3:6379/0')

@app.task(acks_late=True)
def download(video):
    print('Downloading {}'.format(video))

    try:
        sp.check_call('ia download {} --glob "*.mp4"'.format(video), shell=True)
        sp.check_call('gsutil mv {id}/{id}.mp4 gs://esper/tvnews/videos/{id}.mp4'.format(id=video), shell=True)
    except Exception:
        print('Error: {}'.format(video))
