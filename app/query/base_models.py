from sklearn.neighbors import NearestNeighbors
from django.db import models, connection, connections
from django.db.models import F, ExpressionWrapper
from django.db.models.base import ModelBase
from django.db.models.functions import Cast
from django.db.models.query import QuerySet
from django_bulk_update.manager import BulkUpdateManager
import sys
import numpy as np
import json
import warnings
import os
import subprocess as sp
import sqlparse
import subprocess as sp
import csv

MAX_STR_LEN = 256


class QuerySetMixin(object):
    def explain(self):
        # TODO(wcrichto): doesn't work for queries with strings
        cursor = connections[self.db].cursor()
        cursor.execute('EXPLAIN ANALYZE %s' % str(self.query))
        print(("\n".join(([t for (t, ) in cursor.fetchall()]))))

    def print_sql(self):
        q = str(self.query)
        print((sqlparse.format(q, reindent=True)))

    def exists(self):
        try:
            next(self.iterator())
            return True
        except StopIteration:
            return False

    def values_with(self, *fields):
        return self.values(*([f.name for f in self.model._meta.get_fields()] + list(fields)))

    def save_to_csv(self, name):
        meta = self.model._meta
        with connection.cursor() as cursor:
            cursor.execute("COPY ({}) TO '{}' CSV DELIMITER ',' HEADER".format(
                str(self.query), '/app/pg/{}.csv'.format(name)))


for key in QuerySetMixin.__dict__:
    if key[:2] == '__':
        continue

    setattr(QuerySet, key, QuerySetMixin.__dict__[key])


def _print(args):
    print(args)
    sys.stdout.flush()


def bulk_create_copy(self, objects, keys, table=None):
    meta = self.model._meta
    fname = '/app/rows.csv'
    log.debug('Creating CSV')
    with open(fname, 'w') as f:
        writer = csv.writer(f, delimiter=',')
        writer.writerow(keys)
        max_id = self.all().aggregate(Max('id'))['id__max']
        id = max_id + 1 if max_id is not None else 0
        for obj in tqdm(objects):
            if table is None:
                obj['id'] = id
                id += 1
            writer.writerow([obj[k] for k in keys])

    log.debug('Writing to database')
    print(sp.check_output("""
    echo "\copy {table} FROM '/app/rows.csv' WITH DELIMITER ',' CSV HEADER;" | psql -h db esper will
    """.format(table=table or meta.db_table),
        shell=True))

    # with connection.cursor() as cursor:
    #     cursor.execute("COPY {} ({}) FROM '{}' DELIMITER ',' CSV HEADER".format(
    #         table or meta.db_table, ', '.join(keys), fname))
    #     if table is None:
    #         cursor.execute("SELECT setval('{}_id_seq', {}, false)".format(table, id))

    # os.remove(fname)
    log.debug('Done!')


def model_repr(model):
    def field_repr(field):
        return '{}: {}'.format(field.name, getattr(model, field.name))

    return '{}({})'.format(
        model.__class__.__name__,
        ', '.join([
            field_repr(field) for field in model._meta.get_fields(include_hidden=False)
            if not field.is_relation
        ]))


models.Model.__repr__ = model_repr


def model_defaults(Model):
    from django.db.models.fields import NOT_PROVIDED
    return {
        f.name: f.default
        for f in Model._meta.get_fields()
        if hasattr(f, 'default') and f.default is not NOT_PROVIDED
    }


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


def Track(Labeler):
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
    return Track


def Labeled(Labeler):
    class Labeled(models.Model):
        labeler = models.ForeignKey(Labeler)

        class Meta:
            abstract = True
    return Labeled


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
