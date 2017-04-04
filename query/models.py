from django.db import models
import numpy as np
from scannerpy import ProtobufGenerator, Config

cfg = Config()
proto = ProtobufGenerator(cfg)


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


class Video(models.Model):
    path = models.CharField(max_length=256)
    num_frames = models.IntegerField()
    fps = models.FloatField()
    width = models.IntegerField()
    height = models.IntegerField()


class Frame(models.Model):
    video = models.ForeignKey(Video)
    number = models.IntegerField()


class Person(models.Model):
    name = models.CharField(max_length=256)


class Face(models.Model):
    frame = models.ForeignKey(Frame)
    person = models.ForeignKey(Person)
    bbox = ProtoField(proto.BoundingBox)
