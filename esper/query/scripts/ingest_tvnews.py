from query.scripts.script_util import *
from django import db
import json

# print 'Videos'
# videos = {}
# with open('videos.csv') as f:
#     lines = [s.strip().split('\t') for s in f.readlines()[1:]]
#     for line in lines:
#         [id, path, num_frames, fps, width, height, timestamp, channel, show, time] = line
#         videos[id] = Video(id=id, path=path, num_frames=int(num_frames), fps=float(fps), width=int(width),
#                            height=int(height), channel=channel, show=show, time=time)
# Video.objects.bulk_create(videos.values())

# print 'Frames'
# frames = []
# with open('frames.csv') as f:
#     lines = [s.strip().split('\t') for s in f.readlines()[1:]]
#     for line in lines:
#         [id, number, video_id] = line
#         frames.append(Frame(id=id, video=videos[video_id], number=number))
# Frame.objects.bulk_create(frames)

handlabeled, _ = Labeler.objects.get_or_create(name='handlabeled')
mtcnn, _ = Labeler.objects.get_or_create(name='mtcnn')
facenet, _ = Labeler.objects.get_or_create(name='facenet')
genders = {
    'M':  m.Gender.objects.get_or_create(name='male')[0],
    'F':  m.Gender.objects.get_or_create(name='female')[0],
    '0':  m.Gender.objects.get_or_create(name='unknown')[0]
}

print 'Tracks'
old_tracks = {}
new_tracks = {}
with open('tracks.csv') as f:
    lines = [s.strip().split('\t') for s in f.readlines()[1:]]
    for [id, gender] in lines:
        old_tracks[int(id)] = Face(gender=genders[gender])

with open('db.csv') as f:
    lines = f.readlines()[1:]

print 'Faces'
for i, line in enumerate(lines):
    [path, frame_number, labelset, track, gender, bbox] = line.strip().split('\t')[:6]
    if track == 'NULL':
        new_tracks[i] = Face(gender=genders[gender])

Face.objects.bulk_create(old_tracks.values() + new_tracks.values())

videos = {v.path: v for v in Video.objects.all()}
frames = {v.id: {f.number: f for f in Frame.objects.filter(video=v)} for v in videos.values()}

print 'Instances'
instances = {}
tuples = set()
for i, line in enumerate(lines):
    if i % 100 == 0: print i
    [path, frame_number, labelset, track, gender, bbox] = line.strip().split('\t')[:6]
    frame_number = int(frame_number)

    path = 'tvnews/segments/{}'.format(path.split('/')[-1])
    if path not in videos:
        continue
    video = videos[path]
    frame = frames[video.id][frame_number]

    if track == 'NULL':
        face = new_tracks[i]
    else:
        face = old_tracks[int(track)]

    key = (video.id, frame_number, labelset, face.id)
    if key in tuples:
        continue
    tuples.add(key)

    labeler = mtcnn if labelset == 'detected' else handlabeled
    bbox_bytes = bytearray.fromhex(bbox)
    bbox = proto.BoundingBox()
    bbox.ParseFromString(bbox_bytes)

    instances[i] = FaceInstance(frame=frame, bbox_x1=bbox.x1, bbox_x2=bbox.x2, bbox_y1=bbox.y1, bbox_y2=bbox.y2, labeler=labeler, concept=face)

FaceInstance.objects.bulk_create(instances.values())

print 'Features'
features = []
for i, line in enumerate(lines):
    if not i in instances: continue
    try:
        [path, frame_number, labelset, track, gender, bbox, features_str] = line.strip().split('\t')[:7]

        features.append(FaceFeatures(labeler=facenet, features=features_str, instance=instances[i]))
    except ValueError:
        pass

db.reset_queries()
FaceFeatures.objects.bulk_create(features, batch_size=1000)
