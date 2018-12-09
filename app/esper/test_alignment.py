from scannertools import audio, transcript_alignment
from query.models import Video
from esper.kube import make_cluster, cluster_config, worker_config

import scannerpy
import os
import pickle
import math
import tempfile
import re

def get_audio_length(video):
    url = video.url()
    log = tempfile.NamedTemporaryFile(suffix='.txt').name
    cmd = 'ffprobe -show_streams -i ' + \
        '\"' + url + '\"' + ' > ' + log
    os.system(cmd)
    format_str = open(log, 'r').read()
    return float(re.findall(r'\nduration=(.*)', format_str)[1])

SEG_LENGTH = 60

def main():
    # set test video list
#     video_list = ['CNNW_20161116_200000_CNN_Newsroom_With_Brooke_Baldwin']
    video_list = pickle.load(open('/app/data/tvnews_std_sample.pkl', '_St_sample_'))['three_year'][:500]
    
    # remove videos whose result is already dumped
    # todo
    
    # load videos from database
    videos = [Video.objects.filter(path__contains=video_name)[0] for video_name in video_list]
#     videos = []
#     video_list_copy = video_list.copy()
#     for video_name in video_list_copy:
#         video_filter = Video.objects.filter(path__contains=video_name)
#         if len(video_filter) > 0:
#             videos.append(video_filter[0])
#         else:
#             video_list.remove(video_name)
    
    # get audio length
    audio_length = []
    pkl_path = '/app/data/audio_length_dict.pkl'
    if os.path.exists(pkl_path):
        audio_length_dict = pickle.load(open(pkl_path, 'rb'))
    else:
        audio_length_dict = {}
    for video_name, video in zip(video_list, videos):
        if video_name in audio_length_dict:
            audio_length += [audio_length_dict[video_name]]
        else:
            audio_length += [get_audio_length(video)]
            audio_length_dict[video_name] = audio_length[-1]
    pickle.dump(audio_length_dict, open(pkl_path, 'wb'))
    
#     pkl_path = '/app/data/audio_length_dict.pkl'
#     audio_length_dict = pickle.load(open(pkl_path, 'rb'))
#     audio_length = [audio_length_dict[video_name] for video_name in video_list]
    
    # load audios from videos
    audios = [audio.AudioSource(video.for_scannertools(), frame_size=SEG_LENGTH) for video in videos]
    
    # set up transcripts 
    captions = [audio.CaptionSource('tvnews/subs10/'+video_name, max_time=length , window_size=SEG_LENGTH) 
                for video_name, length in zip(video_list, audio_length)]
    
    # set up run ops
    run_opts = {'pipeline_instances_per_node': 1}
    
    # local run
    db = scannerpy.Database(workers_per_node=64)
    
    # kubernete run
#     cfg = cluster_config(
#         num_workers=5,
#         worker=worker_config('n1-standard-32'))
#     with make_cluster(cfg, no_delete=True) as db_wrapper:
#         db = db_wrapper.db

    transcript_alignment.align_transcript_pipeline(db=db, audio=audios, captions=captions, cache=True, run_opts=run_opts)
#     transcript_alignment.align_transcript(db, video_list=video_list, audio=audios, caption=captions, 
#                                           cache=True, 
#                                           run_opts={'pipeline_instances_per_node': 64},
#                                           align_dir=None,
#                                           res_path=None)
#                                                    align_dir='/app/result/aligned_transcript_1000',
#                                                    res_path='/app/result/test_align_1000.pkl')
    
if __name__ == "__main__": 
    main()
    