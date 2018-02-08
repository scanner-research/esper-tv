from query.datasets.prelude import *
from query.datasets.ingest import ingest, ingest_scanner


def ingestor(video, local_path):
    parts = os.path.splitext(os.path.split(video.path)[1])[0].split('_')
    [channel, date, time] = parts[:3]
    dt = datetime.datetime.strptime('{} {}'.format(date, time), '%Y%m%d %H%M%S')
    if channel[-1] == 'W':
        channel = channel[:-1]
    show = ' '.join(parts[3:-1] if parts[-1] == 'segment' else parts[3:])

    video.time = dt
    video.channel = Channel.objects.get_or_create(name=channel)[0]
    video.show = Show.objects.get_or_create(name=show)[0]


ingest_scanner([s.strip() for s in open('paths').readlines()])
print('Done!')
#ingest([s.strip() for s in open('paths').readlines()], ingestor)
