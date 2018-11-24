import numpy as np
import torch
from torch.utils.data import Dataset
import requests
from query.models import Video
from timeit import default_timer as now

SEGMENT_SIZE = 200
SEGMENT_STRIDE = 100

def video_list():
    r = requests.get('http://localhost:8111/videos')
    return r.json()

def get_doc(item):
    r = requests.post('http://localhost:8111/getdoc', json={'phrases': [item]})
    return r.json()

def doc_len():
    r = requests.get('http://localhost:8111/doclen')
    return r.json()

def compute_vectors(docs, vocabulary, window_size, stride):
    requests.post('http://localhost:8111/computevectors', json={
        'vocabulary': vocabulary,
        'docs': docs,
        'window_size': window_size,
        'stride': stride
    })

def find_segments(docs, lexicon, threshold, window_size, stride):
    r = requests.post('http://localhost:8111/findsegments', json={
        'lexicon': lexicon,
        'threshold': threshold,
        'window_size': window_size,
        'merge_overlaps': False,
        'stride': stride,
        'docs': docs
    })
    return r.json()

def small_video_sample():
    videos = []
    id = 1
    while len(videos) < 10:
        try:
            v = Video.objects.get(id=id)
            get_doc(v)
            videos.append(v)
        except Exception:
            pass
        id += 1
    return videos


class SegmentTextDataset(Dataset):
    def __init__(self, docs, vocabulary=None, segment_size=SEGMENT_SIZE, segment_stride=SEGMENT_STRIDE, use_cuda=False):
        self._segment_size = segment_size
        self._use_cuda = use_cuda
        self._vocabulary = vocabulary
        self._doc_names = docs
        self._doc_lens = doc_len()
        self._num_segs = np.array([
            len(range(0, self._doc_lens[doc]-segment_size+1, segment_stride))
            for doc in self._doc_names
        ])
        self._back_index = [
            (i, j, k)
            for i, doc in enumerate(self._doc_names)
            for k, j in enumerate(range(0, self._doc_lens[doc]-segment_size+1, segment_stride))
        ]
        self._forward_index = {
            (self._doc_names[i], j): k
            for k, (i, j, _) in enumerate(self._back_index)
        }
        self._docs = {}
        self._segs = {}

    def segment_index(self, doc, word):
        return self._forward_index[(doc, word)]

    def _text_to_vector(self, words):
        words = set(words)
        return torch.tensor([1 if word in words else 0 for word in self._vocabulary],
                            dtype=torch.float32)

    def __len__(self):
        return self._num_segs.sum()

    def __getitem__(self, idx):
        (i, j, _) = self._back_index[idx]

        if not (i, j) in self._segs:
            if not i in self._docs:
                self._docs[i] = get_doc(self._doc_names[i])

            seg = self._docs[i][j:j+self._segment_size]

            data = {
                'document_idx': i,
                'segment_idx': j,
            }

            if self._vocabulary is not None:
                data['vector'] = self._text_to_vector(seg)

                if self._use_cuda:
                    data['vector'] = data['vector'].cuda()

            data['segment'] = ' '.join(seg)

            self._segs[(i, j)] = data

        return self._segs[(i, j)]

import mmap
class SegmentVectorDataset(Dataset):
    def __init__(self, docs, vocab_size, segment_size=SEGMENT_SIZE, segment_stride=SEGMENT_STRIDE, use_cuda=False):
        self._ds = SegmentTextDataset(docs, segment_size=segment_size, segment_stride=segment_stride)
        self._doc_names = docs
        self._vocab_size = vocab_size
        self._use_cuda = use_cuda
        self._file_handle = open('/app/data/segvectors.bin', 'r+b')
        self._file = mmap.mmap(self._file_handle.fileno(), 0)
        self._byte_offsets = []

        # Compute prefix sum of document offsets
        for i, doc in enumerate(self._doc_names):
            dlen = self._ds._num_segs[i-1] * self._vocab_size
            if i == 0:
                self._byte_offsets.append(0)
            else:
                self._byte_offsets.append(self._byte_offsets[i - 1] + dlen)

    def _byte_offset(self, idx):
        (i, _, j) = self._ds._back_index[idx]
        return self._byte_offsets[i] + j * self._vocab_size

    def __len__(self):
        return len(self._ds)

    def __getitem__(self, idx):
        offset = self._byte_offset(idx)
        self._file.seek(offset)
        byts = self._file.read(self._vocab_size)
        assert len(byts) == self._vocab_size, \
            'Invalid read at index {}, offset {}. Expected {} bytes, got {}'.format(idx, offset, self._vocab_size, len(byts))
        npbuf = np.frombuffer(byts, dtype=np.uint8)
        tbuf = torch.from_numpy(npbuf).float()
        if self._use_cuda:
            tbuf = tbuf.cuda()
        return tbuf

class LabeledSegmentDataset(Dataset):
    def __init__(self, unlabeled_dataset, labels, categories):
        self._ds = unlabeled_dataset
        self._labels = labels
        self._categories = categories

    def __len__(self):
        return len(self._labels)

    def __getitem__(self, idx):
        (seg_idx, label) = self._labels[idx]
        label = torch.tensor([1 if label == i else 0 for i in range(self._categories)], dtype=torch.float32)
        if self._ds._use_cuda:
            label = label.cuda()
        return self._ds[seg_idx], label
