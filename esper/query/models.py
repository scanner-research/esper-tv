from django.db import models
import base_models as base
import sys

with base.Dataset('tvnews'):

    class Video(base.Video):
        station = base.CharField()
        show = base.CharField()

    class Frame(base.Frame):
        pass

    class Labeler(base.Labeler):
        pass

    class Identity(base.Model):
        name = base.CharField()

    class Gender(base.Model):
        name = base.CharField()

    class Face(base.Concept):
        gender = models.ForeignKey(Gender, null=True, blank=True)
        identity = models.ForeignKey(Identity, null=True, blank=True)


with base.Dataset('krishna'):

    class Video(base.Video):
        station = base.CharField()
        show = base.CharField()

    class Frame(base.Frame):
        pass

    class Labeler(base.Labeler):
        pass

    class Face(base.Concept):
        pass
