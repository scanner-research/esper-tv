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
