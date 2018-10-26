from sklearn.neighbors import NearestNeighbors
from django.db import models, connection
from django.db.models import F, ExpressionWrapper
from django.db.models.base import ModelBase
from django.db.models.functions import Cast
from django_bulk_update.manager import BulkUpdateManager
import sys
import numpy as np
import json
import warnings
import os
import subprocess as sp

MAX_STR_LEN = 256

current_dataset = None
datasets = {}


def _print(args):
    print(args)
    sys.stdout.flush()


def CharField(*args, **kwargs):
    return models.CharField(*args, max_length=MAX_STR_LEN, **kwargs)


class Video(models.Model):
    path = CharField(db_index=True)
    num_frames = models.IntegerField()
    fps = models.FloatField()
    width = models.IntegerField()
    height = models.IntegerField()
    has_captions = models.BooleanField(default=False)

    def copy(self, path):
        from esper.prelude import storage
        with open(path, 'wb') as f:
            f.write(storage.read(self.path))

    def url(self, expiry='1m'):
        if os.environ['ESPER_ENV'] != 'google':
            raise Exception('Video.url only works on GCS for now')

        return sp.check_output(
            "gsutil signurl -d {} /app/service-key.json gs://{}/{} | awk 'FNR==2{{print $5}}'".
            format(expiry, os.environ['BUCKET'], self.path),
            shell=True).strip()

    def extract_audio(self, output_path=None, ext='wav', segment=None):
        if output_path is None:
            output_path = tempfile.NamedTemporaryFile(suffix='.{}'.format(ext), delete=False).name

        def fmt_time(t):
            return '{:02d}:{:02d}:{:02d}.{:03d}'.format(
                int(t / 3600), int(t / 60 % 60), int(t % 60), int(t * 1000 % 1000))

        if segment is not None:
            (start, end) = segment
            start_str = '-ss {}'.format(fmt_time(start))
            end_str = '-t {}'.format(fmt_time(end - start))
        else:
            start_str = ''
            end_str = ''

        sp.check_call(
            'ffmpeg -y {} -i "{}" {} {}'.format(start_str, self.url(), end_str, output_path),
            shell=True)
        return output_path

    def frame_time(self, frame):
        return frame / self.fps

    def for_scannertools(self):
        from scannertools import Video as STVideo
        return STVideo(self.path)

    class Meta:
        abstract = True


class Frame(models.Model):
    number = models.IntegerField(db_index=True)
    video = models.ForeignKey(Video)

    class Meta:
        abstract = True

class Labeler(models.Model):
    name = CharField()

    class Meta:
        abstract = True


class Noun(models.Model):
    frame = models.ForeignKey(Frame)

    class Meta:
        abstract = True


class Track(models.Model):
    min_frame = models.IntegerField()
    max_frame = models.IntegerField()
    video = models.ForeignKey(Video)
    labeler = models.ForeignKey(Labeler)

    @staticmethod
    def duration_expr():
        return ExpressionWrapper(
            Cast(F('max_frame') - F('min_frame'), models.FloatField()) / F('video__fps'),
            models.FloatField())

    def duration(self):
        return (self.max_frame - self.min_frame) / int(self.video.fps)

    class Meta:
        abstract = True


class Attribute(models.Model):
    labeler = models.ForeignKey(Labeler)

    class Meta:
        abstract = True


class BoundingBox(models.Model):
    bbox_x1 = models.FloatField()
    bbox_x2 = models.FloatField()
    bbox_y1 = models.FloatField()
    bbox_y2 = models.FloatField()

    def height(self):
        return self.bbox_y2 - self.bbox_y1

    @staticmethod
    def height_expr():
        return ExpressionWrapper(F('bbox_y2') - F('bbox_y1'), models.FloatField())

    def bbox_to_numpy(self):
        return np.array([self.bbox_x1, self.bbox_x2, self.bbox_y1, self.bbox_y2, self.bbox_score])

    class Meta:
        abstract = True


feat_nn = None
feat_ids = None


class Features(models.Model):
    features = models.BinaryField()
    distto = models.FloatField(null=True)

    def load_features(self):
        return np.array(json.loads(str(self.features)))

    @classmethod
    def compute_distances(cls, inst_id):
        global feat_nn
        global feat_ids

        it = cls.objects.annotate(height=F('face__bbox_y2') - F('face__bbox_y1')).filter(
            height__gte=0.1).order_by('id')
        if feat_nn is None:
            _print('Loading features...')
            feats = list(it[::5])
            feat_ids = np.array([f.id for f in feats])
            feat_vectors = [f.load_features() for f in feats]
            X = np.vstack(feat_vectors)
            _print('Constructing KNN tree...')
            feat_nn = NearestNeighbors().fit(X)
            _print('Done!')

        # Erase distances from previous computation
        prev = list(cls.objects.filter(distto__isnull=False))
        for feat in prev:
            feat.distto = None
        cls.objects.bulk_update(prev)

        dists, indices = feat_nn.kneighbors([cls.objects.get(face=inst_id).load_features()], 1000)

        for dist, feat_id in zip(dists[0], feat_ids[indices[0]]):
            feat = cls.objects.get(id=feat_id)
            feat.distto = dist
            feat.save()

    class Meta:
        abstract = True


class Pose(models.Model):
    keypoints = models.BinaryField()

    def _format_keypoints(self):
        kp = np.frombuffer(self.keypoints, dtype=np.float32)
        return kp.reshape((kp.shape[0] / 3, 3))

    POSE_KEYPOINTS = 18
    FACE_KEYPOINTS = 70
    HAND_KEYPOINTS = 21

    Nose = 0
    Neck = 1
    RShoulder = 2
    RElbow = 3
    RWrist = 4
    LShoulder = 5
    LElbow = 6
    LWrist = 7
    RHip = 8
    RKnee = 9
    RAnkle = 10
    LHip = 11
    LKnee = 12
    LAnkle = 13
    REye = 14
    LEye = 15
    REar = 16
    LEar = 17
    Background = 18

    def pose_keypoints(self):
        kp = self._format_keypoints()
        return kp[:self.POSE_KEYPOINTS, :]

    def face_keypoints(self):
        kp = self._format_keypoints()
        return kp[self.POSE_KEYPOINTS:(self.POSE_KEYPOINTS + self.FACE_KEYPOINTS), :]

    def hand_keypoints(self):
        kp = self._format_keypoints()
        base = kp[self.POSE_KEYPOINTS + self.FACE_KEYPOINTS:, :]
        return [base[:self.HAND_KEYPOINTS, :], base[self.HAND_KEYPOINTS:, :]]

    class Meta:
        abstract = True

