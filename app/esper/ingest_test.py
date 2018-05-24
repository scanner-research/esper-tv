from query.scripts.script_util import *
import json
import math
from django.db import transaction

def parse(path):
    with open(path, 'r') as f:
        while True:
            path = f.next()[:-1]  # this will raise StopIteration for us when we reach EOF
            num_rows = int(math.ceil(int(next(f)) / 24.0))
            print((path, num_rows))
            yield path, [f.next()[:-1] for _ in range(num_rows)]

to_ingest = [
    # ('assets/kcam_tiny_faces.txt', 'tinyfaces'),
    # ('assets/kcam_cpm_faces.txt', 'cpm'),
    ('assets/kcam_frcnn_people.txt', 'frcnn')
]  # yapf: disable

for fpath, labeler_name in to_ingest:
    print(fpath)

    labeler, _ = Labeler.objects.get_or_create(name=labeler_name)
    bar = progress_bar(len(list(parse(fpath))))
    does_not_exist = []

    for vi, (path, rows) in enumerate(parse(fpath)):
        try:
            video = Video.objects.get(path__contains=path)
        except Video.DoesNotExist:
            does_not_exist.append(path)
            continue

        video_boxes = {
            j: [
                proto.BoundingBox(x1=r[0], y1=r[1], x2=r[2], y2=r[3])
                for r in [[float(s) for s in box.split(' ')] for box in l.split(',')[:-1]]
            ]
            for j, l in enumerate(rows) if l != ''
        }

        Instance = PersonInstance if labeler_name == 'frcnn' else FaceInstance

        frames = list(
            Frame.objects.filter(video=video).order_by('number').extra(
                where=['number mod 24=0']))
        faces = [
            Instance(labeler=labeler, frame=frames[j], bbox=bbox)
            for j, frame_boxes in list(video_boxes.items()) for bbox in frame_boxes
        ]

        with transaction.atomic():
            for face in faces:
                f = Face()
                f.save()
                face.concept = f

        Instance.objects.bulk_create(faces)

        bar.update(vi)

    print(('Failed to find: {}'.format(json.dumps(does_not_exist))))
