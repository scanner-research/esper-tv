from query.scripts.script_util import *

faces = list(Face.objects.all())
insts = list(FaceInstance.objects.all())

for f, i in zip(faces, insts):
    i.concept = f

FaceInstance.objects.bulk_update(insts, update_fields=['concept'], batch_size=100)
