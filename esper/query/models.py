from django.db import models
import base_models as base

# TODO(wcrichto): can we auto-generate *Instance and *Feature classes?

##### Specializations of base models


class Video(base.VideoBase):
    station = base.CharField()
    show = base.CharField()


class Frame(base.FrameBase(Video)):
    pass


class Labeler(base.LabelerBase):
    pass


def InstanceBase(Concept):
    return base.InstanceBase(Frame, Labeler, Concept)


def FeaturesBase(Instance):
    return base.FeaturesBase(Labeler, Instance)


##### App-specific models


class Identity(models.Model):
    name = base.CharField()


class Gender(models.Model):
    name = base.CharField()


class Face(base.ConceptBase):
    gender = models.ForeignKey(Gender, null=True, blank=True)
    identity = models.ForeignKey(Identity, null=True, blank=True)
    labeler = models.ForeignKey(Labeler, null=True, blank=True)

class FaceInstance(InstanceBase(Face)):
    pass


class FaceFeatures(FeaturesBase(FaceInstance)):
    pass


class Commercial(base.ConceptBase):
    pass


class CommercialInstance(InstanceBase(Commercial)):
    pass
