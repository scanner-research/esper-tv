from scannerpy import ProtobufGenerator, Config
from query.base_models import ModelDelegator
from django.db.models import Min, Max

m = ModelDelegator('krishna')
Video, Frame, FaceInstance, PersonInstance, Labeler = \
    m.Video, m.Frame, m.FaceInstance, m.PersonInstance, m.Labeler

cfg = Config()
proto = ProtobufGenerator(cfg)
