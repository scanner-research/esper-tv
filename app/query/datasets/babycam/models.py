from django.db import models
import query.base_models as base
import math

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

    def get_stride(self):
        return int(math.ceil(self.fps)/2)

class Frame(base.Frame):
    pass

class Labeler(base.Labeler):
    pass

class Face(base.Concept):
    pass

class Pose(base.Concept, base.Pose):
    pass
