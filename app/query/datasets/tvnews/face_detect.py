from query.datasets.prelude import *
from scannerpy.stdlib import pipelines, parsers

LABELER, _ = Labeler.objects.get_or_create(name='tinyfaces')


def face_detect(videos, all_frames, force=False):
    if not force and Face.objects.filter(
            person__frame__video=videos[0], labeler=LABELER).exists():
        return [
            list(
                Face.objects.filter(person__frame__video=video, labeler=LABELER).order_by('id')
                .select_related('person', 'person__frame')) for video in videos
        ]

    def output_name(video):
        return video.path + '_boxes_0'

    with Database() as db:
        all_faces = []

        for video, video_frames in zip(videos, all_frames):
            log.debug(video.path)
            db.ingest_videos([(video.path, video.path)], force=True)

            if not db.has_table(output_name(video)) or force:
                log.debug('Running Scanner face detect job')
                pipelines.detect_faces(db, [db.table(video.path).column('frame')],
                                       db.sampler.gather(video_frames), video.path)

            video_faces = list(db.table(output_name(video)).load(
                ['bboxes'], lambda lst, db: parsers.bboxes(lst[0], db.protobufs)))

            prefetched_frames = list(Frame.objects.filter(video=video).order_by('number'))

            log.debug('Creating people')
            people = []
            for (_, frame_faces), frame_num in zip(video_faces, video_frames):
                frame = prefetched_frames[frame_num]
                for bbox in frame_faces:
                    people.append(Person(frame=frame))
            Person.objects.bulk_create(people)

            log.debug('Creating faces')
            faces_to_save = []
            p_idx = 0
            for (_, frame_faces), frame_num in zip(video_faces, video_frames):
                for bbox in frame_faces:
                    faces_to_save.append(
                        Face(
                            person=people[p_idx],
                            bbox_x1=bbox.x1 / video.width,
                            bbox_x2=bbox.x2 / video.width,
                            bbox_y1=bbox.y1 / video.height,
                            bbox_y2=bbox.y2 / video.height,
                            bbox_score=bbox.score,
                            labeler=LABELER))
                    p_idx += 1

            log.debug('Creating {} faces'.format(len(faces_to_save)))
            Face.objects.bulk_create(faces_to_save)
            all_faces.append(faces_to_save)

        return all_faces
