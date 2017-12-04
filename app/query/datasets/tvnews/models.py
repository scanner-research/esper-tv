from django.db import models
import query.base_models as base
import math
import numpy as np

class Video(base.Video):
    channel = base.CharField()
    show = base.CharField()
    time = models.DateTimeField()

    def get_stride(self):
        return int(math.ceil(self.fps)/2)

class Frame(base.Frame):
    pass

class Labeler(base.Labeler):
    pass

class Identity(base.Model):
    name = base.CharField()

class Gender(base.Model):
    name = base.CharField()

class CommercialTrack(base.Track):
    pass

class Commercial(base.Noun):
    tracks = base.ManyToManyField(CommercialTrack)

class PersonTrack(base.Track):
    pass

class Person(base.Noun):
    tracks = base.ManyToManyField(PersonTrack)

class IdentityLabel(base.Attribute):
    person = base.ForeignKey(Person)
    identity = base.ForeignKey(Identity)

class Pose(base.Attribute, base.Pose):
    person = base.ForeignKey(Person)

class Face(base.Attribute, base.BoundingBox):
    person = base.ForeignKey(Person)

class FaceGender(base.Attribute):
    face = base.ForeignKey(Face)
    gender = base.ForeignKey(Gender)

class FaceFeatures(base.Attribute, base.Features):
    face = base.ForeignKey(Face)
