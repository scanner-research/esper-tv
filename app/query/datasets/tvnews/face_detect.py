from query.datasets.prelude import *
from scannerpy.stdlib import pipelines, parsers

LABELER, _ = Labeler.objects.get_or_create(name='tinyfaces')


def face_detect(videos, all_frames, force=False):
    if force or \
       not Face.objects.filter(person__frame__video=videos[0], labeler=LABELER).exists():

        def output_name(video):
            return video.path + '_boxes_0'

        with Database() as db:
            for video, video_frames in zip(videos, all_frames):
                log.debug(video.path)
                db.ingest_videos([(video.path, video.path)], force=True)

                # TODO(wcrichto): allow frame-specific output name for face pipeline
                # to avoid incorrect caching
                #if not db.has_table(output_name(video)) or force:
                log.debug('Running Scanner face detect job on {} frames'.format(len(video_frames)))
                pipelines.detect_faces(db, [db.table(video.path).column('frame')],
                                       db.sampler.gather(video_frames), video.path)

                video_faces = list(
                    db.table(output_name(video)).load(
                        ['bboxes'], lambda lst, db: parsers.bboxes(lst[0], db.protobufs)))

                prefetched_frames = list(Frame.objects.filter(video=video).order_by('number'))

                people = []
                for (_, frame_faces), frame_num in zip(video_faces, video_frames):
                    frame = prefetched_frames[frame_num]
                    for bbox in frame_faces:
                        people.append(Person(frame=frame))
                Person.objects.bulk_create(people)

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

                print(faces_to_save)
                Face.objects.bulk_create(faces_to_save)
                log.debug('Created {} faces'.format(len(faces_to_save)))

    return [
        group_by_frame(
            list(
                Face.objects.filter(person__frame__video=video, labeler=LABELER)
                .select_related('person', 'person__frame')),
            lambda f: f.person.frame.number,
            lambda f: f.id,
            include_frame=False) for video in videos
    ]
