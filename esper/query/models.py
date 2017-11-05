from django.db import models
import base_models as base
import sys

with base.Dataset('tvnews'):

    class Video(base.Video):
        channel = base.CharField()
        show = base.CharField()
        time = models.DateTimeField()

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

