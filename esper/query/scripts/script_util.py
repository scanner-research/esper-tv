from scannerpy import ProtobufGenerator, Config, Database, Job
from query.base_models import ModelDelegator
from django.db.models import Min, Max
import os

m = ModelDelegator(os.environ.get('DATASET'))
Video, Frame, Face, FaceInstance, FaceFeatures, Labeler = \
    m.Video, m.Frame, m.Face, m.FaceInstance, m.FaceFeatures, m.Labeler

cfg = Config()
proto = ProtobufGenerator(cfg)
