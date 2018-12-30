from scannertools.transcript_alignment import TranscriptAligner
import pickle
import os
import sys

def callback(name, outputs):
    video_name = name[:name.find('.mp4')].split('/')[2]
    path = name.replace('_align_transcript', '')
    
    align_dir = '/app/data/subs/aligned/'
    align_word_list = []
    num_word_aligned = 0
    num_word_total = 0
    for seg_idx, seg_bytes in enumerate(outputs):
        seg = pickle.loads(seg_bytes)
        align_word_list += seg['align_word_list']
        num_word_aligned += seg['num_word_aligned']
        if 'num_word_total' in seg:
            num_word_total += seg['num_word_total']
        else:
            num_word_total += len(seg['align_word_list'])
                
    output_path = os.path.join(align_dir, '{}.{}.srt'.format(video_name, 'word'))
    TranscriptAligner.dump_aligned_transcript_byword(align_word_list, output_path)

    if num_word_total == 0:
        print(path, 1)
    else:
        print(path, 1 - 1. * num_word_aligned / num_word_total)
    sys.stdout.flush()

