from django.db import models
from . import base_models as base
import math
import numpy as np
import tempfile


class Identity(models.Model):
    name = base.CharField()


class CanonicalShow(models.Model):
    name = base.CharField()
    is_recurring = models.BooleanField(default=False)
    hosts = models.ManyToManyField(Identity, blank=True)


class Show(models.Model):
    name = base.CharField()
    hosts = models.ManyToManyField(Identity, blank=True)
    canonical_show = models.ForeignKey(CanonicalShow)


class Channel(models.Model):
    name = base.CharField()


class Video(base.Video):
    channel = models.ForeignKey(Channel)
    show = models.ForeignKey(Show)
    time = models.DateTimeField()
    commercials_labeled = models.BooleanField(default=False)
    srt_extension = base.CharField()
    threeyears_dataset = models.BooleanField(default=False)

    def get_stride(self):
        return int(math.ceil(self.fps) / 2)

    def item_name(self):
        return '.'.join(self.path.split('/')[-1].split('.')[:-1])


class Tag(models.Model):
    name = base.CharField()


class VideoTag(models.Model):
    video = models.ForeignKey(Video)
    tag = models.ForeignKey(Tag)


class Frame(base.Frame):
    tags = models.ManyToManyField(Tag)


class Labeler(base.Labeler):
    data_path = base.CharField(blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True, null=True, blank=True)


class Gender(models.Model):
    name = base.CharField()


class Commercial(base.Track):
    pass


class Topic(models.Model):
    name = base.CharField()


class Segment(base.Track):
    topics = models.ManyToManyField(Topic)
    polarity = models.FloatField(null=True)
    subjectivity = models.FloatField(null=True)


class Shot(base.Track):
    in_commercial = models.BooleanField(default=False)


class Person(base.Noun):
    pass


class Pose(base.Pose, base.Attribute):
    person = models.ForeignKey(Person)

    class Meta:
        unique_together = ('labeler', 'person')


class Face(base.Attribute, base.BoundingBox):
    person = models.ForeignKey(Person)
    shot = models.ForeignKey(Shot, null=True)
    background = models.BooleanField(default=False)
    is_host = models.BooleanField(default=False)
    blurriness = models.FloatField(null=True)
    probability = models.FloatField(default=1.)

    class Meta:
        unique_together = ('labeler', 'person')


class FaceGender(base.Attribute):
    face = models.ForeignKey(Face)
    gender = models.ForeignKey(Gender)
    probability = models.FloatField(default=1.)

    class Meta:
        unique_together = ('labeler', 'face')


class FaceIdentity(base.Attribute):
    face = models.ForeignKey(Face)
    identity = models.ForeignKey(Identity)
    probability = models.FloatField(default=1.)

    class Meta:
        unique_together = ('labeler', 'face')


class FaceFeatures(base.Attribute, base.Features):
    face = models.ForeignKey(Face)

    class Meta:
        unique_together = ('labeler', 'face')


class ScannerJob(models.Model):
    name = base.CharField()


class Object(base.Noun, base.BoundingBox):
    label = models.IntegerField()
    probability = models.FloatField()
