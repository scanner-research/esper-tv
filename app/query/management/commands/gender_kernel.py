from scannerpy.stdlib import readers
from carnie_helper import RudeCarnie
import scannerpy
import cv2
import struct

model_dir = '/app/deps/rude-carnie/21936'

i = 0


class GenderKernel(scannerpy.Kernel):
    def __init__(self, config, protobufs):
        self.protobufs = protobufs
        self.rc = RudeCarnie(model_dir=model_dir)

    def close(self):
        pass

    def execute(self, columns):
        global i
        [img, bboxes] = columns
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        [h, w] = img.shape[:2]
        bboxes = readers.bboxes(bboxes, self.protobufs)
        imgs = [
            img[int(h * bbox.y1):int(h * bbox.y2),
                int(w * bbox.x1):int(w * bbox.x2)] for bbox in bboxes
        ]
        for img in imgs:
            cv2.imwrite('/app/tmp/{:05d}.jpg'.format(i), img)
            i += 1
        genders = self.rc.get_gender_batch(imgs)
        outputs = [struct.pack('=cf', label, score) for [label, score] in genders]
        assert (len(outputs) == len(imgs))
        return [''.join(outputs)]


KERNEL = GenderKernel
