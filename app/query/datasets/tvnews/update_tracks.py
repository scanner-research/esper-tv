from query.datasets.prelude import *
 
tracks = FaceTrack.objects.all()
for i, track in enumerate(tracks):
    print i
    faces = list(Face.objects.filter(track=track).values('id', 'frame__number', 'frame__video__id'))
    if len(faces) == 0:
        continue
    track.min_frame = min([f['frame__number'] for f in faces])
    track.max_frame = max([f['frame__number'] for f in faces])
    track.video_id = faces[0]['frame__video__id']
    track.save()
#FaceTrack.objects.bulk_update(tracks)
