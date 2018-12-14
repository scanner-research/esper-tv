from scannertools import audio, transcript_alignment
from query.models import Video
from esper.kube import make_cluster, cluster_config, worker_config

import scannerpy
import os
import pickle
import math
import tempfile
import re

SEG_LENGTH = 60

def main():
    # set test video list
#     video_list = ['CNNW_20160107_180000_Wolf']

    videos = Video.objects.filter(threeyears_dataset=True).all()
    addtional_field = pickle.load(open('/app/data/addtional_field.pkl', 'rb'))
    videos = [video for video in videos if addtional_field[video.id]['valid_transcript']]
    videos = videos[20000:30000]

    # todo: remove videos whose result is already dumped
    
    # get audio length
#     pkl_path = '/app/data/audio_length_dict.pkl'
#     audio_length_dict = pickle.load(open(pkl_path, 'rb'))
#     audio_length = [audio_length_dict[video_name] for video_name in video_list]
    
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
    run_opts = {'pipeline_instances_per_node': 32, 'checkpoint_frequency': 5}
    
    # set up align opts
    align_opts = {'seg_length' : 60,
                  'max_misalign' : 10,
                  'num_thread' : 1,
                  'exhausted' : False,
                  'align_dir' : None,
                  'res_path' : None,
#                   'align_dir' : '/app/data/subs/orig/',
#                   'res_path' : '/app/result/test_align_3y.pkl',
    }
    
    '''local run'''
#     db = scannerpy.Database()
#     transcript_alignment.align_transcript(db, videos, audios, captions, run_opts, align_opts, cache=False) 
    
    '''kubernete run'''
    cfg = cluster_config(
        num_workers=100,
        worker=worker_config('n1-standard-32'))
    
    with make_cluster(cfg, no_delete=True) as db_wrapper:
        db = db_wrapper.db
        transcript_alignment.align_transcript_pipeline(db=db, audio=audios, captions=captions, cache=False, 
                                                       run_opts=run_opts, align_opts=align_opts)

        
if __name__ == "__main__": 
    main()
    