from esper.prelude import *
from esper.tvnews.embed_kernel import EmbedFaceKernel
from sklearn.neighbors import NearestNeighbors
from scannerpy.stdlib import writers
import cv2

LABELER, _ = Labeler.objects.get_or_create(name='facenet')
FEATURE_DISTANCE_THRESHOLD = 1.0


# Simple K-NN based identity detector
def identity_detect(videos, exemplar, features, force=False):
    log.debug('Loading features')
    ids, vectors = unzip([((i, j, k), f)
                          for i, vid_features in tqdm(enumerate(features))
                          for j, frame in enumerate(vid_features) for k, f in enumerate(frame)])

    log.debug('Building k-nn tree')
    feat_nn = NearestNeighbors().fit(np.vstack(vectors))

    log.debug('Computing exemplar features')

    def compute_exemplar():
        img = cv2.imread(exemplar)
        with Database() as db:
            bboxes = [db.protobufs.BoundingBox(x1=0, y1=0, x2=img.shape[1], y2=img.shape[0])]
            kernel = EmbedFaceKernel(None, db.protobufs)
            [emb] = kernel.execute(
                [cv2.cvtColor(img, cv2.COLOR_RGB2BGR),
                 writers.bboxes([bboxes], db.protobufs)[0]])
            return np.frombuffer(emb, dtype=np.float32)

    exemplar_vector = pcache.get('exemplar', compute_exemplar, method='pickle', force=force)

    log.debug('Doing lookup')
    dists, id_indices = feat_nn.kneighbors([exemplar_vector], len(vectors))

    face_map = defaultdict(list)
    for q, (dist, id_idx) in enumerate(zip(dists[0], id_indices[0])):
        (i, j, k) = ids[id_idx]
        if dist > FEATURE_DISTANCE_THRESHOLD:
            break

        face_map[i].append((j, k))

    return [face_map[i] for i in range(len(videos))]

    # return unzip([unzip(face_map[video.id]) for video in videos])
