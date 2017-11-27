from query.datasets.prelude import *
import os

paths = ['FOXNEWSW_20160919_230000_On_the_Record_With_Brit_Hume.mp4', 'FOXNEWS_20120724_210000_The_Five.mp4']

for path in paths:
    faces = Face.objects.filter(frame__video__path__contains=path, labeler__name='mtcnn') \
                        .select_related('frame') \
                        .order_by('frame__number')
    bboxes = np.vstack([np.hstack([[f.frame.number], f.bbox_to_numpy()]) for f in faces])
    pd.DataFrame(bboxes).to_csv("{}.csv".format(os.path.splitext(path)[0]), index=False, header=False)
