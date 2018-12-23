from scannertools import audio
from scannertools.transcript_alignment import align_transcript_pipeline, TranscriptAligner
from query.models import Video
from esper.kube import make_cluster, cluster_config, worker_config
from esper.load_alignment import callback

import scannerpy
import os
import pickle
import math
import tempfile
import re
import sys

SEG_LENGTH = 60

if __name__ == "__main__":
    
#     video_start = int(sys.argv[1])

    # set test video list
#     video_list = ['MSNBCW_20160614_180000_MSNBC_Live']
#     videos = [Video.objects.filter(path__contains=video_name)[0] for video_name in video_list]

    videos = Video.objects.all()
    addtional_field = pickle.load(open('/app/data/addtional_field_all.pkl', 'rb'))
    videos = [video for video in videos if addtional_field[video.id]['valid_transcript']]
    
    # second run for bad align videos
    res_stats = pickle.load(open('/app/result/align_stats_first.pkl', 'rb'))
    videos = [video for video in videos if video.id in res_stats and res_stats[video.id]['word_missing'] > 0.2]
    print("Videos total: ", len(videos))
    
    # remove already dumped videos
    res_stats = pickle.load(open('/app/result/align_stats_second.pkl', 'rb'))
    videos = [video for video in videos if video.id not in res_stats]
    print('Unfinished videos:', len(videos))
    
    # remove videos have inequal audio/frame time
    videos_valid = []
    for video in videos:
        audio_time = addtional_field[video.id]['audio_duration']
        frame_time = video.num_frames / video.fps
        if audio_time / frame_time < 1.1 and audio_time / frame_time > 0.9:
            videos_valid.append(video)
    videos = videos_valid
    print("Videos valid: ", len(videos))
#     videos = videos[video_start : video_start+10000]

    # remove videos not saved in database
    db = scannerpy.Database()
    meta = db._load_db_metadata()
    tables_in_db= {t.name for t in meta.tables}
    videos_uncommitted = []
    for video in videos:
        table_name = '{}_align_transcript2'.format(video.path)
        if table_name not in tables_in_db:
            videos_uncommitted.append(video)
    print("Videos uncommitted:", len(videos_uncommitted))
    videos = videos_uncommitted
    
    '''batch load'''
#     db.batch_load(tables_committed, 'align_transcript', callback)
    
    # load audios from videos
    audios = [audio.AudioSource(video.for_scannertools(), 
                                frame_size=SEG_LENGTH, 
                                duration=addtional_field[video.id]['audio_duration']) 
              for video in videos]
    
    # set up transcripts 
    captions = [audio.CaptionSource('tvnews/subs10/'+video.item_name(), 
                                    max_time=addtional_field[video.id]['audio_duration'], 
                                    window_size=SEG_LENGTH) 
                for video in videos]
    
    # set up run opts
    run_opts = {'pipeline_instances_per_node': 32, 'checkpoint_frequency': 5, 'io_packet_size': 4, 'work_packet_size': 4}
    
    # set up align opts
    align_opts = {'win_size': 300,
                  'seg_length' : 60,
                  'max_misalign' : 10,
                  'num_thread' : 1,
                  'estimate' : True,
                  'align_dir' : None,
                  'res_path' : None,
#                   'align_dir' : '/app/result/aligned_transcript',
#                   'res_path' : '/app/result/test_align_3y.pkl',
    }
    
    '''local run'''
#     db = scannerpy.Database()
#     result = align_transcript_pipeline(db=db, audio=audios, captions=captions, cache=False, 
#                                                    run_opts=run_opts, align_opts=align_opts)
    
    '''kubernete run'''
    cfg = cluster_config(
        num_workers=20,
        worker=worker_config('n1-standard-32'))
    
    with make_cluster(cfg, no_delete=True) as db_wrapper:
        db = db_wrapper.db
        align_transcript_pipeline(db=db, audio=audios, captions=captions, cache=False, 
                                                       run_opts=run_opts, align_opts=align_opts)
    
    align_dir = align_opts['align_dir']
    res_path = align_opts['res_path']
    if align_dir is None or res_path is None:
        exit() 
    if os.path.exists(res_path):
        res_stats = pickle.load(open(res_path, 'rb'))
    else:
        res_stats = {}
        
    for idx, res_video in enumerate(result):
        video_name, srt_ext, video_id = videos[idx].item_name(), videos[idx].srt_extension, videos[idx].id
        if res_video is None:
            continue
        
        align_word_list = []
        num_word_aligned = 0
        num_word_total = 0
        res_video_list = res_video.load()
        for seg_idx, seg in enumerate(res_video_list):
            align_word_list += seg['align_word_list']
            num_word_aligned += seg['num_word_aligned']
            if 'num_word_total' in seg:
                num_word_total += seg['num_word_total']
            else:
                num_word_total += len(seg['align_word_list'])
            print(seg_idx, len(seg['align_word_list']))
                
        res_stats[video_id] = {'word_missing': 1 - 1. * num_word_aligned / num_word_total}
        print(idx, video_name)
        print('num_word_total: ', num_word_total)
        print('num_word_aligned: ', num_word_aligned)
        print('word_missing by total words: ', 1 - 1. * num_word_aligned / num_word_total)
        print('word_missing by total aligned: ', 1 - 1. * num_word_aligned / len(align_word_list))
        
        output_path = os.path.join(align_dir, '{}.{}.srt'.format(video_name, 'word'))
        TranscriptAligner.dump_aligned_transcript_byword(align_word_list, output_path)
        pickle.dump(res_stats, open(res_path, 'wb'))