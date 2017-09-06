from query.base_models import ModelDelegator
from django.db.models import Min, Max
m = ModelDelegator('krishna')
Video, Frame, Face, FaceInstance = m.Video, m.Frame, m.Face, m.FaceInstance
