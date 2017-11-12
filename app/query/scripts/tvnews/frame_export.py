from query.scripts.script_util import *
import requests
import math

videos = Video.objects.all()
for video in videos:
    stride = int(math.ceil(video.fps)/2)
    print video.path, video.fps, stride
    ids = [
        str(f['id'])
        for f in Frame.objects.filter(video=video, number__in=range(0, video.num_frames, stride))
        .order_by('number').values('id')
    ]
    requests.post('http://localhost:8000/batch_fallback', data={'frames': ','.join(ids)})
