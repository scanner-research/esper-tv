from esper.prelude import par_for, unzip, pcache, flatten, collect
from query.models import Video, Face, Frame, HairColor, HairColorName, Labeler
from esper.scannerutil import ScannerWrapper, ScannerSQLTable
from scannertools import clothing_detection , hairstyle_detection
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

    return [f['number'] for f in
            qs.annotate(
                c=Subquery(Face.objects.filter(frame=OuterRef('pk')).values('frame').annotate(c=Count('*')).values('c')))
            .filter(c__gte=1)
            .values('number').order_by('number')]


@register_python_op(name='BboxesFromJson')
def bboxes_from_json(config, bboxes: bytes) -> bytes:
    dilate = config.args['dilate'] if 'dilate' in config.args else 1.0
    bboxes = json.loads(bboxes.decode('utf-8'))
    return writers.bboxes([
        config.protobufs.BoundingBox(
            x1=bb['bbox_x1']*(2.-dilate),
            x2=bb['bbox_x2']*dilate,
            y1=bb['bbox_y1']*(2.-dilate),
            y2=bb['bbox_y2']*dilate)
        for bb in bboxes
    ], config.protobufs)


#class ClothingDetectionPipeline(clothing_detection.ClothingDetectionPipeline):
class ClothingDetectionPipeline(hairstyle_detection.HairStyleDetectionPipeline):
    # parser_fn = {
    #     'clothing': hairstyle_detection.HairStyleDetectionPipeline.parser_fn,
    #     #clothing_detection.ClothingDetectionPipeline.parser_fn,
    #     'bboxes': lambda: readers.bboxes
    # }

    def build_pipeline(self, adjust_bboxes=True):
        bboxes = self._db.ops.BboxesFromJson(bboxes=self._sources['bboxes'].op)
        # new_bbs = self._db.ops.PrepareClothingBbox(
        #     frame=self._sources['frame_sampled'].op,
        #     bboxes=bboxes)
        return {
            'clothing':
            getattr(self._db.ops, 'DetectHairStyle{}'.format('GPU' if self._device == DeviceType.GPU else 'CPU'))(
                frame=self._sources['frame_sampled'].op,
                bboxes=bboxes,
                model_path=self._model_path,
                model_def_path=self._model_def_path,
                model_key='best_model',
                adjust_bboxes=adjust_bboxes,
                device=self._device),
            # 'bboxes': new_bbs
        }

detect_clothing = ClothingDetectionPipeline.make_runner()

videos = list(Video.objects.all().order_by('id'))

cfg = cluster_config(
    num_workers=50, worker=worker_config('n1-standard-16', gpu=2),
    pipelines=[hairstyle_detection.HairStyleDetectionPipeline])
    #pipelines=[clothing_detection.ClothingDetectionPipeline])

# with make_cluster(cfg, sql_pool=2, no_delete=True) as db_wrapper:
if True:
    db_wrapper = ScannerWrapper.create()

    db = db_wrapper.db

    print('Fetching frames')
    frames = pcache.get('clothing_frames', lambda: par_for(frames_for_video, videos, workers=8))
    videos, frames = unzip([(v, f) for (v, f) in zip(videos, frames) if len(f) > 0])
    videos = list(videos)
    frames = list(frames)

    videos = videos[:1000]
    frames = frames[:1000]

    print('Running pipeline')

    clothing = detect_clothing(
        db,
        videos=[v.for_scannertools() for v in videos],
        frames=frames,
        bboxes=[ScannerSQLTable(
            Face, v, num_elements=len(f),
            filter='MOD(query_frame.number, CAST(FLOOR(query_video.fps * 3) AS INTEGER)) = 0' 
            if v.threeyears_dataset else 
            'MOD(query_frame.number, CAST(CEIL(query_video.fps * 3) AS INTEGER)) = 0')
            for v, f in zip(videos, frames)],
        run_opts={
            'io_packet_size': 500,
            'work_packet_size': 20,
            'checkpoint_frequency': 100
        },
        device=DeviceType.GPU,
        megabatch=25000)

    # frame = video.for_scannertools().frame(frame_num)
    # frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    # [h, w] = frame.shape[:2]
    # for i, (bb, cloth) in enumerate(zip(frame_bb, frame_cloth)):
    #     assert cv2.imwrite('/app/data/clothing/{}/{}_{}_{}.jpg'.format(
    #         cloth.to_dict()['Hair color 3'],
    #         video.item_name(), frame_num, i),
    #         frame[int(bb.y1*h):int(bb.y2*h), int(bb.x1*w):int(bb.x2*w), :]) != None

    hc_names = {h.name: h.id for h in HairColorName.objects.all()}
    labeler, _ = Labeler.objects.get_or_create(name='haotian-hairstyle')

    def run(arg):
        (video, vid_frames, outp) = arg
        hcs = []
        face_ids = collect(
            list(Face.objects.filter(frame__video=video).order_by('frame__number', 'id')
                 .values('id', 'frame__number')),
            lambda f: f['frame__number'])

        for (frame_num, frame_cloth) in zip(vid_frames, list(outp.load())):
            faces = list(Face.objects.filter(frame__video=video, frame__number=frame_num).order_by('id').values('id'))
            for (cloth, face) in zip(frame_cloth, face_ids[frame_num]):
                hcs.append(HairColor(
                    labeler=labeler,
                    face_id=face['id'], 
                    color_id=hc_names[cloth.to_dict()['Hair color 3']]))

        pcache.set(video.item_name() + '-haircolor', hcs)

    #pcache.set('haircolors', flatten(
    par_for(run, list(zip(videos, frames, clothing)), workers=16)
    #))

    # HairColor.objects.bulk_create(pcache.get('haircolors'))
    #HairColor.objects.bulk_create(flatten(hcs))
                
