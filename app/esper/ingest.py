from esper.prelude import *
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


def ingest_scanner(paths):
    with Database() as db:
        print('Ingesting videos into Scanner...')
        tables, failed = db.ingest_videos([(p, p) for p in paths], force=True)
        for path, _ in failed:
            paths.remove(path)
        print(('Scanner failed on: ', failed))
        return paths


def ingest(paths, fun, dry_run=False):
    if not dry_run:
        with Database() as db:
            all_num_frames = [db.table(p).num_rows() for p in paths if db.has_table(p)]
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

        except:
            Video.objects.filter(path=path).delete()
            raise

        finally:
            if ESPER_ENV == 'google':
                run('rm {}'.format(local_path))


def ingest_pose(video, table, frame_numbers):
    kp_size = (Pose.POSE_KEYPOINTS + Pose.FACE_KEYPOINTS + 2 * Pose.HAND_KEYPOINTS) * 3
    poses = []
    frames = list(Frame.objects.filter(video=video).order_by('number'))
    pose_labeler, _ = Labeler.objects.get_or_create(name='openpose')
    for (_, buf), frame_number in zip(table.column('pose').load(), frame_numbers):
        if len(buf) == 1: continue
        frame = frames[frame_number]
        all_kp = np.frombuffer(buf, dtype=np.float32)
        for j in range(0, len(all_kp), kp_size):
            person = Person(frame=frame)
            person.save()

            pose = Pose(
                keypoints=all_kp[j:(j + kp_size)].tobytes(), labeler=pose_labeler, person=person)

            # Estimate bounding box
            p = pose.pose_keypoints()
            l = p[16, :2]
            r = p[17, :2]
            o = p[0, :2]
            up = o + [r[1] - l[1], l[0] - r[0]]
            down = o + [l[1] - r[1], r[0] - l[0]]
            face = np.array([l, r, up, down])

            xmin = face[:, 0].min()
            xmax = face[:, 0].max()
            ymin = face[:, 1].min()
            ymax = face[:, 1].max()

            pose.bbox_x1 = xmin
            pose.bbox_x2 = xmax
            pose.bbox_y1 = ymin
            pose.bbox_y2 = ymax
            pose.bbox_score = min(p[16, 2], p[17, 2], p[0, 2])

            poses.append(pose)

    Pose.objects.bulk_create(poses)



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


# ingest_scanner([s.strip() for s in open('paths').readlines()])
# print('Done!')
# #ingest([s.strip() for s in open('paths').readlines()], ingestor)
