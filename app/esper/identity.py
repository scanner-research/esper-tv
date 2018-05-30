from esper.prelude import *
from esper.stdlib import *
from esper.ingest import ingest_pose
from query.models import *

try:
    from IPython.display import clear_output
except ImportError as e:
    print('Failed to import clear_output')
    clear_output = lambda: None

import _pickle as pickle
import os
import concurrent.futures
import tempfile
import random
import string

from subprocess import check_call
from esper import embed_google_images
from collections import defaultdict, Counter
from django.db.models.functions import Cast
from django.db.models import F, Sum, FloatField, Count, IntegerField
from django.db import transaction


RESULTS_DIR = '/app/data/face_eval'
if not os.path.exists(RESULTS_DIR):
    os.makedirs(RESULTS_DIR)

GCS_MODEL_PREFIX = 'gs://esper/tvnews/face_identity_model'


def random_hex_string(length):
    return ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length))


class FaceIdentityModel(object):
    """
    Standardized results from a run of the face identity model
    """
    
    def __init__(self, name, face_ids_by_bucket, face_ids_to_score, precision_by_bucket, model_params):
        self.name = name
        self._face_ids_to_score = face_ids_to_score
        self._face_ids_by_bucket = face_ids_by_bucket
        self._precision_by_bucket = precision_by_bucket
        self._model_params = model_params
     
    @property
    def model_params(self):
        return self._model_params
    
    @property
    def face_ids_to_score(self):
        return self._face_ids_to_score
    
    @property
    def precision_by_bucket(self):
        return self._precision_by_bucket
    
    @property
    def face_ids_by_bucket(self):
        return self._face_ids_by_bucket
    
    @property
    def buckets(self):
        return self._face_ids_by_bucket.keys()
    
    @property
    def exp_positives_by_bucket(self, verbose=True):
        assert self._face_ids_by_bucket and self._precision_by_bucket
        exp_total_positives = 0
        exp_positives_by_bucket = {}
        for k in sorted(self.buckets):
            min_t, max_t = k
            count = len(self._face_ids_by_bucket[k])
            if verbose:
                print('in range=({:0.2f}, {:0.2f})'.format(min_t, max_t))
            exp_positives = self._precision_by_bucket[k] * count
            if verbose:
                print('\tprecision={:0.3f}, count={}, exp_positives={:0.2f}'.format(self.precision_by_bucket[k], count, exp_positives))
            exp_total_positives += exp_positives
            exp_positives_by_bucket[k] = exp_positives
        if verbose:
            print('Expected positives:', exp_total_positives)
        return exp_positives_by_bucket
    
    @property
    def exp_positives_total(self):
        return sum(self._precision_by_bucket[k] * len(self._face_ids_by_bucket[k]) 
                   for k in self.buckets)
    
    def dumps(self):
        return pickle.dumps({
            'name': self.name,
            'face_ids_to_score': self._face_ids_to_score,
            'face_ids_by_bucket': self._face_ids_by_bucket,
            'precision_by_bucket': self._precision_by_bucket,
            'model_params': self._model_params
        })
    
    def save(self, out_path=None):
        if not out_path:
            out_path = os.path.join(RESULTS_DIR, '{}.pkl'.format(self.name))
        with open(out_path, 'wb') as f:
            f.write(self.dumps())
    
    @staticmethod
    def load(in_path=None, name=None):
        if not in_path:
            in_path = os.path.join(RESULTS_DIR, '{}.pkl'.format(name))
        with open(in_path, 'rb') as f:
            obj = pickle.load(f)
        return FaceIdentityModel(
            name=obj['name'],
            face_ids_to_score=obj['face_ids_to_score'],
            face_ids_by_bucket=obj['face_ids_by_bucket'],
            precision_by_bucket=obj['precision_by_bucket'],
            model_params=obj['model_params']
        )
    
    def save_to_gcs(self, out_path=None):
        if not out_path:
            out_path = os.path.join(GCS_MODEL_PREFIX, '{}.pkl'.format(self.name))
        with tempfile.NamedTemporaryFile() as f:
            f.write(self.dumps())
            f.flush()
            check_call(['gsutil', 'cp', f.name, out_path])
        return out_path
    
    @staticmethod
    def load_from_gcs(in_path=None, name=None):
        if not in_path:
            in_path = os.path.join(GCS_MODEL_PREFIX, '{}.pkl'.format(name))
        tmp_file = '/tmp/face_identity_{}.pkl'.format(random_hex_string(16))
        try:
            check_call(['gsutil', 'cp', in_path, tmp_file])
            return FaceIdentityModel.load(in_path=tmp_file)
        finally:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)
    

def commit_face_identities_to_db(model, person, labeler):
    """person is a Thing and labeler is a Labeler"""
    id_set = set()
    
    min_prob = 0.001
    
    # build score interpolation function
    f_x = []
    f_y = []
    for k in sorted(model.buckets):
        f_x.append((k[0] + k[1]) / 2.)
        f_y.append(model.precision_by_bucket[k])
    
    with transaction.atomic():
        for k in sorted(model.buckets):
            # Skip if the whole bucket is less than the threshold
            if np.interp(k[0], f_x, f_y) < min_prob and np.interp(k[1], f_x, f_y) < min_prob:
                continue
                
            face_ids = model.face_ids_by_bucket[k]
            face_scores = [model.face_ids_to_score[x] for x in face_ids]
            face_probs = [float(x) for x in np.interp(face_scores, f_x, f_y)]
            for i, p in zip(face_ids, face_probs):
                if p >= min_prob:
                    if i in id_set:
                        print('Warning: face id {} is duplicated in more than one bucket'.format(i))
                        continue
                    else:
                        id_set.add(i)
                    FaceIdentity.objects.create(
                        face_id=i,
                        probability=p, 
                        labeler=labeler, 
                        identity=person
                    )
    

class PrecisionModel(object):
    
    def __init__(self, face_ids_by_bucket):
        sorted_buckets = sorted(face_ids_by_bucket.keys())
        lower_buckets = sorted_buckets[:int(len(sorted_buckets) / 2)]
        upper_buckets = sorted_buckets[len(lower_buckets):]

        def sample_buckets(buckets, n):
            idx_to_face_ids = []
            idx_to_bucket = []
            for k in buckets:
                face_ids = face_ids_by_bucket[k]
                sample_ids = random.sample(face_ids, k=min(len(face_ids), n))
                idx_to_face_ids.extend(sample_ids)
                idx_to_bucket.extend([k] * len(sample_ids))
            assert(len(idx_to_face_ids) == len(idx_to_bucket))
            return idx_to_face_ids, idx_to_bucket

        lower_face_ids, self.lower_coresp_buckets = sample_buckets(lower_buckets, n=50)
        upper_face_ids, self.upper_coresp_buckets = sample_buckets(upper_buckets, n=50)

        self.lower_face_qs = Face.objects.filter(id__in=lower_face_ids)
        assert(self.lower_face_qs.count() == len(lower_face_ids))
        self.lower_qs_result = qs_to_result(
            Face.objects.filter(id__in=lower_face_ids), custom_order_by_id=lower_face_ids[::-1],
            limit=len(lower_face_ids))

        self.upper_face_qs = Face.objects.filter(id__in=upper_face_ids)
        assert(self.upper_face_qs.count() == len(upper_face_ids))
        self.upper_qs_result = qs_to_result(
            Face.objects.filter(id__in=upper_face_ids), custom_order_by_id=upper_face_ids,
            limit=len(upper_face_ids))
        
    def get_lower_count(self):
        return len(self.lower_coresp_buckets)
    
    def get_upper_count(self):
        return len(self.upper_coresp_buckets)
            
    def get_lower_widget(self):
        return esper_widget(self.lower_qs_result, crop_bboxes=True)
    
    def get_upper_widget(self):
        return esper_widget(self.upper_qs_result, crop_bboxes=True)
    
    def compute_precision_for_lower_buckets(self, selected_idxs):
        expected_count_by_bucket = Counter()
        error_count_by_bucket = Counter()
        for k in self.lower_coresp_buckets:
            expected_count_by_bucket[k] += 1
        for i in selected_idxs:
            error_count_by_bucket[self.lower_coresp_buckets[-i]] += 1

        result = {}
        for k in expected_count_by_bucket:
            result[k] = (expected_count_by_bucket[k] - error_count_by_bucket[k]) / expected_count_by_bucket[k]
        return result
        
    def compute_precision_for_upper_buckets(self, selected_idxs):
        expected_count_by_bucket = Counter()
        correct_count_by_bucket = Counter()
        for k in self.upper_coresp_buckets:
            expected_count_by_bucket[k] += 1
        for i in selected_idxs:
            correct_count_by_bucket[self.upper_coresp_buckets[i]] += 1

        result = {}
        for k in expected_count_by_bucket:
            result[k] = correct_count_by_bucket[k] / expected_count_by_bucket[k]
        return result

    
def load_and_select_faces_from_images(img_dir):
    
    def yn_prompt(msg):
        while True:
            x = input(msg)
            if x == '' or x.lower() == 'y':
                return True
            elif x.lower() == 'n':
                return False
    
    img_paths = []
    imgs = []
    for img_file in os.listdir(img_dir):
        img_path = os.path.join(img_dir, img_file)
        img = cv2.imread(img_path)
        img_paths.append(img_path)
        imgs.append(img)
    face_crops = embed_google_images.detect_faces_in_images(imgs)
    
    selected_crops = []
    for img_path, face_imgs in zip(img_paths, face_crops):
        if len(face_imgs) != 1:
            continue
        print(img_path)
        selected_crops_for_img = []
        for img in face_imgs:
            imshow(img)
            plt.show()
            if yn_prompt('Keep this image? [Y/n] '):
                selected_crops_for_img.append(img)
            clear_output()
        if selected_crops_for_img:
            selected_crops.append(selected_crops_for_img)

    return selected_crops


def face_search_by_embeddings(embs, increment=0.05, min_thresh=0., max_thresh=1.2,
                              exclude_labeled=False):
    face_sims = face_knn(targets=embs, min_threshold=min_thresh, max_threshold=max_thresh)
    face_ids_to_score = { a : b for a, b in face_sims if b >= min_thresh and b < max_thresh }
    
    results_by_bucket = {}
    for t in frange(min_thresh, max_thresh, increment):
        face_ids = [x for x, _ in filter(lambda z: z[1] >= t and z[1] < t + increment, face_sims)]
            
        if len(face_ids) != 0:
            results_by_bucket[(t, t + increment)] = face_ids

    if len(results_by_bucket) == 0:
        raise Exception('No results to show')
        
    return results_by_bucket, face_ids_to_score


def faces_to_tiled_img(faces, cols=12):
    def face_img(face):
        return crop(load_frame(face.person.frame.video, face.person.frame.number, []), face)
    
    def tile(imgs, rows=None, cols=None):
        # If neither rows/cols is specified, make a square
        if rows is None and cols is None:
            rows = int(math.sqrt(len(imgs)))

        if rows is None:
            rows = int((len(imgs) + cols - 1) / cols)
        else:
            cols = int((len(imgs) + rows - 1) / rows)

        # Pad missing frames with black
        diff = rows * cols - len(imgs)
        if diff != 0:
            imgs.extend([np.zeros(imgs[0].shape, dtype=imgs[0].dtype) for _ in range(diff)])

        return np.vstack([np.hstack(imgs[i * cols:(i + 1) * cols]) for i in range(rows)])
    
    face_imgs = par_for(face_img, faces)
    im = tile([cv2.resize(img, (200, 200)) for img in face_imgs], cols=cols)
    return im


def plot_precision_and_cdf(model):
    """
    Plot precision and cdf curves for an identity
    """
    exp_positives_by_bucket = model.exp_positives_by_bucket
    
    x = []
    y_cdf = []
    acc = 0.
    for k in sorted(exp_positives_by_bucket.keys()):
        min_t, max_t = k
        x.append((max_t + min_t) / 2.)
        acc += exp_positives_by_bucket[k]
        y_cdf.append(acc)
    y_cdf = [z / acc for z in y_cdf]
    plt.plot(x, y_cdf, '-o', color='blue', label='cdf')
    
    y_prec = []
    for k in sorted(model.buckets):
        y_prec.append(model.precision_by_bucket[k])
    plt.plot(x, y_prec, '-x', color='red', label='precision')
    
    plt.xlabel('Distance threshold')
    plt.legend()
    
    plt.show()


def compute_gender_breakdown(model):
    """
    Return the breakdown of genders for labeled faces
    """
    def gender_proportion_per_bucket(args):
        bucket, precision, face_ids = args
        assert precision >= 0 and precision <= 1.
        if precision > 0:
            query_result = FaceGender.objects.filter(
                face__id__in=face_ids,
                face__shot__in_commercial=False
            ).values(
                'gender__name'
            ).annotate(
                total=Count('gender')
            )
            return { x['gender__name'] : precision * x['total'] for x in query_result }
        else:
            return {}
    
    gender_breakdown = defaultdict(float)
    args_list = [(k, model.precision_by_bucket[k], model.face_ids_by_bucket[k])
                 for k in sorted(model.buckets)]
    results = par_for(gender_proportion_per_bucket, args_list)
    for x in results:
        for k, v in x.items():
            gender_breakdown[k] += v
    return gender_breakdown


def show_gender_examples(model, precision_thresh=0.8, n=50):
    """
    Tiled examples for each gender pertaining to a labeled identity
    """
    selected_ids = []
    for k in sorted(model.buckets):
        if model.precision_by_bucket[k] >= precision_thresh:
            selected_ids.extend(model.face_ids_by_bucket[k])
    
    results = {}
    for gender in ['M', 'F', 'U']:
        ids = [
            x['face__id'] for x in FaceGender.objects.filter(
                face__id__in=selected_ids, gender__name=gender
            ).distinct('face__id').values('face__id')[:n]
        ]
        results[gender] = qs_to_result(Face.objects.filter(id__in=ids))
    return esper_widget(group_results([x for x in results.items()]), crop_bboxes=True)
        

def plot_histogram_of_face_sizes(model, max_bucket=35):
    """
    Plot a histogram of face bounding box sizes by area
    """
    def face_sizes_per_bucket(args):
        bucket, precision, face_ids = args
        assert precision >= 0 and precision <= 1.
        if precision > 0.:
            query_results = Face.objects.filter(
                id__in=face_ids,
                shot__in_commercial=False,
            ).annotate(
                bbox_area=Cast((F('bbox_x2') - F('bbox_x1')) * (F('bbox_y2') - F('bbox_y1')) * 100 , IntegerField())
            ).values(
                'bbox_area'
            ).annotate(
                count=Count('bbox_area')
            )
            return { x['bbox_area'] : x['count'] * precision for x in query_results }
        else:
            return {}

    face_size_hist = Counter()
    args_list = [(k, model.precision_by_bucket[k], model.face_ids_by_bucket[k])
                 for k in sorted(model.buckets)]
    results = par_for(face_sizes_per_bucket, args_list)
    for x in results:
        for k, v in x.items():
            if k <= max_bucket:
                face_size_hist[k] += v
            else:
                face_size_hist[max_bucket] += v
    
    def make_plot(data):
        fig, ax1 = plt.subplots()

        ind = np.arange(len(data))
        width = 0.5
        rect1 = ax1.bar(ind, [y for _, y in data], width,
                        color='SkyBlue')
        ax1.set_ylabel('Count', fontsize=14)
        ax1.set_title('Distribution of {} face sizes across non-commercial videos'.format(model.name))
        ax1.set_xticks(ind)
        ax1.set_xlabel('Area (%)', fontsize=14)
        ax1.set_xticklabels(ind)
        plt.show()
    
    make_plot([
        (x, face_size_hist[x]) for x in sorted(face_size_hist.keys())
    ])
    

def compute_screen_time_by_video(model, show_name):
    """
    Return a dictionary from video id to seconds for single show
    """
    def screen_time_by_video_per_bucket(args):
        bucket, precision, face_ids, show_name = args
        if precision > 0.:
            query_results = Shot.objects.filter(
                id__in=[
                    x['shot__id'] for x in 
                    Face.objects.filter(id__in=face_ids).distinct('shot').values('shot__id')
                ],
                video__show__name=show_name, in_commercial=False,
            ).values(
                'video__id'
            ).annotate(
                screen_time=Sum((F('max_frame') - F('min_frame')) / F('video__fps'), 
                                output_field=FloatField())
            )
            return { x['video__id'] : x['screen_time'] * precision for x in query_results }
        else:
            return {}
    
    screen_time_by_video_id = Counter()
    args_list = [(k, model.precision_by_bucket[k], model.face_ids_by_bucket[k], show_name)
                 for k in sorted(model.buckets)]
    results = par_for(screen_time_by_video_per_bucket, args_list)
    for x in results:
        for k, v in x.items():
            screen_time_by_video_id[k] += v
    return screen_time_by_video_id


def plot_histogram_of_screen_times_by_video(name, show_name,
                                            screen_time_by_video_id):
    """
    Make a histogram of the per video screen times
    """
    histogram_dict = defaultdict(list)
    for k, v in screen_time_by_video_id.items():
        histogram_dict[int(v / 60) + 1].append(k)

    videos_with_no_screen_time = Video.objects.filter(
        show__name=show_name
    ).exclude(
        id__in=[x for x in screen_time_by_video_id]
    )
    
    videos_with_faces = [x['shot__video__id'] for x in 
                         Face.objects.filter(
                             shot__video__show__name=show_name
                         ).distinct(
                            'shot__video'
                         ).values('shot__video__id')]

    videos_with_no_screen_time_and_no_faces = videos_with_no_screen_time.exclude(id__in=videos_with_faces)
    videos_with_no_screen_time_but_with_faces = videos_with_no_screen_time.filter(id__in=videos_with_faces)
    
    histogram_dict[0] = [x.id for x in videos_with_no_screen_time_but_with_faces]
    
    def make_plot(data):
        fig, ax1 = plt.subplots()

        ind = np.arange(len(data))
        width = 0.5
        rect1 = ax1.bar(ind, [y for _, y in data], width,
                        color='SkyBlue')
        ax1.set_ylabel('Video count', fontsize=14)
        ax1.set_title('Histogram of {} screen time across videos for "{}"'.format(name, show_name))
        ax1.set_xticks(ind)
        ax1.set_xlabel('Minutes', fontsize=14)
        ax1.set_xticklabels(ind)
        plt.show()
    
    make_plot([
        (x, len(histogram_dict[x])) for x in sorted(histogram_dict.keys())
    ])
    

def plot_screentime_over_time(name, show_name, screen_time_by_video_id):
    """
    Plot a scatterplot of screentime over time
    """
    histogram_dict = defaultdict(list)
    for k, v in screen_time_by_video_id.items():
        histogram_dict[int(v / 60) + 1].append(k)

    videos_with_no_screen_time = Video.objects.filter(
        show__name=show_name
    ).exclude(
        id__in=[x for x in screen_time_by_video_id]
    )
    
    videos_with_faces = [x['shot__video__id'] for x in 
                         Face.objects.filter(
                             shot__video__show__name=show_name
                         ).distinct(
                            'shot__video'
                         ).values('shot__video__id')]

    videos_with_no_screen_time_and_no_faces = videos_with_no_screen_time.exclude(id__in=videos_with_faces)
    videos_with_no_screen_time_but_with_faces = videos_with_no_screen_time.filter(id__in=videos_with_faces)
    
    histogram_dict[0] = [x.id for x in videos_with_no_screen_time_but_with_faces]
    
    def make_plot():
        videos = Video.objects.filter(
            id__in=[x for x in screen_time_by_video_id.keys()]
        ).order_by('time')
        x = []
        y = []
        for video in videos:
            x.append(video.time)
            y.append(screen_time_by_video_id[video.id] / 60.)    
        plt.plot(x, y, '.', linewidth=1)

        x2 = [x.time for x in videos_with_no_screen_time_and_no_faces]
        y2 = [0] * len(x2)
        plt.plot(x2, y2, 'rx')

        plt.title('Screen time for {} on "{}" over time'.format(name, show_name))
        plt.ylabel('Screentime (min)')
        plt.xlabel('Date')
        plt.show()
    make_plot()
    
    
def plot_distribution_of_appearance_times_by_video(model, show_name):
    """
    Plot the distribution of appearances (shot beginnings)
    """
    def screen_time_by_appearance_time_per_bucket(args):
        bucket, precision, face_ids, show_name = args
        if precision > 0.:
            query_results = Shot.objects.filter(
                id__in=[
                    x['shot__id'] for x in 
                    Face.objects.filter(id__in=face_ids).distinct('shot').values('shot__id')
                ],
                video__show__name=show_name, 
                in_commercial=False,
            ).annotate(
                appearance_time=Cast(F('min_frame') / F('video__fps'), IntegerField())
            ).values(
                'appearance_time'
            ).annotate(
                count=Count('appearance_time')
            )
            return { x['appearance_time'] : x['count'] * precision for x in query_results }
        else:
            return {}
    
    screen_time_by_appearance = Counter()
    args_list = [(k, model.precision_by_bucket[k], model.face_ids_by_bucket[k], show_name)
                 for k in sorted(model.buckets)]
    results = par_for(screen_time_by_appearance_time_per_bucket, args_list)
    for x in results:
        for k, v in x.items():
            screen_time_by_appearance[int(k / 60)] += v
    
    def make_plot(data):
        fig, ax1 = plt.subplots()

        ind = np.arange(len(data))
        width = 0.5
        rect1 = ax1.bar(ind, [y for _, y in data], width,
                        color='SkyBlue')
        ax1.set_ylabel('Count', fontsize=14)
        ax1.set_title('Distribution of {} appearance times across videos for "{}"'.format(model.name, show_name))
        ax1.set_xticks(ind)
        ax1.set_xlabel('Minute in show', fontsize=14)
        ax1.set_xticklabels(ind)
        plt.show()
    
    make_plot([
        (x, screen_time_by_appearance[x]) for x in sorted(screen_time_by_appearance.keys())
    ])
    

major_shows = []
with open('/app/major_shows.pkl', 'rb') as f:
    major_shows_frame = pickle.load(f)
    for show in major_shows_frame:
        major_shows.append(str(show))
        
# Cache this
total_shot_time_by_show = None


def get_total_shot_time_by_show():
    global total_shot_time_by_show
    if total_shot_time_by_show is None:
        query_results = Shot.objects.filter(
            video__show__name__in=major_shows, in_commercial=False,
        ).values(
            'video__show__name'
        ).annotate(
            screen_time=Sum((F('max_frame') - F('min_frame')) / F('video__fps'),
                            output_field=FloatField())
        )
        total_shot_time_by_show = { 
            x['video__show__name'] : x['screen_time'] for x in query_results 
        }
    return total_shot_time_by_show


def get_screen_time_by_show(model):
    """
    Return the screentime by show name in a dict
    """
    def total_screen_time_by_bucket(args):
        bucket, precision, face_ids, major_shows = args
        if precision > 0:
            query_result = Face.objects.filter(
                id__in=face_ids, shot__video__show__name__in=major_shows,
                shot__in_commercial=False,
            ).values(
                'shot__video__show__name'
            ).annotate(
                screen_time=Sum(
                    (F('shot__max_frame') - F('shot__min_frame')) / F('shot__video__fps'), 
                    output_field=FloatField()
                )
            )
            return { x['shot__video__show__name'] : precision * x['screen_time'] 
                    for x in query_result } 
        else:
            return {}
    screen_time_by_show = defaultdict(float)
    
    args_list = [(k, model.precision_by_bucket[k], model.face_ids_by_bucket[k], major_shows)
                 for k in sorted(model.buckets)]
    results = par_for(total_screen_time_by_bucket, args_list)
    
    for x in results:
        for k, v in x.items():
            screen_time_by_show[k] += v

    return [x for x in screen_time_by_show.items()]


def plot_screen_time_by_show(name, screen_time_by_show):
    """
    Plot per show screentime
    """
    def plot_bar_chart_by_show_raw(data):
        fig, ax1 = plt.subplots()

        ind = np.arange(len(data))
        width = 0.5
        rect1 = ax1.bar(ind, [y for _, y in data], width,
                        color='SkyBlue')
        ax1.set_ylabel('Minutes', fontsize=14)
        ax1.set_title('Minutes of non-commercial screen time by show for {}'.format(name))
        ax1.set_xticks(ind)
        ax1.set_xlabel('Show name', fontsize=14)
        ax1.set_xticklabels([x for x, _ in data], rotation=45,ha='right')
        plt.show()
    
    data_to_plot = []
    for show, screen_time in sorted(screen_time_by_show, 
                                    key=lambda x: x[1]):
        data_to_plot.append((show, screen_time / 60.))
    plot_bar_chart_by_show_raw(data_to_plot)
        
    def plot_bar_chart_by_show_scaled(data):
        fig, ax1 = plt.subplots()

        ind = np.arange(len(data))
        width = 0.5
        rect1 = ax1.bar(ind, [y for _, y in data], width,
                        color='SkyBlue')
        ax1.set_ylabel('Proportion', fontsize=14)
        ax1.set_title('Proportion of non-commercial screen time by show for {}'.format(name))
        ax1.set_xticks(ind)
        ax1.set_xlabel('Show name', fontsize=14)
        ax1.set_xticklabels([x for x, _ in data], rotation=45,ha='right')
        plt.show()

    data_to_plot = []
    for show, screen_time in sorted(screen_time_by_show, 
                                    key=lambda x: x[1]):
        data_to_plot.append((show,  screen_time / get_total_shot_time_by_show()[show]))
    plot_bar_chart_by_show_scaled(list(sorted(data_to_plot, key=lambda x: x[1])))
    