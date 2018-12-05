from scannertools import audio, transcript_alignment
from query.models import Video
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
#     video_list = ['CNNW_20161229_060000_CNN_Newsroom_Live']
    video_list = pickle.load(open('/app/app/data/tvnews_std_sample.pkl', 'rb'))['sample_100']

    # load videos from database
    videos = [Video.objects.filter(path__contains=video_name)[0] for video_name in video_list]
    
    # get audio length
    audio_length = [get_audio_length(video) for video in videos]
    
    # load audios from videos
    audios = [audio.AudioSource(video.for_scannertools(), frame_size=SEG_LENGTH) for video in videos]
    
    # set up transcripts 
    captions = [audio.CaptionSource('tvnews/subs10/'+video_name, max_time=length , window_size=SEG_LENGTH) 
                for video_name, length in zip(video_list, audio_length)]

    db = scannerpy.Database(workers_per_node=64)
    result = transcript_alignment.align_transcript(db, video_list=video_list, audio=audios, caption=captions, 
                                                   cache=False, 
                                                   align_dir='/app/app/result/aligned_transcript',
                                                   res_path='/app/app/result/test_align_100.pkl')
    
    result[0]._column._table.profiler().write_trace('/app/app/result/test_align_100.trace')

if __name__ == "__main__": 
    main()
    