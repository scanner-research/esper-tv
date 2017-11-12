from django.db import models
import base_models as base
import sys
import math
import numpy as np

with base.Dataset('tvnews'):

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

    class Pose(base.Concept):
        keypoints = models.BinaryField()

        def _format_keypoints(self):
            kp = np.frombuffer(self.keypoints, dtype=np.float32)
            return kp.reshape((kp.shape[0]/3, 3))

        POSE_KEYPOINTS = 18
        FACE_KEYPOINTS = 70
        HAND_KEYPOINTS = 21

        def pose_keypoints(self):
            kp = self._format_keypoints()
            return kp[:self.POSE_KEYPOINTS, :]

        def face_keypoints(self):
            kp = self._format_keypoints()
            return kp[self.POSE_KEYPOINTS:(self.POSE_KEYPOINTS+self.FACE_KEYPOINTS), :]

        def hand_keypoints(self):
            kp = self._format_keypoints()
            base = kp[self.POSE_KEYPOINTS+self.FACE_KEYPOINTS:, :]
            return [base[:self.HAND_KEYPOINTS, :], base[self.HAND_KEYPOINTS:, :]]







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
