from django.db import models
import query.base_models as base
import math
import numpy as np


class Show(base.Model):
    name = base.CharField()


class Channel(base.Model):
    name = base.CharField()


class Video(base.Video):
    channel = base.ForeignKey(Channel)
    show = base.ForeignKey(Show)
    time = models.DateTimeField()
    commercials_labeled = models.BooleanField(default=False)

    def get_stride(self):
        return int(math.ceil(self.fps) / 2)


class Tag(base.Model):
    name = base.CharField()


class VideoTag(base.Model):
    video = base.ForeignKey(Video)
    tag = base.ForeignKey(Tag)


class Frame(base.Frame):
    tags = base.ManyToManyField(Tag)


class Labeler(base.Labeler):
    pass


class Gender(base.Model):
    name = base.CharField()


class Commercial(base.Track):
    pass


class ThingType(base.Model):
    name = base.CharField()


class Thing(base.Model):
    name = base.CharField()
    type = base.ForeignKey(ThingType)

    class Meta:
        unique_together = ('name', 'type')


class Segment(base.Track):
    things = base.ManyToManyField(Thing)
    polarity = models.FloatField(null=True)
    subjectivity = models.FloatField(null=True)


class Shot(base.Track):
    in_commercial = models.BooleanField(default=False)


class PersonTrack(base.Track):
    pass


class Person(base.Noun):
    tracks = base.ManyToManyField(PersonTrack)


class Pose(base.Attribute, base.Pose):
    person = base.ForeignKey(Person)

    class Meta:
        unique_together = ('labeler', 'person')


class Face(base.Attribute, base.BoundingBox):
    person = base.ForeignKey(Person)
    shot = base.ForeignKey(Shot, null=True)
    background = models.BooleanField(default=False)

    class Meta:
        unique_together = ('labeler', 'person')


class FaceGender(base.Attribute):
    face = base.ForeignKey(Face)
    gender = base.ForeignKey(Gender)

    class Meta:
        unique_together = ('labeler', 'face')


class FaceIdentity(base.Attribute):
    face = base.ForeignKey(Face)
    identity = base.ForeignKey(Thing)

    class Meta:
        unique_together = ('labeler', 'face')


class FaceFeatures(base.Attribute, base.Features):
    face = base.ForeignKey(Face)

    class Meta:
        unique_together = ('labeler', 'face')
