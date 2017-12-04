from query.datasets.prelude import *
from query.datasets.ingest import ingest

def ingestor(video, local_path):
    pass

ingest([s.strip() for s in open('paths').readlines()], ingestor)
