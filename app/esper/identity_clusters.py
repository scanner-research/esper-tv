from esper.prelude import *
from esper.stdlib import *
from esper.plot_util import plot_time_series, plot_heatmap_with_images
from esper.identity import faces_to_tiled_img
from query.models import *

import random
from collections import Counter
from datetime import datetime

from django.db.models import ExpressionWrapper, F, FloatField

try:
    from IPython.display import clear_output
except ImportError as e:
    print('Failed to import clear_output')
    clear_output = lambda: None


CENTROID_EST_SAMPLES = 50
    

def _get_cluster_images(clusters, n, c):
    cluster_images = [None] * len(clusters)
    for cluster_id, face_ids in clusters.items():
        im = faces_to_tiled_img(
            Face.objects.filter(id__in=face_ids).order_by('?')[:n], 
            cols=c
        )
        cluster_images[cluster_id] = im
    return cluster_images


def _recluster_clusters(clusters, merge_cluster_threshold):
    cluster_samples = []
    cluster_clusters = []
    cluster_nsamples = {}
    for k, v in clusters.items():
        cluster_nsamples[k] = min(len(v), CENTROID_EST_SAMPLES)
        cluster_samples.extend(random.sample(v, cluster_nsamples[k]))
        cluster_clusters.extend([k] * cluster_nsamples[k])
    est_centroids = {}
    for cluster_id, features in zip(cluster_clusters, face_features(cluster_samples)):
        if cluster_id not in est_centroids:
            est_centroids[cluster_id] = features / cluster_nsamples[cluster_id]
        else:
            est_centroids[cluster_id] += features / cluster_nsamples[cluster_id]

    def _find_meta_cluster(meta_clusters, k):
        for i, c in enumerate(meta_clusters):
            if k in c:
                return i
        raise Exception('Not found')

    def _merge_meta_clusters(meta_clusters, i, j):
        i_idx = _find_meta_cluster(meta_clusters, i)
        j_idx = _find_meta_cluster(meta_clusters, j)
        if i_idx != j_idx:
            meta_clusters[i_idx].update(meta_clusters[j_idx])
            del meta_clusters[j_idx]
        return meta_clusters

    meta_clusters = [{i} for i in range(k)]
    for i in range(k):
        for j in range(i + 1, k):
            if np.linalg.norm(est_centroids[i] - est_centroids[j]) <= merge_cluster_threshold:
                meta_clusters = _merge_meta_clusters(meta_clusters, i, j)

    new_clusters = defaultdict(list)
    for i, l in enumerate(meta_clusters):
        for cluster_id in l:
            new_clusters[i].extend(clusters[cluster_id])
    return new_clusters


def _manual_recluster(clusters, examples_per_cluster):
    cluster_images = _get_cluster_images(clusters, n=examples_per_cluster,
                                         c=examples_per_cluster)
    
    def _show_clusters(cluster_ids):
        for cluster_id in sorted(cluster_ids):
            print('Cluster {} ({} faces)'.format(cluster_id, len(clusters[cluster_id])))
            imshow(cluster_images[cluster_id])
            plt.show()

    def _get_remaining_clusters(meta_clusters):
        meta_cluster_set = set()
        for l in meta_clusters: 
            meta_cluster_set.update(l)
        return set(clusters.keys()) - meta_cluster_set 

    discarded_clusters = set()
    meta_clusters = []
    while True:
        clear_output()
        remaining_clusters = _get_remaining_clusters(meta_clusters) - discarded_clusters
        if len(remaining_clusters) == 0:
            break
        elif len(remaining_clusters) == 1:
            meta_clusters.append(list(remaining_clusters))
            break
        else:
            _show_clusters(remaining_clusters)

        try:
            line = input(
                'Enter a cluster delimited by ","s ("d" if done, "-" to discard): [choices: {}]: '.format(
                    ', '.join([str(i) for i in sorted(remaining_clusters)])
                )
            )
            line = line.strip()
            if line == '':
                continue
            elif line == 'd':
                for i in remaining_clusters:
                    meta_clusters.append([i])
            elif line[0] == '-':
                cluster_to_discard = -int(line)
                if cluster_to_discard not in remaining_clusters:
                    raise Exception('{} is not a choice for discarding'.format(cluster_to_discard))
                discarded_clusters.add(cluster_to_discard)
            else:
                choices = [int(s.strip()) for s in line.split(',') if s.strip() != '']
                for choice in choices:
                    if choice not in remaining_clusters:
                        raise Exception('{} is not a valid choice. Try again.')
                else:
                    meta_clusters.append(choices)
        except Exception as e:
            print(e)
    clear_output()

    recluster = defaultdict(list)
    for i, l in enumerate(meta_clusters):
        for j in l:
            recluster[i].extend(clusters[j])
    return recluster


def identity_clustering_workflow(
    name, examples_per_cluster=10,
    face_probability_threshold=0.9, 
    merge_cluster_threshold=0.2, 
    init_clusters=10, 
    exclude_commercials=True,
    duration_label_unit='m',
    show_titles=True,
    save_paths=None,
):
    """
    Cluster faces associated with a name and plot heatmaps of the distribution of the faces 
    across shows.
    
    face_probability_threshold: minimum probability face to consider
    examples_per_cluster: number of examples to plot
    merge_cluster_threshold: l2 threshold for merging clusters automatically
    init_clusters: number of initial clusters (k for k-means)
    """

    channels = [c.name for c in Channel.objects.all()]
    
    extra_kwargs = {}
    if exclude_commercials:
        extra_kwargs['face__shot__in_commercial'] = False
    face_id_to_info = {
        x['face__id'] : { 
            'channel' : x['face__shot__video__channel__name'],
            'screentime' : x['screentime'],
            'time': x['face__shot__video__time']
        } for x in FaceIdentity.objects.filter(
            identity__name=name.lower(), 
            probability__gt=face_probability_threshold, 
            **extra_kwargs
        ).annotate(
            screentime=ExpressionWrapper(
                (F('face__shot__max_frame') - F('face__shot__min_frame')) / F('face__shot__video__fps'), 
                output_field=FloatField()
            )
        ).values(
            'face__id', 'face__shot__video__channel__name', 
            'screentime', 'face__shot__video__time'
        )
    }
        
    clusters = defaultdict(list)
    for face_id, cluster_id in face_kmeans(list(face_id_to_info.keys()), k=init_clusters):
        clusters[cluster_id].append(face_id)
    clusters = _recluster_clusters(clusters, merge_cluster_threshold)
    clusters = _manual_recluster(clusters, examples_per_cluster)
    
    def _sort_clusters_by_screentime(clusters):
        return {
            i : v for i, v in enumerate(sorted(
                clusters.values(), 
                key=lambda l: sum(face_id_to_info[x]['screentime'] for x in l)
            ))
        }
    clusters = _sort_clusters_by_screentime(clusters)
    
    cluster_images = _get_cluster_images(clusters, n=examples_per_cluster,
                                         c=examples_per_cluster)
    
    def _truncate_to_date(dt):
        return datetime(year=dt.year, month=dt.month, day=dt.day)
    
    # Visualize the clusters
    min_time = min(v['time'] for v in face_id_to_info.values() if v['time'] is not None)
    max_time = max(v['time'] for v in face_id_to_info.values() if v['time'] is not None)
    for cluster_id in clusters:
        
        # Compute cluster composition
        channel_counts = Counter()
        for face_id in clusters[cluster_id]:
            channel_counts[face_id_to_info[face_id]['channel']] += 1
            
        print('Cluster {} ({} faces): {}'.format(
            cluster_id, 
            len(clusters[cluster_id]),
            ', '.join([
                '{}: {:0.1f}%'.format(
                    channel,
                    100 * channel_counts[channel] / len(clusters[cluster_id])
                ) for channel in channels
            ])
        ))
        imshow(cluster_images[cluster_id])
        plt.show()
        
        channels_to_date_to_screentime = defaultdict(lambda: defaultdict(float))
        for face_id in clusters[cluster_id]:
            face_info = face_id_to_info[face_id]
            channels_to_date_to_screentime[
                face_info['channel']
            ][_truncate_to_date(face_info['time'])] += face_info['screentime'] / 60
        
        plot_time_series(
            channels, 
            [channels_to_date_to_screentime[c] for c in channels],
            'Timeline of Images from Cluster {}'.format(cluster_id),
            'Screentime (min)',
            plotstyle='o',
            min_time=min_time, 
            max_time=max_time,
            figsize=(20, 2)
        )
    
    # Make heatmap
    raw_heatmap = np.zeros((len(clusters), len(channels)))
    for cluster_id in sorted(clusters):
        face_ids = clusters[cluster_id]
        for face_id in face_ids:
            raw_heatmap[cluster_id][
                channels.index(face_id_to_info[face_id]['channel'])
            ] += face_id_to_info[face_id]['screentime']
            
    def heatmap_raw_label_fn(x):
        if duration_label_unit == 'm':
            x /= 60
        elif duration_label_unit == 'h':
            x /= 3600
        elif duration_label_unit == 's':
            pass
        else:
            raise Exception('Unknown unit: {}'.format(duration_label_unit))
            
        if x <= 1e-4:
            return '0{}'.format(duration_label_unit)
        elif x < 1:
            return '<1{}'.format(duration_label_unit)
        else:
            return '{:d}{}'.format(int(x), duration_label_unit)
            
    plot_heatmap_with_images(
        raw_heatmap, channels, cluster_images,
        'Images of {} and Screen Time'.format(name) if show_titles else '',
        heatmap_label_fn=heatmap_raw_label_fn,
        save_path=save_paths[0] if save_paths else None
    )
    plot_heatmap_with_images(
        raw_heatmap / raw_heatmap.sum(axis=1)[:, np.newaxis],
        channels, cluster_images,
        'Images of {} and Screen Time (Row Normalized: Distribution Across Channels)'.format(name) if show_titles else '',
        save_path=save_paths[1] if save_paths else None
    )
    plot_heatmap_with_images(
        raw_heatmap / raw_heatmap.sum(axis=0)[np.newaxis, :], 
        channels, cluster_images,
        'Images of {} and Screen Time (Column Normalized: Distribution on a Channel)'.format(name) if show_titles else '',
        save_path=save_paths[2] if save_paths else None
    )
