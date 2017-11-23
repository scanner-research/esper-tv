from django.db import models
import query.base_models as base

class Video(base.Video):
    pass

class Frame(base.Frame):
    pass

class Labeler(base.Labeler):
    pass

class Face(base.Concept):
    pass

class Pose(base.Concept, base.Pose):
    pass

class Gender(base.Model):
    name = base.CharField()
    labeler = base.ForeignKey(Labeler, 'Gender')
    face = base.ForeignKey(Face, 'Gender')
