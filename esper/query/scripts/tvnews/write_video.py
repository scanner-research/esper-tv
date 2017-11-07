from query.scripts.script_util import *
from scannerpy.stdlib import writers
from collections import defaultdict

with Database() as db:
    video = Video.objects.all()[0]
    faces = FaceInstance.objects.filter(frame__video=video).order_by('frame__number').values('bbox', 'frame__number')
    t = db.table(video.path)

    # frames = defaultdict(list)
    # for face in faces:
    #     bbox = face['bbox']
    #     bbox.x1 *= video.width
    #     bbox.x2 *= video.width
    #     bbox.y1 *= video.height
    #     bbox.y2 *= video.height
    #     frames[face['frame__number']].append(bbox)

    # N = t.num_rows()
    # all_bboxes = [[] for _ in range(N)]

    # for frame, bboxes in frames.iteritems():
    #     for i in range(frame, min(frame+24, N)):
    #         all_bboxes[i] = bboxes

    # bb_t = db.new_table('test', ['bboxes'], [[t] for t in all_bboxes], fn=writers.bboxes, force=True)
    # print bb_t.num_rows()

    bb_t = db.table('test')

    frame = t.as_op().all()
    bboxes = bb_t.as_op().all()
    out_frame = db.ops.DrawBox(frame=frame, bboxes=bboxes)
    job = Job(columns=[out_frame], name='test2')
    out_table = db.run(job, force=True)
    out_table.column('frame').save_mp4('faces')
