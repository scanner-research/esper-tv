from django.db import models
from scannerpy import ProtobufGenerator, Config

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
        v.ParseFromString(value)
        return v

    def deconstruct(self):
        name, path, args, kwargs = super(ProtoField, self).deconstruct()
        return name, path, [self._proto] + args, kwargs


def CharField():
    return models.CharField(max_length=MAX_STR_LEN)


class VideoBase(models.Model):
    path = CharField()
    num_frames = models.IntegerField()
    fps = models.IntegerField()
    width = models.IntegerField()
    height = models.IntegerField()
    timestamp = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True


def FrameBase(Video):
    class FrameBase(models.Model):
        number = models.IntegerField()
        video = models.ForeignKey(Video)

        class Meta:
            abstract = True

    return FrameBase


class ConceptBase(models.Model):
    class Meta:
        abstract = True


def InstanceBase(Frame, Labeler, Concept):
    class InstanceBase(models.Model):
        bbox = ProtoField(proto.BoundingBox)
        frame = models.ForeignKey(Frame)
        labeler = models.ForeignKey(Labeler)
        concept = models.ForeignKey(Concept, null=True, blank=True)

        class Meta:
            abstract = True

    return InstanceBase


def FeaturesBase(Labeler, Instance):
    class FeaturesBase(models.Model):
        features = models.BinaryField()
        labeler = models.ForeignKey(Labeler)
        instance = models.ForeignKey(Instance)

        class Meta:
            abstract = True

    return FeaturesBase


class LabelerBase(models.Model):
    name = CharField()

    class Meta:
        abstract = True
