from scannerpy.stdlib import readers
from scannerpy import Kernel
from carnie_helper import RudeCarnie
import cv2
import struct

model_dir = '/app/deps/rude-carnie/21936'


class GenderKernel(Kernel):
    def __init__(self, config, protobufs):
        self.protobufs = protobufs
        self.rc = RudeCarnie(model_dir=model_dir)

    def execute(self, columns):
        [img, bboxes] = columns
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        [h, w] = img.shape[:2]
        bboxes = readers.bboxes(bboxes, self.protobufs)
        imgs = [img[int(bbox.y1):int(bbox.y2), int(bbox.x1):int(bbox.x2)] for bbox in bboxes]
        genders = self.rc.get_gender_batch(imgs)
        outputs = [struct.pack('=cf', label, score) for [label, score] in genders]
        assert (len(outputs) == len(imgs))
        return [''.join(outputs)]


KERNEL = GenderKernel
