from django.db import models
from . import base_models as base
import math
import numpy as np
import tempfile
import subprocess as sp

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

    def url(self, duration='1d'):
        fetch_cmd = 'PYTHONPATH=/usr/local/lib/python2.7/dist-packages:$PYTHONPATH gsutil signurl -d {} /app/service-key.json gs://esper/{} ' \
                    .format(duration, self.path)
        url = sp.check_output(fetch_cmd, shell=True).decode('utf-8').split('\n')[1].split('\t')[-1]
        return url


class Tag(models.Model):
    name = base.CharField()


class VideoTag(models.Model):
    video = models.ForeignKey(Video)
    tag = models.ForeignKey(Tag)


class Frame(base.Frame):
    tags = models.ManyToManyField(Tag)
    shot_boundary = models.BooleanField()


class Labeler(base.Labeler):
    data_path = base.CharField(blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True, null=True, blank=True)


Labeled = base.Labeled(Labeler)

class Gender(models.Model):
    name = base.CharField()

Track = base.Track(Labeler)

class Commercial(Track):
    pass


class Topic(models.Model):
    name = base.CharField()


class Segment(Track):
    topics = models.ManyToManyField(Topic)
    polarity = models.FloatField(null=True)
    subjectivity = models.FloatField(null=True)


class Shot(Track):
    in_commercial = models.BooleanField(default=False)


class Pose(Labeled, base.Pose, models.Model):
    frame = models.ForeignKey(Frame)


class Face(Labeled, base.BoundingBox, models.Model):
    frame = models.ForeignKey(Frame)
    shot = models.ForeignKey(Shot, null=True)
    background = models.BooleanField(default=False)
    is_host = models.BooleanField(default=False)
    blurriness = models.FloatField(null=True)
    probability = models.FloatField(default=1.)

    class Meta:
        unique_together = ('labeler', 'frame', 'bbox_x1', 'bbox_x2', 'bbox_y1', 'bbox_y2')


class FaceGender(Labeled, models.Model):
    face = models.ForeignKey(Face)
    gender = models.ForeignKey(Gender)
    probability = models.FloatField(default=1.)

    class Meta:
        unique_together = ('labeler', 'face')


class FaceIdentity(Labeled, models.Model):
    face = models.ForeignKey(Face)
    identity = models.ForeignKey(Identity)
    probability = models.FloatField(default=1.)

    class Meta:
        unique_together = ('labeler', 'face')


class FaceFeatures(Labeled, base.Features, models.Model):
    face = models.ForeignKey(Face)

    class Meta:
        unique_together = ('labeler', 'face')


class ScannerJob(models.Model):
    name = base.CharField()


class Object(base.BoundingBox, models.Model):
    frame = models.ForeignKey(Frame)
    label = models.IntegerField()
    probability = models.FloatField()

class LabeledCommercial(models.Model):
    video = models.ForeignKey(Video)
    start = models.FloatField()
    end = models.FloatField()

class LabeledPanel(models.Model):
    video = models.ForeignKey(Video)
    start = models.FloatField()
    end = models.FloatField()
    num_panelists = models.IntegerField()

class LabeledInterview(models.Model):
    video = models.ForeignKey(Video)
    start = models.FloatField()
    end = models.FloatField()
    interviewer1 = base.CharField(default=None, blank=True, null=True)
    interviewer2 = base.CharField(default=None, blank=True, null=True)
    guest1 = base.CharField(default=None, blank=True, null=True)
    guest2 = base.CharField(default=None, blank=True, null=True)
    original = models.BooleanField(default=True)
    scattered_clips = models.BooleanField(default=False)

class HairColorName(models.Model):
    name = base.CharField(unique=True)

class HairColor(Labeled, models.Model):
    face = models.ForeignKey(Face)
    color = models.ForeignKey(HairColorName)
    
    class Meta:
        unique_together = ('labeler', 'face')
