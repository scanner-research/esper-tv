from esper.prelude import *
from esper.stdlib import *
from esper.major_canonical_shows import *
from query.models import *
from esper.plot_util import *
from esper.face_embeddings import knn, kmeans

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
from datetime import timedelta
from pandas import DataFrame

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


def minutesToSeconds(x):
    return x * 60


def secondsToMinutes(x):
    return x / 60


def random_hex_string(length):
    return ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length))


class FaceIdentityModel(object):
    """
    Standardized results from a run of the face identity model
    """
    
    def __init__(self, name, face_ids_by_bucket, face_ids_to_score, precision_by_bucket,
                 model_params):
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
    
    def get_face_ids_above_threshold(self, precision_thresh):
        selected_ids = []
        for k in sorted(self.buckets):
            if self.precision_by_bucket[k] >= precision_thresh:
                selected_ids.extend(self.face_ids_by_bucket[k])
        return selected_ids
    
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
    

def commit_face_identities_to_db(model, person, labeler, min_threshold=0.001):
    """person is a Thing and labeler is a Labeler"""
    id_set = set()
    
    # build score interpolation function
    f_x = []
    f_y = []
    for k in sorted(model.buckets):
        f_x.append((k[0] + k[1]) / 2.)
        f_y.append(model.precision_by_bucket[k])
    
    with transaction.atomic():
        to_create = []
        for k in sorted(model.buckets):
            # Skip if the whole bucket is less than the threshold
            if np.interp(k[0], f_x, f_y) < min_threshold and np.interp(k[1], f_x, f_y) < min_threshold:
                continue
                
            face_ids = model.face_ids_by_bucket[k]
            face_scores = [model.face_ids_to_score[x] for x in face_ids]
            face_probs = [float(x) for x in np.interp(face_scores, f_x, f_y)]
            for i, p in zip(face_ids, face_probs):
                if p >= min_threshold:
                    if i in id_set:
                        print('Warning: face id {} is duplicated in more than one bucket'.format(i))
                        continue
                    else:
                        id_set.add(i)
                    to_create.append(FaceIdentity(
                        face_id=i,
                        probability=p, 
                        labeler=labeler, 
                        identity=person
                    ))
        FaceIdentity.objects.bulk_create(to_create)


class PrecisionModel(object):
    """
    This class is a bit of a hack to encapsulate code that would otherwise be spread across several
    Jupyter cells.
    """
    
    def __init__(self, face_ids_by_bucket, show_name=None,
                 num_samples_per_bucket=50):
        """
        Initialize a precision model. If show_name is passed, then only faces from that
        show will be sampled and displayed to the user.
        """
        sorted_buckets = sorted(face_ids_by_bucket.keys())
        lower_buckets = sorted_buckets[:int(len(sorted_buckets) / 2)]
        upper_buckets = sorted_buckets[len(lower_buckets):]

        def sample_buckets(buckets, n):
            filter_ids = None
            if show_name is not None:
                filter_ids = set(
                    [
                        x['id'] for x in 
                        Face.objects.filter(
                            shot__video__show__canonical_show__name=show_name
                        ).values('id')
                    ]               
                )
            
            idx_to_face_ids = []
            idx_to_bucket = []
            for k in buckets:
                face_ids = face_ids_by_bucket[k]
                if filter_ids is not None:
                    face_ids_for_show = list(filter(lambda x: x in filter_ids, face_ids))
                    if len(face_ids_for_show) > 0:
                        face_ids = face_ids_for_show
                    else:
                        print(('Bucket {} would be empty using only faces from "{}". '
                               'Using all faces for bucket instead.').format(k, show_name))
                sample_ids = random.sample(face_ids, k=min(len(face_ids), n))
                idx_to_face_ids.extend(sample_ids)
                idx_to_bucket.extend([k] * len(sample_ids))
            assert(len(idx_to_face_ids) == len(idx_to_bucket))
            return idx_to_face_ids, idx_to_bucket

        lower_face_ids, self.lower_coresp_buckets = sample_buckets(
            lower_buckets, n=num_samples_per_bucket
        )
        upper_face_ids, self.upper_coresp_buckets = sample_buckets(
            upper_buckets, n=num_samples_per_bucket
        )

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
            
    def get_lower_widget(self, crop=True):
        return esper_widget(self.lower_qs_result, crop_bboxes=crop)
    
    def get_upper_widget(self, crop=True):
        return esper_widget(self.upper_qs_result, crop_bboxes=crop)
    
    def compute_precision_for_lower_buckets(self, selected_idxs):
        expected_count_by_bucket = Counter()
        error_count_by_bucket = Counter()
        for k in self.lower_coresp_buckets:
            expected_count_by_bucket[k] += 1
        for i in selected_idxs:
            error_count_by_bucket[self.lower_coresp_buckets[-(i + 1)]] += 1

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


def faces_to_tiled_img(faces, cols=12):
    def face_img(face):
        return crop(load_frame(face.person.frame.video, face.person.frame.number, []), face)
    
    face_imgs = par_for(face_img, faces, progress=False)
    im = tile_images([cv2.resize(img, (200, 200)) for img in face_imgs], cols=cols)
    return im
    
    
def load_and_select_faces_from_images(img_dir):
    
    def yn_prompt(msg):
        while True:
            x = input(msg)
            if x == '' or x.lower() == 'y':
                return True
            elif x.lower() == 'n':
                return False
    
    img_to_faces = embed_google_images.detect_faces_in_images(img_dir)
    
    candidate_face_imgs = []
    for img_path, face_imgs in img_to_faces.items():
        if len(face_imgs) != 1:
            continue
        candidate_face_imgs.extend(face_imgs)
    imshow(tile_images([cv2.resize(img, (200, 200)) for img in candidate_face_imgs], cols=10))
    plt.show()
    if not yn_prompt('These are the candidate faces from Google Image Search. The next step '
                     'is to choose whether to keep each image. ' 
                     'Do you wish to continue to the next step? [Y/n] '):
        raise RuntimeError('User aborted labeling')
    clear_output()
    
    selected_crops = []
    for img_path, face_imgs in img_to_faces.items():
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


def face_search_by_embeddings(embs, increment=0.05, max_thresh=1.2,
                              exclude_labeled=False):
    min_thresh = 0.
    face_sims = knn(targets=embs, max_threshold=max_thresh)
    
    face_ids_to_score = {}
    results_by_bucket = {}
    
    for face_id, score in face_sims:
        if score >= min_thresh and score < max_thresh:
            face_ids_to_score[face_id] = score
            t = min_thresh + int((score - min_thresh) / increment) * increment
            bucket = (t, t + increment)
            if bucket not in results_by_bucket:
                results_by_bucket[bucket] = []
            results_by_bucket[bucket].append(face_id)

    if len(results_by_bucket) == 0:
        raise Exception('No results to show')
        
    return results_by_bucket, face_ids_to_score


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
    
    plt.title('Estimated precision and CDF curve for {}'.format(model.name))
    plt.xlabel('Distance threshold')
    plt.legend()
    
    plt.show()


gender_display_names = {
    'M' : 'Male',
    'F' : 'Female',
    'U' : 'Unknown'
}
    
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
            gender_breakdown[gender_display_names[k]] += v
    return gender_breakdown


def show_gender_examples(model, precision_thresh=0.8, n=50):
    """
    Tiled examples for each gender pertaining to a labeled identity
    """
    selected_ids = model.get_face_ids_above_threshold(precision_thresh)
    
    results = []
    for gender in ['M', 'F', 'U']:
        ids = [
            x['face__id'] for x in FaceGender.objects.filter(
                face__id__in=selected_ids, gender__name=gender
            ).distinct('face__id').values('face__id')[:n]
        ]
        key = '{} instances of "{}" with identity probability greater than {:0.1f}%.'.format(
            gender_display_names[gender], model.name, precision_thresh * 100)
        results.append((key, qs_to_result(Face.objects.filter(id__in=ids))))
    return esper_widget(group_results(results), crop_bboxes=True)
        

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
        ax1.set_ylabel('Count')
        ax1.set_title('Distribution of {} face sizes across non-commercial videos'.format(model.name))
        ax1.set_xticks(ind)
        ax1.set_xlabel('Area (%)')
        
        xlabels = [str(x) for x in ind]
        xlabels[-1] = '>= {}'.format(xlabels[-1])
        
        ax1.set_xticklabels(xlabels)
        plt.show()
    
    make_plot([
        (x, face_size_hist[x]) for x in sorted(face_size_hist.keys())
    ])
    
    
def show_faces_by_size(model, precision_thresh=0.8, n=5):
    """
    Show a widget with groups of faces by size
    """
    selected_ids = model.get_face_ids_above_threshold(precision_thresh)
            
    base_qs = Face.objects.filter(
        id__in=selected_ids,
        shot__in_commercial=False,
    ).annotate(
        bbox_area=Cast((F('bbox_x2') - F('bbox_x1')) * (F('bbox_y2') - F('bbox_y1')) * 100 , IntegerField())
    )
    
    results = []
    increment = 2.5
    for min_t in frange(0, 100, increment):
        max_t = min_t + increment
        face_qs = base_qs.filter(bbox_area__gt=min_t, bbox_area__lt=max_t)
        if face_qs.count() > 0:
            results.append((
                'Faces covering between {}% and {}% of the frame'.format(min_t, max_t),
                qs_to_result(face_qs, limit=n)
            ))
    return esper_widget(group_results(results))
    

def get_screen_time_by_video(model, show_name):
    """
    Return a dictionary from video id to timedeltas for single show
    """
    def screen_time_by_video_per_bucket(args):
        bucket, precision, face_ids, show_name = args
        if precision > 0.:
            query_results = Shot.objects.filter(
                id__in=[
                    x['shot__id'] for x in 
                    Face.objects.filter(id__in=face_ids).distinct('shot').values('shot__id')
                ],
                video__show__canonical_show__name=show_name, in_commercial=False,
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
    
    return { k : timedelta(seconds=v) for k, v in screen_time_by_video_id.items() } 


def compute_screen_time_by_video(model, show_name):
    raise NotImplementedError('Renamed to get_screen_time_by_video')


def plot_histogram_of_screen_times_by_video(name, show_name,
                                            screen_time_by_video_id):
    """
    Make a histogram of the per video screen times
    """
    histogram_dict = defaultdict(list)
    for k, v in screen_time_by_video_id.items():
        histogram_dict[int(secondsToMinutes(v.total_seconds())) + 1].append(k)

    videos_with_no_screen_time = Video.objects.filter(
        show__name=show_name
    ).exclude(
        id__in=[x for x in screen_time_by_video_id]
    )
    
    videos_with_faces = [
        x['shot__video__id'] for x in 
        Face.objects.filter(
         shot__video__show__canonical_show__name=show_name
        ).distinct(
        'shot__video'
        ).values('shot__video__id')
    ]

    videos_with_no_screen_time_and_no_faces = videos_with_no_screen_time.exclude(id__in=videos_with_faces)
    videos_with_no_screen_time_but_with_faces = videos_with_no_screen_time.filter(id__in=videos_with_faces)
    
    histogram_dict[0] = [x.id for x in videos_with_no_screen_time_but_with_faces]
    
    def make_plot(data):
        fig, ax1 = plt.subplots()

        ind = np.arange(len(data))
        width = 0.5
        rect1 = ax1.bar(ind, [y for _, y in data], width,
                        color='SkyBlue')
        ax1.set_ylabel('Video count')
        ax1.set_title('Histogram of {} screen time across videos for "{}"'.format(name, show_name))
        ax1.set_xticks(ind)
        ax1.set_xlabel('Minutes')
        ax1.set_xticklabels(ind)
        plt.show()
    
    make_plot([
        (x, len(histogram_dict[x])) for x in sorted(histogram_dict.keys())
    ])
    

def plot_screentime_over_time(names, show_name, screen_times_by_video_id):
    """
    Plot a scatterplot of screentime over time
    
    names is a list of names or a single name
    screen_times_by_video_id is a dict of video_id to screen_time in seconds
    or a list of such dicts
    """
    # TODO: fix xlim on time ranged plots
    
    if not isinstance(names, list):
        names = [names]
        screen_times_by_video_id = [screen_times_by_video_id]
    assert len(names) == len(screen_times_by_video_id)
    
    videos_with_faces = [
        x['shot__video__id'] for x in 
            Face.objects.filter(
                shot__video__show__canonical_show__name=show_name
            ).distinct(
                'shot__video'
            ).values('shot__video__id')
        ]
    videos_with_no_faces = Video.objects.filter(
        show__name=show_name
    ).exclude(id__in=videos_with_faces)
    
    for i, (name, screen_time_by_video_id) in enumerate(zip(names, screen_times_by_video_id)):
        histogram_dict = defaultdict(list)
        for k, v in screen_time_by_video_id.items():
            histogram_dict[int(secondsToMinutes(v.total_seconds())) + 1].append(k)

        videos_with_no_screen_time = Video.objects.filter(
            show__name=show_name
        ).exclude(
            id__in=[x for x in screen_time_by_video_id]
        )
        videos_with_no_screen_time_but_with_faces = \
            videos_with_no_screen_time.filter(id__in=videos_with_faces)
    
        videos = Video.objects.filter(
            id__in=[x for x in screen_time_by_video_id.keys()]
        ).order_by('time')
        x = []
        y = []
        for video in videos:
            x.append(video.time)
            y.append(secondsToMinutes(screen_time_by_video_id[video.id].total_seconds()))    
        plt.scatter(x, y, s=1., label=name, color=get_color(i))
        
    # Plot xs for all videos with not faces
    xe = [video.time for video in videos_with_no_faces]
    ye = [0] * len(xe)
    plt.plot(xe, ye, 'x', color='Black', label='Videos with no faces')

    plt.legend()
    plt.title('Screen time for {} on "{}" over time'.format(
              ' & '.join(names), show_name))
    plt.ylabel('Screentime (min)')
    plt.xlabel('Date')
    plt.show()
    
    
def plot_distribution_of_appearance_times_by_video(model, show_name, max_minute=180):
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
                video__show__canonical_show__name=show_name, 
                in_commercial=False,
            ).annotate(
                appearance_time=Cast(F('min_frame') / F('video__fps'), IntegerField())
            ).filter(
                appearance_time__lt=max_minute * 60
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
            screen_time_by_appearance[int(secondsToMinutes(k))] += v
    
    def make_plot(data):
        fig, ax1 = plt.subplots()

        ind = np.arange(len(data))
        width = 0.5
        rect1 = ax1.bar(ind, [y for _, y in data], width,
                        color='SkyBlue')
        ax1.set_ylabel('Count')
        ax1.set_title('Distribution of {} appearance times across videos for "{}"'.format(model.name, show_name))
        ax1.set_xticks(ind)
        ax1.set_xlabel('Minute in show')
        ax1.set_xticklabels([str(i) if i % 5 == 0 else '' for i in ind])
        plt.show()
    
    make_plot([
        (x, screen_time_by_appearance[x]) for x in sorted(screen_time_by_appearance.keys())
    ])
    
    
def plot_distribution_of_identity_probabilities(model, show_name, bin_range=(20, 100)):
    """
    Plot a distribution of probabilites for a show and identity
    """
    filtered_face_ids = set()
    for k in model.buckets:
        if model.precision_by_bucket[k] > 0:
            face_ids = model.face_ids_by_bucket[k]
            filtered_face_ids.update([
                x['id'] for x in Face.objects.filter(
                    id__in=face_ids, shot__video__show__canonical_show__name=show_name
                ).values('id')
            ])
        
    # build score interpolation function
    f_x = []
    f_y = []
    for k in sorted(model.buckets):
        f_x.append((k[0] + k[1]) / 2.)
        f_y.append(model.precision_by_bucket[k])
    
    face_probs = np.interp([model.face_ids_to_score[x] for x in filtered_face_ids], f_x, f_y).tolist()
    
    if bin_range[0] == 0:
        zero_prob_count = Face.objects.filter(shot__video__show__canonical_show__name=show_name).count() - len(face_probs)
        if zero_prob_count > 0:
            face_probs.extend([0.] * zero_prob_count)
    
    plt.hist([x * 100 for x in face_probs], color='SkyBlue', range=bin_range)
    plt.title('Distribution of face identity probabilites for {} on "{}"'.format(model.name, show_name))
    plt.ylabel('Count')
    plt.xlabel('Face identity probability')
    plt.show()


def get_screen_time_by_show(model, date_range=None):
    """
    Return the screentime by show name in a dict
    """
    def total_screen_time_by_bucket(args):
        bucket, precision, face_ids, major_canonical_shows = args
        if precision > 0:
            qs = Face.objects.filter(
                id__in=face_ids, shot__video__show__canonical_show__name__in=major_canonical_shows,
                shot__in_commercial=False)
            if date_range is not None:
                qs = qs.filter(shot__video__time__range=date_range)
            query_result = qs.values(
                'shot__video__show__canonical_show__name'
            ).annotate(
                sum_screen_time=Sum(
                    (F('shot__max_frame') - F('shot__min_frame')) / F('shot__video__fps'), 
                    output_field=FloatField()
                ),
                sum_screen_time_sq=Sum(
                    ((F('shot__max_frame') - F('shot__min_frame')) / F('shot__video__fps')) ** 2,
                    output_field=FloatField()
                )
            )
            return { 
                x['shot__video__show__canonical_show__name'] : (
                    precision * x['sum_screen_time'], # value
                    (1. - precision) * precision * x['sum_screen_time_sq'] # variance
                ) for x in query_result 
            } 
        else:
            return {}
    screen_time_by_show = defaultdict(float)
    var_in_screen_time_by_show = defaultdict(float)
    
    args_list = [(k, model.precision_by_bucket[k], model.face_ids_by_bucket[k], MAJOR_CANONICAL_SHOWS)
                 for k in sorted(model.buckets)]
    results = par_for(total_screen_time_by_bucket, args_list)
    
    for x in results:
        for k, v in x.items():
            screen_time_by_show[k] += v[0]
            var_in_screen_time_by_show[k] += v[1]

    return {
        k : (timedelta(seconds=v), var_in_screen_time_by_show[k])
        for k, v in screen_time_by_show.items()
    }


def plot_screen_time_by_show(names, screen_times_by_show, 
                             normalize_by_total_runtime=False,
                             title=None, xlabel=None, figsize=(20,10)):
    """
    Plot per show screentime
    
    Names is either a single name or a list of names.
    Likewise, screen_times_by_show is either a single dict mapping
    show name to screentime in seconds or a list of such dicts.
    """
    if not isinstance(names, list):
        names = [names]
        screen_times_by_show = [screen_times_by_show]
    assert len(names) == len(screen_times_by_show)
    
    if not normalize_by_total_runtime:
        def plot_bar_chart_by_show_raw(data_by_name):
            fig, ax1 = plt.subplots(figsize=figsize)

            ind = np.arange(len(data_by_name[0]))

            full_width = 0.6
            width = full_width / len(data_by_name)
            for i, data in enumerate(data_by_name):
                ys = [y for _, y, _ in data]
                stds = [1.96 * (z ** 0.5) for _, _, z in data]
                rect = ax1.bar(ind - ((full_width / 2) + (i * width)), ys, 
                               width, color=get_color(i), yerr=stds, 
                               ecolor='black', label=names[i])

            ax1.legend()
            ax1.set_ylim(ymin=0.)
            ax1.set_ylabel('Minutes')
            ax1.set_title('Minutes of non-commercial screen time by show for {}'.format(
                          ' & '.join(names)) if title is None else title)
            ax1.set_xticks(ind - 0.25)
            ax1.set_xlabel('Show name' if xlabel is None else xlabel)
            ax1.set_xticklabels([x for x, _, _ in data], rotation=45, ha='right')
            plt.show()

        show_sort_order = [
            x[0] for x in sorted(screen_times_by_show[0].items(), 
                                 key=lambda x: x[1][0].total_seconds())
        ]

        data_to_plot = []
        for name, screen_time_by_show in zip(names, screen_times_by_show):
            single_show_data_to_plot = []
            for show in show_sort_order:
                screen_time, variance = screen_time_by_show.get(show, (timedelta(0), 0))
                single_show_data_to_plot.append((
                    show, secondsToMinutes(screen_time.total_seconds()), variance / 3600.
                ))
            data_to_plot.append(single_show_data_to_plot)
        plot_bar_chart_by_show_raw(data_to_plot)
        
    else:
        def plot_bar_chart_by_show_scaled(data_by_name):
            fig, ax1 = plt.subplots(figsize=figsize)

            ind = np.arange(len(data_by_name[0]))
            full_width = 0.6
            width = full_width / len(data_by_name)

            for i, data in enumerate(data_by_name):
                stds = [1.96 * (z ** 0.5) for _, _, z in data]
                rect = ax1.bar(ind - full_width / 2 + i * width, 
                               [y for _, y, _ in data], width,
                               yerr=stds, ecolor='black', color=get_color(i),
                               label=names[i])

            ax1.set_ylim(ymin=0.)
            ax1.set_ylabel('Proportion of Show\'s Total Runtime')
            ax1.set_title('Proportion of non-commercial screen time by show for {}'.format(
                          ' & '.join(names)) if title is None else title)
            ax1.legend()
            ax1.set_xticks(ind - 0.25)
            ax1.set_xlabel('Show name' if xlabel is None else xlabel)
            ax1.set_xticklabels([x for x, _, _ in data], rotation=45, ha='right')
            plt.show()

        show_sort_order = None
        data_to_plot = []
        for name, screen_time_by_show in zip(names, screen_times_by_show):
            single_show_data_to_plot = []
            for show, (screen_time, variance) in screen_time_by_show.items():
                total_show_screen_time = get_total_shot_time_by_show()[show].total_seconds()
                single_show_data_to_plot.append((
                    show, screen_time.total_seconds() / total_show_screen_time, 
                    variance / (total_show_screen_time ** 2)
                ))
            if show_sort_order is None:
                show_sort_order = { 
                    x[0] : i for i, x in enumerate(
                        sorted(single_show_data_to_plot, key=lambda x: x[1]))
                }
            data_to_plot.append(list(sorted(
                single_show_data_to_plot, key=lambda x: show_sort_order[x[0]]
            )))
        plot_bar_chart_by_show_scaled(data_to_plot)
    
    
def plot_screen_time_and_other_by_show(name, screen_time_by_show, other_by_show, other_name,
                                       other_units, normalize_by_total_runtime=True, 
                                       sort_by_other=False):
    """
    Plot the screen time for a single person along side another metric. 
    
    screen_time_by_show is a list of tuples of the form (show_name, time_delta, variance_seconds)
    other_by_show is a dict where keys are show_names
    """
    if not normalize_by_total_runtime:
        def plot_bar_chart_by_show_raw(screen_time_data):
            fig, ax1 = plt.subplots()

            ind = np.arange(len(screen_time_data))

            full_width = 0.9
            width = full_width / 2

            ys = [y for _, y, _ in screen_time_data]
            stds = [1.96 * (z ** 0.5) for _, _, z in screen_time_data]
            rect1 = ax1.bar(ind - width, ys, 
                            width, color=get_color(0), yerr=stds, ecolor='black', 
                            label='Screen time')

            ax1.set_ylim(ymin=0.)
            ax1.set_ylabel('Minutes', color=get_color(0))
            ax1.set_title('Minutes of non-commercial screen time and {} by show for {}'.format(
                          other_name.lower(), name))
            ax1.set_xticks(ind)
            ax1.set_xlabel('Show name')
            ax1.set_xticklabels([x for x, _, _ in screen_time_data], rotation=45, ha='right')

            ax2 = ax1.twinx()
            ax2.set_ylabel(other_units,  color=get_color(1))
            ys_other = [other_by_show[x] for x, _, _ in screen_time_data]
            rect2 = ax2.bar(ind, ys_other, width,
                           color=get_color(1), label=other_name)
            fig.legend()
            fig.tight_layout()

            plt.show()

        show_sort_order = { 
            x[0] : i for i, x in enumerate(
                sorted(screen_time_by_show.items(), 
                       key=lambda x: x[1][0].total_seconds() if not sort_by_other else other_by_show[x[0]])
            )
        }

        screen_time_data_to_plot = []
        for show, (screen_time, variance) in sorted(screen_time_by_show.items(), 
                                                    key=lambda x: show_sort_order[x[0]]):
            screen_time_data_to_plot.append((
                show, secondsToMinutes(screen_time.total_seconds()), variance / 3600.
            ))
        plot_bar_chart_by_show_raw(screen_time_data_to_plot)
        
    else:
        normalized_other_by_show = {
            k : v / secondsToMinutes(get_total_shot_time_by_show()[k].total_seconds()) / 60 # hours
            for k, v in other_by_show.items() if k in screen_time_by_show.keys()
        }
        
        def plot_bar_chart_by_show_scaled(screen_time_data):
            fig, ax1 = plt.subplots()

            ind = np.arange(len(screen_time_data))
            full_width = 0.9
            width = full_width / 2

            ys = [y for _, y, _ in screen_time_data]
            stds = [1.96 * (z ** 0.5) for _, _, z in screen_time_data]
            rect1 = ax1.bar(ind - width, ys, 
                            width, color=get_color(0), yerr=stds, ecolor='black', 
                            label='Proportion of screen time')

            ax1.set_ylim(ymin=0.)
            ax1.set_ylabel('Proportion of show\'s total runtime', color=get_color(0))
            ax1.set_title('Proportion of non-commercial screen time and '
                          'normalized {} by show for {}'.format(other_name.lower(), name))

            ax1.set_xticks(ind)
            ax1.set_xlabel('Show name')
            ax1.set_xticklabels([x for x, _, _ in screen_time_data], rotation=45, ha='right')

            ax2 = ax1.twinx()
            ax2.set_ylabel('{} normalized by number of hours'.format(other_units), color=get_color(1))
            ys_other = [normalized_other_by_show.get(x, 0.) for x, _, _ in screen_time_data]
            rect2 = ax2.bar(ind, ys_other, width,
                            color=get_color(1), label=other_name)
            fig.legend()
            fig.tight_layout()
            plt.show()

        screen_time_data_to_plot = []
        for show, (screen_time, variance) in screen_time_by_show.items():
            total_show_screen_time = get_total_shot_time_by_show()[show].total_seconds()
            screen_time_data_to_plot.append((
                show, screen_time.total_seconds() / total_show_screen_time, variance / (total_show_screen_time ** 2)
            ))
        screen_time_data_to_plot.sort(key=lambda x: x[1] if not sort_by_other else normalized_other_by_show[x[0]])
        plot_bar_chart_by_show_scaled(screen_time_data_to_plot)

        
def plot_difference_in_screen_time_by_show(names, screen_times_by_show, color=get_color(0), 
                                           plot_ratio=True):
    assert len(names) == 2
    assert len(screen_times_by_show) == 2
    
    if not plot_ratio:
        def plot_bar_chart_by_show_scaled(data):
            fig, ax1 = plt.subplots()

            ind = np.arange(len(data))
            width = 0.8

            stds = [1.96 * (z ** 0.5) for _, _, z in data]
            rect = ax1.bar(ind - width / 2, 
                           [y for _, y, _ in data], width,
                           yerr=stds, ecolor='black', color=color,
                           label='screentime({}) - screentime({})'.format(*names))

            ax1.set_ylabel('Difference in proportion of show\'s total runtime')
            ax1.set_title('Difference in proportion of non-commercial screen time by show for {}'.format(
                          ' & '.join(names)))
            ax1.legend()
            ax1.set_xticks(ind)
            ax1.set_xlabel('Show name')
            ax1.set_xticklabels([x for x, _, _ in data], rotation=45, ha='right')
            plt.show()

        data_to_plot = []
        for show in screen_times_by_show[0]:
            total_show_time = get_total_shot_time_by_show()[show].total_seconds()
            data_to_plot.append((
                show, 
                (screen_times_by_show[0][show][0].total_seconds() - screen_times_by_show[1][show][0].total_seconds()) 
                / total_show_time, 
                (screen_times_by_show[0][show][1] + screen_times_by_show[1][show][1])
                / (total_show_time ** 2)
            ))
        data_to_plot.sort(key=lambda x: x[1])
        plot_bar_chart_by_show_scaled(data_to_plot)
        
    else:
        def plot_bar_chart_by_show_scaled(data):
            fig, ax1 = plt.subplots()

            ind = np.arange(len(data))
            width = 0.8
            rect = ax1.bar(ind - width / 2, 
                           [y for _, y in data], width,
                           color=color,
                           label='screentime({}) / screentime({})'.format(*names))

            ax1.set_ylabel('Ratio of screentime')
            ax1.set_title('Ratio of non-commercial screen time by show for {}'.format(
                          ' & '.join(names)))
            ax1.legend()
            ax1.set_xticks(ind)
            ax1.set_xlabel('Show name')
            ax1.set_xticklabels([x for x, _ in data], rotation=45, ha='right')
            plt.show()

        data_to_plot = []
        for show in screen_times_by_show[0]:
            total_show_time = get_total_shot_time_by_show()[show].total_seconds()
            data_to_plot.append((
                show, 
                screen_times_by_show[0][show][0].total_seconds() / 
                screen_times_by_show[1][show][0].total_seconds()
            ))
        data_to_plot.sort(key=lambda x: x[1])
        plot_bar_chart_by_show_scaled(data_to_plot)
        

def get_person_in_shot_similarity(models, show_name=None, date_range=None,
                                  precision_thresh=0.8):
    """
    Returns a dict mapping pairs of (p1,p2) to a tuple of jaccard, (p1 & p2 | p1), (p1 & p2 | p2) 
    """
    selected_faces_by_name = {}
    for model in models:
        selected_faces_by_name[model.name] = model.get_face_ids_above_threshold(precision_thresh)
        
    shot_ids_by_name = {}
    for name, face_ids in selected_faces_by_name.items():
        qs = Face.objects.filter(id__in=face_ids)
        if date_range is not None:
            qs = qs.filter(shot__video__time__range=date_range)
        if show_name is not None:
            qs = qs.filter(shot__video__show__canonical_show__name=show_name)
        shot_ids_by_name[name] = {
            x['shot__id'] for x in qs.values('shot__id')
        }
    
    sims = []
    for p1, v1 in shot_ids_by_name.items():
        for p2, v2 in shot_ids_by_name.items():
            if p2 >= p1:
                continue
            intersection = len(v1 & v2)
            sims.append((
                p1, p2,
                intersection / len(v1 | v2), 
                intersection / len(v1), 
                intersection / len(v2)
            ))
    return DataFrame(sims, columns=['Person 1', 'Person 2', 'Jaccard Sim', '(P1&P2)|P1', '(P1&P2)|P2'])
     
    
def get_other_people_who_are_on_screen(model, precision_thresh=0.8, k=25, n_examples_per_cluster=10,
                                       face_blurriness_threshold=10.):
    selected_faces = model.get_face_ids_above_threshold(precision_thresh)
    shot_ids = [x['shot__id'] for x in Face.objects.filter(id__in=selected_faces).values('shot__id')]
    other_face_ids = [
        x['id'] for x in 
        Face.objects.filter(
            shot__id__in=shot_ids, 
            blurriness__gt=face_blurriness_threshold
        ).exclude(id__in=selected_faces).values('id')
    ]
    clusters = defaultdict(list)
    for (i, c) in kmeans(other_face_ids, k=k):
        clusters[c].append(i)
    
    results = []
    for _, ids in sorted(clusters.items(), key=lambda x: -len(x[1])):
        results.append((
            'Cluster with {} faces'.format(len(ids)), 
            qs_to_result(Face.objects.filter(id__in=ids).distinct('shot__video'), 
                         limit=n_examples_per_cluster)
        ))

    return esper_widget(group_results(results))
