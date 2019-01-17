import os
import numpy as np
from rs_embed import EmbeddingData

EMB_DIR = '/app/data/embs'
EMB_PATH = os.path.join(EMB_DIR, 'face_embs.bin')
ID_PATH = os.path.join(EMB_DIR, 'face_ids.bin')
EMB_DIM = 128


def _load():
    id_file_size = os.path.getsize(ID_PATH)
    assert id_file_size % 8 == 0, \
        'Id file size is not a multiple of sizeof(u64)'
    n = int(id_file_size / 8)
    emb_file_size = os.path.getsize(EMB_PATH)
    assert emb_file_size % 4 == 0, \
        'Embedding file size is a multiple of sizeof(f32)'
    d = int((emb_file_size / 4) / (id_file_size / 8))
    assert emb_file_size % d == 0, \
        'Embedding file size is a multiple of d={}'.format(d)
    emb_data = EmbeddingData(ID_PATH, EMB_PATH, EMB_DIM)
    assert emb_data.count() == n, \
        'Count does not match expected: {} != {}'.format(n, emb_data.count())
    return emb_data


_EMB_DATA = _load()


def get(ids):
    """List of face ids -> List of pairs (id, embedding)"""
    return _EMB_DATA.get(ids)


def mean(ids):
    """List of face ids -> mean embedding"""
    return _EMB_DATA.mean(ids)


def features(ids):
    """List of face ids -> List of embeddings"""
    result = _EMB_DATA.get(ids)
    assert len(result) == len(ids)
    return [np.array(v) for _, v in result]


def sample(k):
    """Returns list of face_ids, uniformly random with replacement"""
    return _EMB_DATA.sample(k)


def exists(ids):
    """List of face ids -> List of bools"""
    return _EMB_DATA.exists(ids)


def dist(ids, targets=None, target_ids=None):
    """
    Computes the distance from each face in ids to the closest target
    
    Args:
        ids: List of faces to compute distances for
        targets: List of embeddings
        target_ids: List of face_ids
    
    Returns:
        List of distances in same order as as ids
    """
    if targets is not None:
        targets = [
            [float(z) for z in x.tolist()] 
            if not isinstance(x, list) else x for x in targets
        ]
        return _EMB_DATA.dist(targets, ids)
    elif target_ids is not None:
        return _EMB_DATA.dist_by_id(target_ids, ids)
    else:
        raise ValueError('No targets given')


def knn(targets=None, ids=None, k=2 ** 31, max_threshold=100.):
    """
    Computes distance of all faces to the targets 
    (specified by targets or ids)
    
    Args:
        targets: List of embeddings (i.e., list of floats)
        ids: List of face ids (another way to specify targets
        max_threshold: largest distance
        
    Returns:
        List of (face_id, distance) pairs by asending distance
    """
    if targets is not None:
        targets = [
            [float(z) for z in x.tolist()] 
            if not isinstance(x, list) else x for x in targets
        ]
        return _EMB_DATA.nn(targets, k, max_threshold)
    elif ids is not None:
        return _EMB_DATA.nn_by_id(ids, k, max_threshold)
    else:
        raise ValueError('No targets given')


def kmeans(ids, k=25):
    """
    Run kmeans on all face_ids in ids.
    
    Args:
        ids: List of face_ids
    
    Returns:
        List of (face_id, cluster number) pairs
    """
    return _EMB_DATA.kmeans(ids, k)


def logreg(ids, labels, min_thresh=0., max_thresh=1., num_epochs=10, 
           learning_rate=1., l2_penalty=0., l1_penalty=0.):
    """
    Args:
        ids: List of face_ids
        labels: List of 0, 1 labels
    Returns:
        (weights, List of (face_id, score) pairs by ascending score)
    """
    return _EMB_DATA.logreg(
        ids, labels, min_thresh, max_thresh, num_epochs,
        learning_rate, l2_penalty, l1_penalty)


def logreg_predict(weights, min_thresh=-1, max_thresh=2):
    """Returns: same as logreg"""
    return _EMB_DATA.logreg_predict(weights, min_thresh, max_thresh)
