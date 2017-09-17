from scannerpy import ProtobufGenerator, Config, Database, Job
from query.base_models import ModelDelegator
from django.db.models import Min, Max

m = ModelDelegator('krishna')
Video, Frame, Face, FaceInstance, PersonInstance, Labeler = \
    m.Video, m.Frame, m.Face, m.FaceInstance, m.PersonInstance, m.Labeler

cfg = Config()
proto = ProtobufGenerator(cfg)
