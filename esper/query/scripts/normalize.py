from query.scripts.script_util import *

print 'Normalizing bboxes...'
insts = FaceInstance.objects.select_related('frame__video')
for inst in insts:
    video = inst.frame.video
    w, h = video.width, video.height
    print inst.bbox
    inst.bbox.x1 /= w
    inst.bbox.x2 /= w
    inst.bbox.y1 /= h
    inst.bbox.y2 /= h

print 'Saving changes...'
FaceInstance.objects.bulk_update(insts, update_fields=['bbox'], batch_size=100)

print 'Done!'
