from query.scripts.prelude import *
from query.scripts.ingest import ingest

def ingestor(video, local_path):
    parts = os.path.splitext(os.path.split(video.pathpath)[1])[0].split('_')
    [channel, date, time] = parts[:3]
    dt = datetime.strptime('{} {}'.format(date, time), '%Y%m%d %H%M%S')
    if channel[-1] == 'W':
        channel = channel[:-1]
    show = ' '.join(parts[3:-1] if parts[-1] == 'segment' else parts[3:])

    video.channel = channel
    video.show = show

ingest([s.strip() for s in open('paths').readlines()], ingestor)
