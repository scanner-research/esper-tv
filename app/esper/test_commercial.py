import scannerpy
from query.models import Video
from esper.prelude import par_for
from rekall.interval_list import IntervalList
from esper.rekall import *
from esper.commercial_detect_rekall import detect_commercial_rekall

import os
import pickle

# load data
# additional_field = pickle.load(open('/app/data/addtional_field.pkl', 'rb'))


def detect_commercial_t(param):
    (video, blackframe_list) = param
    video_name = video.item_name()
    print(video_name)
    transcript_path = "/app/data/subs/aligned/" + video_name + '.word.srt'
    if blackframe_list is None or not os.path.exists(transcript_path):
        return None
    result = detect_commercial_rekall(video, 
                                      transcript_path, 
                                      blackframe_list=blackframe_list, 
                                      debug=False, verbose=False)
    return result

if __name__ == "__main__":
    
    NUM_PACK = 10000
    black_frame_dict = pickle.load(open('/app/data/black_frame_all.pkl', 'rb'))
    videos = Video.objects.all()

    cur_idx = 0
    while cur_idx < len(videos):
        params = []
        for i in range(cur_idx, cur_idx + NUM_PACK):
            if i >= len(videos):
                break
            video = videos[i]
            if video.id in black_frame_dict:
                params.append((video, black_frame_dict[video.id]))
            else:
                params.append((video, None))
        results = par_for(detect_commercial_t, params, workers=64)
        com_dict = {}
        for i in range(NUM_PACK):
            if not results[i] is None:
                com_dict[params[i][0].id] = results[i]
        pickle.dump(com_dict, open('/app/result/commercial/dict_{}.pkl'.format(cur_idx), 'wb'))
        
        cur_idx += NUM_PACK
        print("%d videos done!" % cur_idx)
        break