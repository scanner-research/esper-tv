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


class Identity(base.Model):
    name = base.CharField()


class Gender(base.Model):
    name = base.CharField()


class Topic(base.Model):
    name = base.CharField()


class TopicTrack(base.Track):
    topic = base.ForeignKey(Topic)


class Commercial(base.Track):
    pass


class ThingType():
    TOPIC = 1
    PHRASE = 2
    PERSON = 3
    LOCATION = 4
    ORGANIZATION = 5


class Thing(base.Model):
    name = base.CharField()
    type = models.IntegerField()

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


class IdentityLabel(base.Attribute):
    person = base.ForeignKey(Person)
    identity = base.ForeignKey(Identity)


class Pose(base.Attribute, base.Pose):
    person = base.ForeignKey(Person)

    class Meta:
        unique_together = ('labeler', 'person')


class Face(base.Attribute, base.BoundingBox):
    person = base.ForeignKey(Person)
    shot = base.ForeignKey(Shot, null=True)

    class Meta:
        unique_together = ('labeler', 'person')


class FaceGender(base.Attribute):
    face = base.ForeignKey(Face)
    gender = base.ForeignKey(Gender)

    class Meta:
        unique_together = ('labeler', 'face')


class FaceFeatures(base.Attribute, base.Features):
    face = base.ForeignKey(Face)

    class Meta:
        unique_together = ('labeler', 'face')
