from django.db import models
import query.base_models as base


class Video(base.Video):
    def get_stride(self):
        return int(math.ceil(self.fps) / 2)


class Frame(base.Frame):
    pass


class Labeler(base.Labeler):
    pass


class PersonTrack(base.Track):
    pass


class Person(base.Noun):
    tracks = base.ManyToManyField(PersonTrack)


class Pose(base.Attribute, base.Pose):
    person = base.ForeignKey(Person)


class Face(base.Attribute, base.BoundingBox):
    person = base.ForeignKey(Person)


class Gender(base.Model):
    name = base.CharField()


class FaceGender(base.Attribute):
    face = base.ForeignKey(Face)
    gender = base.ForeignKey(Gender)


class FaceFeatures(base.Attribute, base.Features):
    face = base.ForeignKey(Face)
