from esper.prelude import *

tracks = list(PersonTrack.objects.filter(video__videotag__tag__name='pose-test'))
for i, track in enumerate(tracks):
    print(i)
    faces = list(Face.objects.filter(person__tracks=track).select_related('person__frame'))
    if len(faces) == 0:
        continue
    track.min_frame = min([f.person.frame.number for f in faces])
    track.max_frame = max([f.person.frame.number for f in faces])
PersonTrack.objects.bulk_update(tracks)
