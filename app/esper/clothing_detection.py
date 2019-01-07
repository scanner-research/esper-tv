from esper.prelude import par_for, unzip, pcache, flatten, collect
from query.models import Video, Face, Frame, HairColor, HairColorName, Labeler, Clothing, ClothingName
from esper.scannerutil import ScannerWrapper, ScannerSQLTable, ScannerSQLPipeline
from scannertools import clothing_detection, hairstyle_detection
from django.db.models import Count, OuterRef, Subquery, F, Q, Func, IntegerField
from django.db.models import ExpressionWrapper as Expr
from scannerpy import register_python_op, Database, DeviceType
from esper.kube import cluster_config, worker_config, make_cluster
import json
from scannerpy.stdlib import writers, readers
import cv2
from tqdm import tqdm
from scannertools import init_storage
from django.db.models.functions import Cast
import pickle


class Floor(Func):
    template = 'FLOOR(%(expressions)s)'


class Ceil(Func):
    template = 'CEIL(%(expressions)s)'


def frames_for_video(video):
    if video.threeyears_dataset:
        qs = Frame.objects \
            .annotate(nfloor=Expr(F('number') % Cast(Floor(F('video__fps') * 3), IntegerField()), output_field=IntegerField())) \
            .filter(video=video) \
            .filter(nfloor=0)
    else:
        qs = Frame.objects \
            .annotate(nceil=Expr(F('number') % Cast(Ceil(F('video__fps') * 3), IntegerField()), output_field=IntegerField())) \
            .filter(video=video) \
            .filter(nceil=0)

    return [
        f['number'] for f in qs.annotate(
            c=Subquery(
                Face.objects.filter(frame=OuterRef('pk')).values('frame').annotate(
                    c=Count('*')).values('c'))).filter(c__gte=1).values('number').order_by('number')
    ]


@register_python_op(name='BboxesFromJson')
def bboxes_from_json(config, bboxes: bytes) -> bytes:
    dilate = config.args['dilate'] if 'dilate' in config.args else 1.0
    bboxes = json.loads(bboxes.decode('utf-8'))
    return writers.bboxes([
        config.protobufs.BoundingBox(
            x1=bb['bbox_x1'] * (2. - dilate),
            x2=bb['bbox_x2'] * dilate,
            y1=bb['bbox_y1'] * (2. - dilate),
            y2=bb['bbox_y2'] * dilate) for bb in bboxes
    ], config.protobufs)


labeler_id = Labeler.objects.get_or_create(name='haotian-clothing')[0].id
clothing_names = {c.name: c.id for c in ClothingName.objects.all()}


@register_python_op(name='ClothingToJson')
def clothing_to_json(config, clothing: bytes, bboxes: bytes) -> bytes:
    clothing = pickle.loads(clothing)
    faces = json.loads(bboxes.decode('utf-8'))
    return json.dumps([{
        'face_id':
        face['id'],
        'clothing_id':
        clothing_names[clothing_detection.Clothing(att).to_dict()['Clothing category']],
        'labeler_id':
        labeler_id
    } for (att, face) in zip(clothing, faces)])


class ClothingDetectionPipeline(ScannerSQLPipeline, clothing_detection.ClothingDetectionPipeline):
    db_class = Clothing
    json_kernel = 'ClothingToJson'
    additional_sources = ['bboxes', 'clothing_bboxes']

    def build_pipeline(self, adjust_bboxes=True):
        return {
            'clothing':
            getattr(self._db.ops,
                    'DetectClothing{}'.format('GPU' if self._device == DeviceType.GPU else 'CPU'))(
                        frame=self._sources['frame_sampled'].op,
                        bboxes=self._sources['clothing_bboxes'].op,
                        model_path=self._model_path,
                        model_def_path=self._model_def_path,
                        model_key='best_model',
                        adjust_bboxes=adjust_bboxes,
                        device=self._device),
            'bboxes':
            self._sources['bboxes'].op
        }


class ClothingBboxesPipeline(clothing_detection.ClothingBboxesPipeline):
    def build_pipeline(self):
        bboxes = self._db.ops.BboxesFromJson(bboxes=self._sources['bboxes'].op)
        return {
            'bboxes':
            self._db.ops.PrepareClothingBbox(
                frame=self._sources['frame_sampled'].op, bboxes=bboxes)
        }


detect_clothing_bboxes = ClothingBboxesPipeline.make_runner()
detect_clothing = ClothingDetectionPipeline.make_runner()

videos = list(Video.objects.all().order_by('id'))

cfg = cluster_config(
    num_workers=100,
    worker=worker_config('n1-standard-16', gpu=1),
    pipelines=[clothing_detection.ClothingDetectionPipeline])

with make_cluster(cfg, sql_pool=2, no_delete=True) as db_wrapper:
    # if True:
    #     db_wrapper = ScannerWrapper.create()

    db = db_wrapper.db

    print('Fetching frames')
    frames = pcache.get('clothing_frames', lambda: par_for(frames_for_video, videos, workers=8))
    videos, frames = unzip([(v, f) for (v, f) in zip(videos, frames) if len(f) > 0])
    videos = list(videos)
    frames = list(frames)

    videos = videos
    frames = frames

    bbox_tables = [
        ScannerSQLTable(
            Face,
            v,
            num_elements=len(f),
            filter='MOD(query_frame.number, CAST(FLOOR(query_video.fps * 3) AS INTEGER)) = 0'
            if v.threeyears_dataset else
            'MOD(query_frame.number, CAST(CEIL(query_video.fps * 3) AS INTEGER)) = 0')
        for v, f in zip(videos, frames)
    ]

    print('Running pipeline')

    clothing_bboxes = detect_clothing_bboxes(
        db,
        videos=[v.for_scannertools() for v in videos],
        frames=frames,
        bboxes=bbox_tables,
        run_opts={
            'io_packet_size': 1000,
            'work_packet_size': 50,
            'checkpoint_frequency': 100
        },
        megabatch=25000)

    clothing = detect_clothing(
        db,
        videos=[v.for_scannertools() for v in videos],
        db_videos=videos,
        frames=frames,
        bboxes=bbox_tables,
        clothing_bboxes=clothing_bboxes,
        run_opts={
            'io_packet_size': 250,
            'work_packet_size': 10,
            'checkpoint_frequency': 100
        },
        device=DeviceType.GPU,
        megabatch=25000)
    exit()

    hc_names = {h.name: h.id for h in HairColorName.objects.all()}
    labeler, _ = Labeler.objects.get_or_create(name='haotian-hairstyle')

    def run(arg):
        (video, vid_frames, outp) = arg
        hcs = []
        face_ids = collect(
            list(
                Face.objects.filter(frame__video=video).order_by('frame__number', 'id').values(
                    'id', 'frame__number')), lambda f: f['frame__number'])

        for (frame_num, frame_cloth) in zip(vid_frames, list(outp.load())):
            faces = list(
                Face.objects.filter(frame__video=video,
                                    frame__number=frame_num).order_by('id').values('id'))
            for (cloth, face) in zip(frame_cloth, face_ids[frame_num]):
                hcs.append(
                    HairColor(
                        labeler=labeler,
                        face_id=face['id'],
                        color_id=hc_names[cloth.to_dict()['Hair color 3']]))

        pcache.set(video.item_name() + '-haircolor', hcs)

    #pcache.set('haircolors', flatten(
    par_for(run, list(zip(videos, frames, clothing)), workers=16)
    #))

    # HairColor.objects.bulk_create(pcache.get('haircolors'))
    #HairColor.objects.bulk_create(flatten(hcs))
