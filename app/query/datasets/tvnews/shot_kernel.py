from scannerpy import Kernel

class ShotDetectionKernel(Kernel):
    def __init__(self, config, protobufs):
        pass

    def close(self):
        pass

    def execute(self, input_columns):
        print(len(input_columns[0]))
        return ['']

KERNEL = ShotDetectionKernel
