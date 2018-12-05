from esper.prelude import *
from esper.stdlib import *
import spacy
import pysrt
import itertools
from spacy.attrs import ORTH, LEMMA
import esper.datatypes_pb2 as datatypes
import multiprocessing as mp

SUB_CACHE_DIR = '/app/data/subs'

nlp = spacy.load('en', disable=['parser', 'ner'])
nlp.tokenizer.add_special_case(
    '>>>',
    [{ORTH: ">>>", LEMMA: ">>>"}])
nlp.tokenizer.add_special_case(
    '>>',
    [{ORTH: ">>", LEMMA: ">>"}])

videos = list(Video.objects.all())

def load_transcript(video):
    if video.srt_extension == '':
        return None

    path = '/app/data/subs/orig/{}.{}.srt'.format(video.item_name(), video.srt_extension)

    # TODO(wcrichto): small subset of documents are failing with utf8 decode errors
    try:
        subs = pysrt.from_string(open(path, 'rb').read().decode('utf-8'))
    except Exception:
        print(video.path)
        return None

    # In practice, seems like subs are usually about 5 seconds late, so this is a hand-tuned shift
    subs.shift(seconds=-5)

    return subs

def time_to_float(t):
    return t.hours * 3600 + t.minutes * 60 + t.seconds

def pos_from_str(s):
    exceptions = {
        '-LRB-': 'LRB',
        '-RRB-': 'RRB',
        ',': 'COMMA',
        ':': 'COLON',
        '.': 'PERIOD',
        '\'\'': 'SINGLEQUOTE',
        '""': 'DOUBLEQUOTE',
        '#': 'POUND',
        '``': 'BACKTICK',
        '$': 'DOLLAR',
        'PRP$': 'PRPD',
        '_SP': 'SP',
        'WP$': 'WPD'
    }

    try:
        return getattr(datatypes.Document, exceptions[s] if s in exceptions else s)
    except AttributeError:
        # Sometimes spacy returns '' for token.tag_, not sure why? XX is "unknown" so best guess here
        return datatypes.Document.XX

def do_tokenize(video):
    flat_path = '{}/flat/{}.txt'.format(SUB_CACHE_DIR, video.item_name())
    meta_path = '{}/meta/{}.bin'.format(SUB_CACHE_DIR, video.item_name())
    if os.path.isfile(meta_path):
        return

    subs = load_transcript(video)
    if subs is None:
        return

    # Create/invoke a generator to tokenize the subtitle text
    texts = [sub.text.encode('ascii', 'ignore').decode('utf-8') for sub in subs]
    # NB: we have to remove unicode characters for now since Spacy tokens only track the word index, not
    # byte index of the token, so there's no easy way to figure out the byte offset of an arbitrary token w/
    # unicode chars > 1 byte.
    all_tokens = list(nlp.pipe(texts, batch_size=10000, n_threads=mp.cpu_count()))

    # Convert tokens into Protobuf
    cursor = 0
    doc = datatypes.Document()
    full_text = ''
    for (sub, text, tokens) in zip(subs, texts, all_tokens):
        for tok in tokens:
            word = doc.words.add()
            word.char_start = cursor + tok.idx
            word.char_end = word.char_start + len(tok.text)
            word.time_start = time_to_float(sub.start)
            word.time_end = time_to_float(sub.end)
            word.pos = pos_from_str(tok.tag_)
            word.lemma = tok.lemma_
        full_text += text + ' '
        cursor += len(text) + 1

    # Write flattened transcript as text file
    with open(flat_path, 'w') as f:
        f.write(full_text)

    # Write proto metadata
    with open(meta_path, 'wb') as f:
        f.write(doc.SerializeToString())

par_for(do_tokenize, videos, workers=12)
