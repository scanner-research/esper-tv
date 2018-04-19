from query.datasets.prelude import *
import pexpect

DRY_RUN = False


def csv_path(t):
    return 'csv/{}.csv'.format(t)


def export_table(t):
    print(('Exporting table {}'.format(t)))
    p = pexpect.spawn(
        """bash -c "echo 'select * from query_tvnews_{}' | psql -h db esper will -t -F ',' -A > {}""".
        format(t, csv_path(t)),
        timeout=None)
    p.expect('Password for user will: ')
    p.sendline('foobar')
    p.read()


DEFAULT_BATCH_SIZE = 100000


def batch_update(Model, models, batch_size=1000):
    if DRY_RUN: return
    for i in range(0, len(models), batch_size):
        print(('{}/{}'.format(i, len(models) / batch_size)))
        Model.objects.bulk_update(models[i:i + batch_size])


def batch_create(Model, models, batch_size=DEFAULT_BATCH_SIZE):
    if DRY_RUN: return
    for i in range(0, len(models), batch_size):
        Model.objects.bulk_create(models[i:i + batch_size])


def parse_hex(s):
    return s[2:].decode('hex')


class TableLoader:
    def video(self, rows):
        models = []
        for row in rows:
            [id, path, num_frames, fps, width, height, channel, show, dt] = row
            models.append(
                Video(
                    id=int(id),
                    path=path,
                    num_frames=int(num_frames),
                    fps=float(fps),
                    width=int(width),
                    height=int(height),
                    channel=channel,
                    show=show,
                    time=datetime.datetime.strptime(dt, '%Y-%m-%d %H:%M:%S+00')))
        batch_create(Video, models)

    def frame(self, rows):
        models = []
        for row in rows:
            [id, number, _, video] = row
            models.append(Frame(id=int(id), number=int(number), video_id=int(video)))
        batch_create(Frame, models)

    def labeler(self, rows):
        models = []
        for row in rows:
            [id, name] = row
            models.append(Labeler(id=int(id), name=name))
        batch_create(Labeler, models)

    def pose(self, rows):
        people = [Person(frame_id=int(row[6])) for row in rows]
        batch_create(Person, people)

        poses = []
        for i, row in enumerate(rows):
            [
                id, bbox_x1, bbox_x2, bbox_y1, bbox_y2, bbox_score, frame_id, labeler_id, track_id,
                keypoints
            ] = row
            poses.append(
                Pose(
                    id=int(id),
                    keypoints=parse_hex(keypoints),
                    labeler_id=int(labeler_id),
                    person=people[i]))
        batch_create(Pose, poses)

    def gender(self, rows):
        batch_create(Gender, [Gender(id=int(id), name=name) for [id, name] in rows])

    def facetrack(self, rows):
        models = []
        labeler, _ = Labeler.objects.get_or_create(name='featuretrack')
        for row in rows:
            [id, gender_id, identity_id, max_frame, min_frame, video_id] = row
            models.append(
                PersonTrack(
                    id=int(id),
                    video_id=int(video_id),
                    min_frame=int(min_frame),
                    labeler=labeler,
                    max_frame=int(max_frame)))
        batch_create(PersonTrack, models)

    def face(self, rows):
        people = [Person(frame_id=int(row[2])) for row in rows]
        batch_create(Person, people)

        faces = []
        genders = []
        for i, row in enumerate(rows):
            [
                id, track_id, frame_id, labeler_id, bbox_score, bbox_x1, bbox_x2, bbox_y1, bbox_y2,
                gender_id, identity_id
            ] = row
            genders.append(int(gender_id))
            people[i].tracks.add(track_id)
            faces.append(
                Face(
                    id=int(id),
                    bbox_x1=float(bbox_x1),
                    bbox_x2=float(bbox_x2),
                    bbox_y1=float(bbox_y1),
                    bbox_y2=float(bbox_y2),
                    bbox_score=float(bbox_score),
                    labeler_id=int(labeler_id),
                    person=people[i]))
        batch_update(Person, people)
        batch_create(Face, faces)

        gender_labeler, _ = Labeler.objects.get_or_create(name='rudecarnie')

        batch_create(FaceGender, [
            FaceGender(face=face, gender_id=gender_id, labeler=gender_labeler)
            for face, gender_id in zip(faces, genders)
        ])

    def facefeatures(self, rows):
        batch_create(FaceFeatures, [
            FaceFeatures(
                id=int(id),
                features=parse_hex(features),
                face_id=int(face_id),
                labeler_id=int(labeler_id)) for [id, features, face_id, labeler_id, _] in rows
        ])


tables = [
    # 'Video',
    # 'Frame',
    # 'Labeler',
    'Pose',
    # 'Gender',
    'FaceTrack',
    'Face',
    'FaceFeatures',
]

for t in tables:
    print(('Loading table {}'.format(t)))
    path = csv_path(t.lower())
    if not os.path.isfile(path):
        export_table(t.lower())

    if DRY_RUN:
        with open(path) as f:
            lines = []
            while len(lines) < 10:
                try:
                    lines.append(next(f))
                except StopIteration:
                    break
    else:
        lines = open(path).readlines()

    print('Creating rows')
    rows = [s.strip().split(',') for s in lines]
    loader = TableLoader()
    getattr(loader, t.lower())(rows)
