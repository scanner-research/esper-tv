from query.datasets.prelude import *
from scannerpy.stdlib import pipelines, parsers

LABELER, _ = Labeler.objects.get_or_create(name='tinyfaces')
LABELED_TAG, _ = Tag.objects.get_or_create(name='tinyfaces:labeled')


def face_detect(videos, all_frames, force=False):
    existing_frames = Frame.objects.filter(
        video=videos[0], number__in=all_frames[0], tags=LABELED_TAG).count()
    needed_frames = len(all_frames[0])
    if force or existing_frames != needed_frames:
        log.debug('Faces not cached, missing {}/{} frames'.format(needed_frames - existing_frames,
                                                                  needed_frames))

        def output_name(video, frames):
            return video.path + '_faces_' + str(hash(tuple(frames)))

        with Database() as db:
            ingest_if_missing(db, videos)

            def remove_already_labeled(video, frames):
                already_labeled = set([
                    f['number']
                    for f in Frame.objects.filter(video=video, tags=LABELED_TAG).values('number')
                ])
                return sorted(list(set(frames) - already_labeled))

            filtered_frames = [
                remove_already_labeled(video, vid_frames)
                for video, vid_frames in zip(videos, all_frames)
            ]

            pipelines.detect_faces(db, [db.table(video.path).column('frame') for video in videos],
                                   [db.sampler.gather(vid_frames) for vid_frames in all_frames], [
                                       output_name(video, vid_frames)
                                       for video, vid_frames in zip(videos, filtered_frames)
                                   ])

            for video, video_frames in zip(videos, filtered_frames):
                video_faces = list(
                    db.table(output_name(video, video_frames)).load(
                        ['bboxes'], lambda lst, db: parsers.bboxes(lst[0], db.protobufs)))

                prefetched_frames = list(Frame.objects.filter(video=video).order_by('number'))

                people = []
                tags = []
                for (_, frame_faces), frame_num in zip(video_faces, video_frames):
                    frame = prefetched_frames[frame_num]
                    tags.append(
                        Frame.tags.through(tvnews_frame_id=frame.pk, tvnews_tag_id=LABELED_TAG.pk))
                    for bbox in frame_faces:
                        people.append(Person(frame=frame))
                Frame.tags.through.objects.bulk_create(tags)
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
                Face.objects.filter(
                    person__frame__video=video,
                    person__frame__number__in=vid_frames,
                    labeler=LABELER).select_related('person', 'person__frame')),
            lambda f: f.person.frame.number,
            lambda f: f.id,
            include_frame=False) for video, vid_frames in zip(videos, all_frames)
    ]
