from django.core.management.base import BaseCommand, CommandError
from query.models import Video, Face
from scannerpy import Database, DeviceType
from scannerpy.stdlib import NetDescriptor, parsers, bboxes


class Command(BaseCommand):
    help = 'Detect faces in videos'

    def add_arguments(self, parser):
        parser.add_argument('path')

    def _detect(self, db, path):
        descriptor = NetDescriptor.from_file(db, '/h/wcrichto/scanner/nets/caffe_facenet.toml')
        facenet_args = db.protobufs.FacenetArgs()
        facenet_args.threshold = 0.5
        caffe_args = facenet_args.caffe_args
        caffe_args.net_descriptor.CopyFrom(descriptor.as_proto())
        caffe_args.batch_size = 5

        table_input = db.ops.Input()
        facenet_input = db.ops.FacenetInput(
            inputs=[(table_input, ["frame", "frame_info"])],
            args=facenet_args,
            device=DeviceType.GPU)
        facenet = db.ops.Facenet(
            inputs=[(facenet_input, ["facenet_input"]), (table_input, ["frame_info"])],
            args=facenet_args,
            device=DeviceType.GPU)
        facenet_output = db.ops.FacenetOutput(
            inputs=[(facenet, ["facenet_output"]), (table_input, ["frame_info"])],
            args=facenet_args)

        sampler = db.sampler()
        print('Running face detector...')
        outputs = []
        for scale in [0.125, 0.25, 0.5, 1.0]:
            print('Scale {}...'.format(scale))
            facenet_args.scale = scale
            tasks = sampler.all([(path, '{}_faces_{}'.format(path, scale))],
                                    item_size=50)
            [output] = db.run(tasks, facenet_output, force=True, work_item_size=5)
            output = db.table('{}_faces_{}'.format(path, scale))
            outputs.append(output)

        all_bboxes = [
            [box for (_, box) in out.load(['bboxes'], parsers.bboxes)]
            for out in outputs]

        nms_bboxes = []
        frames = len(all_bboxes[0])
        runs = len(all_bboxes)
        for fi in range(frames):
            frame_bboxes = []
            for r in range(runs):
                frame_bboxes += (all_bboxes[r][fi])
            frame_bboxes = bboxes.nms(frame_bboxes, 0.3)
            nms_bboxes.append(frame_bboxes)

        return nms_bboxes

    def handle(self, *args, **options):
        with open(options['path']) as f:
            paths = [s.strip() for s in f.readlines()]

        with Database() as db:
            for path in paths:
                video = Video.objects.filter(path=path)[0]
                print video.path
                if len(Face.objects.filter(video=video)) > 0:
                    print 'Skipping...'
                    continue
                print 'Detecting...'
                faces = self._detect(db, path)
                for i, frame_faces in enumerate(faces):
                    if len(frame_faces) == 0: continue
                    for bbox in frame_faces:
                        f = Face()
                        f.video = video
                        f.frame = i
                        f.bbox = bbox
                        f.save()
