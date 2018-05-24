from esper.prelude import *
import socket
import scannerpy
import cv2

@scannerpy.register_python_op(name='Blurriness')
def blurriness(config, frame: scannerpy.FrameType, bboxes: bytes) -> bytes:
    bboxes = json.loads(bboxes.decode('utf-8'))
    results = []
    for bbox in bboxes:
        img = frame[int(bbox['y1']):int(bbox['y2']),
                    int(bbox['x1']):int(bbox['x2']), :]
        if img.shape[0] == 0 or img.shape[1] == 0:
            continue
        img = cv2.resize(img, (200, 200))
        results.append({
            'id': bbox['id'],
            'blurriness': cv2.Laplacian(img, cv2.CV_64F).var()
        })

    return json.dumps(results).encode()


db = make_scanner_db(multiworker=True)

videos = Video.objects.all()[20000:]

sql_config = db.protobufs.SQLConfig(
    adapter='postgres',
    hostaddr=socket.gethostbyname('db'),
    port=5432,
    dbname='esper',
    user=os.environ['DJANGO_DB_USER'],
    password=os.environ['DJANGO_DB_PASSWORD'])
sql_query = db.protobufs.SQLQuery(
    fields='''
    query_tvnews_face.id as id,
    (query_tvnews_face.bbox_x1 * query_tvnews_video.width) as x1,
    (query_tvnews_face.bbox_y1 * query_tvnews_video.height) as y1,
    (query_tvnews_face.bbox_x2 * query_tvnews_video.width) as x2,
    (query_tvnews_face.bbox_y2 * query_tvnews_video.height) as y2''',
    table='query_tvnews_face',
    joins='''
    INNER JOIN "query_tvnews_person" ON ("query_tvnews_face"."person_id" = "query_tvnews_person"."id")
    INNER JOIN "query_tvnews_frame" ON ("query_tvnews_person"."frame_id" = "query_tvnews_frame"."id")
    INNER JOIN "query_tvnews_video" ON ("query_tvnews_frame"."video_id" = "query_tvnews_video"."id")
    ''',
    id='query_tvnews_face.id',
    group='query_tvnews_frame.number',
    job_table='query_tvnews_scannerjob'
)

frame = db.sources.FrameColumn()
frame_sampled = frame.sample()
bboxes = db.sources.SQL(config=sql_config, query=sql_query)
blurriness = db.ops.Blurriness(frame=frame_sampled, bboxes=bboxes)
output = db.sinks.SQL(config=sql_config, query=sql_query, input=blurriness)

log.debug('Fetching indices')
def fetch_indices(v):
    return [f['person__frame__number']
            for f in Face.objects.filter(person__frame__video=v).distinct('person__frame__number') \
            .order_by('person__frame__number').values('person__frame__number')]
frame_indices = par_for(fetch_indices, videos, workers=8)

log.debug('Making jobs')
jobs = [
    Job(op_args={
        frame: db.table(v.path).column('frame'),
        frame_sampled: db.sampler.gather(f),
        bboxes: {'filter': 'query_tvnews_video.id = {}'.format(v.id)},
        output: {'job_name': v.path + '_blurriness'}
    })
    for v, f in zip(videos, frame_indices)
]

log.debug('Running job')
db.run(output, jobs, pipeline_instances_per_node=8)
