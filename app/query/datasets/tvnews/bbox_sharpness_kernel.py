import scannerpy
import cv2
import scannerpy.stdlib.readers as readers
import json


class BBoxSharpness(scannerpy.Kernel):
    def __init__(self, config, protobufs):
        self.config = config
        self.protobufs = protobufs

    def execute(self, columns):
        [frame, bboxes] = columns
        bboxes = readers.bboxes(bboxes, self.protobufs)

        if len(bboxes) == 0:
            return []

        results = []
        for bbox in bboxes:
            img = frame[int(bbox.y1):int(bbox.y2), int(bbox.x1):int(bbox.x2), :]
            img = cv2.resize(img, (200, 200))
            results.append(cv2.Laplacian(img, cv2.CV_64F).var())

        return [json.dumps(results)]


KERNEL = BBoxSharpness
