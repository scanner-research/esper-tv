import os
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


def knn(targets=None, ids=None, k=2 ** 31, max_threshold=100.):
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
    return _EMB_DATA.kmeans(ids, k)


def features(ids):
    result = _EMB_DATA.get(ids)
    assert len(result) == len(ids)
    return [np.array(v) for _, v in result]
