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
    talking_heads = models.BooleanField(default=False)

class Labeler(base.Labeler):
    pass

class Identity(base.Model):
    name = base.CharField()

class Gender(base.Model):
    name = base.CharField()

class Face(base.Concept):
    gender = models.ForeignKey(Gender, on_delete=models.CASCADE, null=True, blank=True)
    identity = models.ForeignKey(Identity, on_delete=models.CASCADE, null=True, blank=True)

class Pose(base.Concept, base.Pose):
    pass
