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
cfg = Config()
proto = ProtobufGenerator(cfg)
MAX_STR_LEN = 256

class ProtoField(models.BinaryField):
    def __init__(self, proto, *args, **kwargs):
        self._proto = proto
        super(ProtoField, self).__init__(*args, **kwargs)

    def get_prep_value(self, value):
        return value.SerializeToString()

    def from_db_value(self, value, expression, connection, context):
        return self.to_python(value)

    def to_python(self, value):
        v = self._proto()
        try:
            v.ParseFromString(value)
            return v
        except TypeError:
            return None

    def deconstruct(self):
        name, path, args, kwargs = super(ProtoField, self).deconstruct()
        return name, path, [self._proto] + args, kwargs


def CharField(*args, **kwargs):
    return models.CharField(*args, max_length=MAX_STR_LEN, **kwargs)

def _print(args):
    print(args)
    sys.stdout.flush()

current_dataset = None
datasets = {}


class Dataset(object):
    def __init__(self, name):
        self.name = name
        self.concepts = []
        self.other = []
        if name not in datasets:
            datasets[name] = self

    def __enter__(self):
        global current_dataset
        current_dataset = datasets[self.name]

    def __exit__(self, type, val, traceback):
        global current_dataset
        current_dataset = None

    def all_models(self):
        return ['Video', 'Frame', 'Labeler'] + self.other + sum([[c, c + 'Track', c + 'Features']
                                                               for c in self.concepts], [])

def ForeignKey(model, name, on_delete=models.CASCADE, **kwargs):
    return models.ForeignKey(model, related_query_name=name.lower(), on_delete=on_delete, **kwargs)


class BaseMeta(ModelBase):
    def __new__(cls, name, bases, attrs):
        global current_dataset
        base = bases[0]
        is_base_class = base is models.Model or base is object

        if is_base_class:
            if not 'Meta' in attrs:

                class Meta:
                    abstract = True

                attrs['Meta'] = Meta

            attrs['objects'] = BulkUpdateManager()
            child_name = name

        else:
            if base.__name__ == 'Frame':
                attrs['video'] = ForeignKey(current_dataset.Video, name)

                class Meta:
                    unique_together = ('video', 'number')

                attrs['Meta'] = Meta

            child_name = '{}_{}'.format(current_dataset.name, name)

        if base.__name__ != 'Concept':
            new_cls = super(BaseMeta, cls).__new__(cls, child_name, bases, attrs)

        if not is_base_class:
            if base.__name__ == 'Concept':
                new_cls = register_concept(name, attrs, list(bases[1:]))
            elif base.__name__ == 'Model':
                current_dataset.other.append(name)

            setattr(current_dataset, name, new_cls)

        return new_cls


def register_concept(name, attrs, bases):
    global current_datset

    current_dataset.concepts.append(name)

    # Create the ConceptTrack class
    track_cls_name = '{}Track'.format(name)
    track_methods = {
        '__module__': current_dataset.Video.__module__,
        'video': ForeignKey(current_dataset.Video, track_cls_name),
        'min_frame': models.IntegerField(),
        'max_frame': models.IntegerField(),
    }
    track_methods.update(attrs)
    track_cls = type(track_cls_name, (Track, ), track_methods)

    # Create the Concept class
    class Meta:
        unique_together = ('track', 'frame', 'labeler')

    inst_cls_name = name
    inst_methods = {
        '__module__': current_dataset.Video.__module__,
        'track': ForeignKey(track_cls, inst_cls_name, null=True, on_delete=models.SET_NULL),
        'frame': ForeignKey(current_dataset.Frame, inst_cls_name),
        'labeler': ForeignKey(current_dataset.Labeler, inst_cls_name),
        'Meta': Meta
    }
    inst_methods.update(attrs)

    # Multi-class inheritance doesn't seem to work with the Django magic, so we just explicitly
    # copy data members and methods into the derived class.
    for base in bases:
        for k, v in base.__dict__.iteritems():
            if not hasattr(super(base), k) and k not in ['__dict__', '__weakref__', '__module__']:
                inst_methods[k] = v

    inst_cls = type(inst_cls_name, (Instance, ), inst_methods)

    # Create the ConceptFeatures class
    class Meta:
        unique_together = ('labeler', inst_cls_name.lower())

    feat_cls_name = '{}Features'.format(name)
    type(feat_cls_name, (Features, ), {
        '__module__': current_dataset.Video.__module__,
        'labeler': ForeignKey(current_dataset.Labeler, feat_cls_name),
        name.lower(): ForeignKey(inst_cls, feat_cls_name),
        'distto': models.FloatField(null=True),
        'Meta': Meta,
    })

    return inst_cls

class Video(models.Model):
    __metaclass__ = BaseMeta
    path = CharField(db_index=True)
    num_frames = models.IntegerField()
    fps = models.FloatField()
    width = models.IntegerField()
    height = models.IntegerField()


class Frame(models.Model):
    __metaclass__ = BaseMeta
    number = models.IntegerField(db_index=True)

    def save(self, *args, **kwargs):
        self.validate_unique()
        super(Frame, self).save(*args, **kwargs)


class Labeler(models.Model):
    __metaclass__ = BaseMeta
    name = CharField(db_index=True)


class Concept(object):
    __metaclass__ = BaseMeta

class Track(models.Model):
    __metaclass__ = BaseMeta

    @staticmethod
    def duration():
        return ExpressionWrapper(
            Cast(F('max_frame')-F('min_frame'), models.FloatField())/F('video__fps'), 
            models.FloatField())

class Model(models.Model):
    __metaclass__ = BaseMeta

class Instance(models.Model):
    __metaclass__ = BaseMeta

    bbox_x1 = models.FloatField()
    bbox_x2 = models.FloatField()
    bbox_y1 = models.FloatField()
    bbox_y2 = models.FloatField()
    bbox_score = models.FloatField()

    def height(self):
        return self.bbox_y2 - self.bbox_y1

    @staticmethod
    def height_expr():
        return ExpressionWrapper(
            F('bbox_y2') - F('bbox_y1'),
            models.FloatField())

    def save(self, *args, **kwargs):
        self.validate_unique()
        super(Instance, self).save(*args, **kwargs)

    def bbox_to_numpy(self):
        return np.array([self.bbox_x1, self.bbox_x2, self.bbox_y1, self.bbox_y2, self.bbox_score])

    class Meta:
        abstract = True


feat_nn = None
feat_ids = None

class Features(models.Model):
    __metaclass__ = BaseMeta

    features = models.BinaryField()

    def save(self, *args, **kwargs):
        self.validate_unique()
        super(Features, self).save(*args, **kwargs)

    def load_features(self):
        return np.array(json.loads(str(self.features)))

    @classmethod
    def compute_distances(cls, inst_id):
        global feat_nn
        global feat_ids

        it = cls.objects.annotate(height=F('face__bbox_y2')-F('face__bbox_y1')).filter(height__gte=0.2)
        if feat_nn is None:
            _print('Loading features...')
            feats = list(it[::5])
            feat_ids = np.array([f.id for f in feats])
            feat_vectors = [f.load_features() for f in feats]
            X = np.vstack(feat_vectors)
            _print('Constructing KNN tree...')
            feat_nn = NearestNeighbors().fit(X)
            _print('Done!')

        dists, indices = feat_nn.kneighbors([cls.objects.get(face=inst_id).load_features()], 1000)

        for dist, feat_id in zip(dists[0], feat_ids[indices[0]]):
            feat = cls.objects.get(id=feat_id)
            feat.distto = dist
            feat.save()


class Pose(object):
    keypoints = models.BinaryField()

    def _format_keypoints(self):
        kp = np.frombuffer(self.keypoints, dtype=np.float32)
        return kp.reshape((kp.shape[0]/3, 3))

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
        return kp[self.POSE_KEYPOINTS:(self.POSE_KEYPOINTS+self.FACE_KEYPOINTS), :]

    def hand_keypoints(self):
        kp = self._format_keypoints()
        base = kp[self.POSE_KEYPOINTS+self.FACE_KEYPOINTS:, :]
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
