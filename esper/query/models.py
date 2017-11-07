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


with base.Dataset('babycam'):

    class Video(base.Video):
        session_id = models.IntegerField()
        session_name = base.CharField()
        session_date = models.DateField()
        participant_id = models.IntegerField()
        participant_birthdate = models.DateField()
        participant_gender = base.CharField()
        context_setting = base.CharField()
        context_country = base.CharField()
        context_state = base.CharField()

    class Frame(base.Frame):
        pass

    class Labeler(base.Labeler):
        pass

    class Face(base.Concept):
        pass
