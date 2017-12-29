from query.datasets.prelude import *
from query.datasets.tvnews.embed_kernel import EmbedFaceKernel
from sklearn.neighbors import NearestNeighbors
from scannerpy.stdlib import writers
import cv2

LABELER, _ = Labeler.objects.get_or_create(name='facenet')
FEATURE_DISTANCE_THRESHOLD = 1.0


# Simple K-NN based identity detector
def identity_detect(videos, exemplar, features, force=False):
    log.debug('Loading features')
    ids, vectors = unzip([((i, j, k), f.load_features())
                          for i, vid_features in enumerate(features)
                          for j, frame in enumerate(vid_features) for k, f in enumerate(frame)])

    log.debug('Building k-nn tree')
    feat_nn = NearestNeighbors().fit(np.vstack(vectors))

    log.debug('Computing exemplar features')
    # exemplar_vector = FaceFeatures.objects.get(face__id=119033).load_features()
    if not force and pcache.has(exemplar):
        exemplar_vector = pcache.get(exemplar)
    else:
        img = cv2.imread(exemplar)
        with Database() as db:
            bboxes = [db.protobufs.BoundingBox(x1=0, y1=0, x2=img.shape[1] - 1, y2=img.shape[0] - 1)]
            kernel = EmbedFaceKernel(None, db.protobufs)
            [emb] = kernel.execute(
                [cv2.cvtColor(img, cv2.COLOR_RGB2BGR),
                 writers.bboxes([bboxes], db.protobufs)[0]])
            exemplar_vector = np.frombuffer(emb, dtype=np.float32)
            pcache.set(exemplar, exemplar_vector)

    log.debug('Doing lookup')
    dists, id_indices = feat_nn.kneighbors([exemplar_vector], min(10000, len(vectors)))

    face_map = defaultdict(list)
    for (dist, id_idx) in zip(dists[0], id_indices[0]):
        (i, j, k) = ids[id_idx]
        if dist > FEATURE_DISTANCE_THRESHOLD:
            break

        face_map[videos[i].id].append((features[i][j][k], (j, k)))

    return unzip([unzip(face_map[video.id]) for video in videos])
