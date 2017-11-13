from query.datasets.prelude import *
import requests
import cv2
import shlex
import math

ESPER_ENV = os.environ.get('ESPER_ENV')
BUCKET = os.environ.get('BUCKET')
DATASET = os.environ.get('DATASET')

def run(s, shell=False, output=False):
    if shell == True:
        return sp.check_output(s, shell=True)
    elif output == True:
        return sp.check_output(shlex.split(s))
    else:
        return sp.check_call(shlex.split(s))


def get_dimensions(path):
    cmd = 'ffprobe -v error -show_entries stream=width,height -of default=noprint_wrappers=1 "{}"'
    s = run(cmd.format(path), output=True).split("\n")
    if s[0].split("=")[1] == "N/A":
        width = int(s[2].split("=")[1])
        height = int(s[3].split("=")[1])
    else:
        width = int(s[0].split("=")[1])
        height = int(s[1].split("=")[1])
    return width, height


def get_fps(path):
    cmd = 'ffmpeg -i "{}" 2>&1 | sed -n "s/.*, \\(.*\\) fp.*/\\1/p"'
    return float(run(cmd.format(path), shell=True, output=True))


def get_num_frames(path):
    cmd = '''
    ffprobe -v error -count_frames -select_streams v:0 \
      -show_entries stream=nb_read_frames -of default=nokey=1:noprint_wrappers=1 \
      "{}"'''
    return int(run(cmd.format(path), output=True))


def make_thumbnail(video, db):
    indices = [int(n * video.num_frames) for n in [0.1, 0.35, 0.60, 0.85]]
    table = db.table(video.path)
    frames = [f[0] for _, f in table.load([1], rows=indices)]
    img = make_montage(len(frames), iter(frames), frame_width=150, frames_per_row=2)
    run('mkdir -p assets/thumbnails')
    cv2.imwrite('assets/thumbnails/{}.jpg'.format(video.id), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))


def extract_audio(video):
    sp.check_call(['mkdir', '-p', 'assets/audio'])
    cmd = 'ffmpeg -y -i "{}" -c:a copy "assets/audio/{}.aac"'.format(video.path, video.id)
    run(cmd)


def save_frames(video):
    stride = int(math.ceil(video.fps) / 2)
    ids = [
        str(f['id'])
        for f in Frame.objects.filter(video=video, number__in=range(0, video.num_frames, stride))
        .order_by('number').values('id')
    ]
    requests.post(
        'http://localhost:8000/batch_fallback', data={'frames': ','.join(ids),
                                                      'dataset': DATASET})


def ingest(paths, fun, dry_run=False):
    if not dry_run:
        with Database() as db:
            print 'Ingesting videos into Scanner...'
            tables, failed = db.ingest_videos([(p, p) for p in paths], force=True)
            for path, _ in failed:
                paths.remove(path)
            print('Scanner failed on: ', failed)
            all_num_frames = [table.num_rows() for table in tables]
    else:
        all_num_frames = [0 for _ in range(len(paths))]

    for num_frames, path in zip(all_num_frames, paths):
        try:
            if ESPER_ENV == 'google':
                _, filename = os.path.split(path)
                local_path = '/tmp/{}'.format(filename)
                run('gsutil cp gs://{}/{} {}'.format(BUCKET, path, local_path))
            else:
                local_path = path

            video = Video()
            video.path = path
            video.num_frames = num_frames
            video.fps = get_fps(local_path)
            width, height = get_dimensions(local_path)
            video.width = width
            video.height = height

            fun(video, local_path)

            video.save()

            if not dry_run:
                frames = [Frame(number=i, video=video) for i in range(video.num_frames)]
                Frame.objects.bulk_create(frames)

                save_frames(video)

        except:
            Video.objects.filter(path=path).delete()
            raise

        finally:
            if ESPER_ENV == 'google':
                run('rm {}'.format(local_path))
