from sklearn.neighbors import NearestNeighbors
from django.db import models, connection
from django.db.models import F, ExpressionWrapper
from django.db.models.base import ModelBase
from django.db.models.functions import Cast
from django_bulk_update.manager import BulkUpdateManager
from scannerpy import ProtobufGenerator, Config
import sys
import numpy as np
import json
import warnings

MAX_STR_LEN = 256

current_dataset = None
datasets = {}


def _print(args):
    print(args)
    sys.stdout.flush()


def CharField(*args, **kwargs):
    return models.CharField(*args, max_length=MAX_STR_LEN, **kwargs)


class ForeignKey(object):
    def __init__(self, model, on_delete=models.CASCADE, **kwargs):
        self._make_key = lambda name: models.ForeignKey(model, related_query_name=name.lower(), on_delete=on_delete, **kwargs)


class ManyToManyField(object):
    def __init__(self, model, **kwargs):
        self._make_key = lambda name: models.ManyToManyField(model, related_query_name=name.lower(), **kwargs)


class Dataset(object):
    def __init__(self, name):
        self.name = name
        self.models = []
        if name not in datasets:
            datasets[name] = self

    def __enter__(self):
        global current_dataset
        current_dataset = datasets[self.name]

    def __exit__(self, type, val, traceback):
        global current_dataset
        current_dataset = None

    def register_model(self, name, cls):
        self.models.append(name)
        setattr(self, name, cls)

    def all_models(self):
        return self.models


class DatasetMeta(ModelBase):
    def __new__(cls, name, bases, attrs):
        global current_dataset
        primary_base = bases[0]
        mixins = bases[1:]

        # Don't modify base models (i.e. the ones in this file)
        if current_dataset is None:
            # Don't create a table for base models
            class Meta:
                abstract = True

            attrs['Meta'] = Meta
            attrs['objects'] = BulkUpdateManager()
            return super(DatasetMeta, cls).__new__(cls, name, bases, attrs)

        # Model-specific fields
        if primary_base is Frame:
            attrs['video'] = ForeignKey(current_dataset.Video)

            class Meta:
                unique_together = ('video', 'number')

            attrs['Meta'] = Meta

        if primary_base is Noun:
            attrs['frame'] = ForeignKey(current_dataset.Frame)

        elif primary_base is Attribute:
            attrs['labeler'] = ForeignKey(current_dataset.Labeler)

        elif primary_base is Track:
            attrs['video'] = ForeignKey(current_dataset.Video)
            attrs['labeler'] = ForeignKey(current_dataset.Labeler)

        # Add mixins
        for mixin in mixins:
            for k, v in mixin.__dict__.iteritems():
                if not hasattr(super(mixin), k) and k not in [
                        '__dict__', '__weakref__', '__module__'
                ]:
                    attrs[k] = v

        # Initialize foreign keys with class name
        for key, val in attrs.iteritems():
            if isinstance(val, ForeignKey) or isinstance(val, ManyToManyField):
                attrs[key] = val._make_key(name)

        # Prefix class name with dataset name to avoid clashes across datasets
        namespaced_name = '{}_{}'.format(current_dataset.name, name)

        # Call out to Django ModelBase to create the class/table
        new_cls = super(DatasetMeta, cls).__new__(cls, namespaced_name, tuple(bases), attrs)

        # Remember the created class on our Dataset object
        current_dataset.register_model(name, new_cls)

        return new_cls


class Video(models.Model):
    __metaclass__ = DatasetMeta
    path = CharField(db_index=True)
    num_frames = models.IntegerField()
    fps = models.FloatField()
    width = models.IntegerField()
    height = models.IntegerField()
    has_captions = models.BooleanField(default=False)


class Frame(models.Model):
    __metaclass__ = DatasetMeta
    number = models.IntegerField(db_index=True)


class Labeler(models.Model):
    __metaclass__ = DatasetMeta
    name = CharField()


class Noun(models.Model):
    __metaclass__ = DatasetMeta


class Track(models.Model):
    __metaclass__ = DatasetMeta
    min_frame = models.IntegerField()
    max_frame = models.IntegerField()

    @staticmethod
    def duration_expr():
        return ExpressionWrapper(
            Cast(F('max_frame') - F('min_frame'), models.FloatField()) / F('video__fps'),
            models.FloatField())

    def duration(self):
        return (self.max_frame - self.min_frame) / int(self.video.fps)


class Attribute(models.Model):
    __metaclass__ = DatasetMeta


class Model(models.Model):
    __metaclass__ = DatasetMeta


class BoundingBox(object):
    bbox_x1 = models.FloatField()
    bbox_x2 = models.FloatField()
    bbox_y1 = models.FloatField()
    bbox_y2 = models.FloatField()
    bbox_score = models.FloatField()

    def height(self):
        return self.bbox_y2 - self.bbox_y1

    @staticmethod
    def height_expr():
        return ExpressionWrapper(F('bbox_y2') - F('bbox_y1'), models.FloatField())

    def bbox_to_numpy(self):
        return np.array([self.bbox_x1, self.bbox_x2, self.bbox_y1, self.bbox_y2, self.bbox_score])


feat_nn = None
feat_ids = None


class Features(object):
    features = models.BinaryField()
    distto = models.FloatField(null=True)

    def load_features(self):
        return np.array(json.loads(str(self.features)))

    @classmethod
    def compute_distances(cls, inst_id):
        global feat_nn
        global feat_ids

        it = cls.objects.annotate(height=F('face__bbox_y2') - F('face__bbox_y1')).filter(
            height__gte=0.1)
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


class Pose(object):
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


class ModelDelegator:
    def __init__(self, name=None):
        if name is not None:
            self._dataset = datasets[name]

    def datasets(self):
        return datasets

    def import_all(self, globals_):
        for model in self._dataset.all_models():
            globals_[model] = getattr(self, model)

    def __getattr__(self, k):
        return getattr(self._dataset, k)
