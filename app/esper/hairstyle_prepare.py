from hwang import Decoder
from storehouse import StorageConfig, StorageBackend, RandomReadFile
from query.models import Video, FaceIdentity, Identity
from esper.prelude import collect

import cv2
import os
import pickle
import math
import random
import multiprocessing as mp


def prepare_hairstyle(video_path, face_list, storage=None, out_folder='/app/result/clothing/images/'):
#     (frame_id, face_id, identity_id, bbox) = face_list[0]

    fid_list = [face[0] for face in face_list]
#     print("fid_list", fid_list)
    
    # load frames from google cloud
    if storage is None:
        storage = StorageBackend.make_from_config(StorageConfig.make_gcs_config('esper'))
    video_file = RandomReadFile(storage, video_path.encode('ascii'))
    video = Decoder(video_file)
    img_list = video.retrieve(fid_list)
    img_list = [cv2.cvtColor(img, cv2.COLOR_RGB2BGR) for img in img_list]
#     print("load %d frames" % len(fid_list))
    
    H, W = img_list[0].shape[:2]
#     result = []
    for i, face in enumerate(face_list):
        (frame_id, face_id, identity_id, bbox) = face
        frame = img_list[i]
        x1 = int(bbox[0] * W)
        y1 = int(bbox[1] * H)
        x2 = int(bbox[2] * W)
        y2 = int(bbox[3] * H)
        w = max(y2 - y1, x2 - x1) * 3 // 4
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        x1 = cx - w if cx - w > 0 else 0
        x2 = cx + w if cx + w < W else W
        y1 = cy - w if cy - w > 0 else 0
        y2 = cy + w if cy + w < H else H
        filename = '{}_{}.jpg'.format(identity_id, face_id)
        cv2.imwrite(os.path.join(out_folder, filename), img_list[i][y1:y2, x1:x2])
#         result.append((identity_id, filename))
#     return result


def solve_thread(face_dict, tmp_dict_path, thread_id):
    print("Thread %d start computing..." % (thread_id))
    res_dict = {}
    storage = StorageBackend.make_from_config(StorageConfig.make_gcs_config('esper'))

    for i, video in enumerate(sorted(face_dict)):
        print("Thread %d start %dth video: %s" % (thread_id, i, video))
        
        prepare_clothing(video, face_dict[video], storage)
#         res_dict[video] = result
#         if i % 200 == 0 and i != 0:
#             pickle.dump(res_dict, open(tmp_dict_path, "wb" ))
            
#     pickle.dump(res_dict, open(tmp_dict_path, "wb" ))
    print("Thread %d finished computing..." % (thread_id))

    
def solve_parallel(face_dict, res_dict_path=None, workers=64):
    
#     if os.path.exists(res_dict_path):
#         res_dict = pickle.load(open(res_dict_path, "rb" ))
# #         video_list = [video for video in video_list if video not in res_dict]
#     else:
#     res_dict = {}

    video_list = sorted(face_dict)
    num_video = len(video_list)
    print("Num videos total: ", num_video)
    if num_video == 0:
        return 
    if num_video <= workers:
        workers = num_video
        num_video_t = 1
    else:
        num_video_t = math.ceil(1. * num_video / workers)
    print("Num videos per worker:", num_video_t)
    
    tmp_dict_list = []
    for i in range(workers):
        tmp_dict_list.append('/app/result/clothing/dict_{}.pkl'.format(i))
    
    ### using ctx will stuck in fork
#     ctx = mp.get_context('spawn')
    process_list = []
    for i in range(workers):
        if i != workers - 1:
            face_dict_t = { video: face_dict[video] for video in video_list[i*num_video_t : (i+1)*num_video_t] } 
        else:
            face_dict_t = { video: face_dict[video] for video in video_list[i*num_video_t : ] } 
        p = mp.Process(target=solve_thread, args=(face_dict_t, tmp_dict_list[i], i,))
        process_list.append(p)
    
    print("Assign jobs done")
    
    for p in process_list:
        p.start()
#     for p in process_list:
#         p.join()
    
#     for path in tmp_dict_list:
#         if not os.path.exists(path):
#             continue
#         res_dict_tmp = pickle.load(open(path, "rb" ))
#         res_dict = {**res_dict, **res_dict_tmp}
    
#     pickle.dump(res_dict, open(res_dict_path, "wb" ))  


if __name__ == "__main__":
    
    faceIdentities = FaceIdentity.objects \
        .filter(probability__gt=0.99) \
        .select_related('face__frame__video')
    
    faceIdentities_sampled = random.sample(list(faceIdentities), 100000)
    print("Load %d face identities" % len(faceIdentities_sampled))
    
    identity_grouped = collect(list(faceIdentities_sampled), lambda identity: identity.face.frame.video.id)
    print("Group into %d videos" % len(identity_grouped))
    
    face_dict = {}
    for video_id, fis in identity_grouped.items():
        video = Video.objects.filter(id=video_id)[0]
        face_list = []
        for i in fis:
            face_id = i.face.id
            frame_id = i.face.frame.number
            identity_id = i.identity.id
            x1, y1, x2, y2 = i.face.bbox_x1, i.face.bbox_y1, i.face.bbox_x2, i.face.bbox_y2
            bbox = (x1, y1, x2, y2)
            face_list.append((frame_id, face_id, identity_id, bbox))
        face_list.sort()
        face_dict[video.path] = face_list
    print("Preload face bbox done")
        
    solve_parallel(face_dict, res_dict_path='/app/result/clothing/fina_dict.pkl', workers=64)