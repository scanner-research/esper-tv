from esper.prelude import *
from esper.widget import *
from esper.plot_util import plot_time_series, plot_heatmap_with_images, plot_stacked_bar_chart
from esper.identity import faces_to_tiled_img, export_face_img
import esper.face_embeddings as face_embeddings
from query.models import *
import random
import json
import io
import webbrowser
import os
import sys
import pickle
import PIL.Image
import time
import traceback
import random
import math
import numpy as np
import PIL
from matplotlib import cm
import ipywidgets as widgets
from collections import Counter
from datetime import datetime
from IPython.display import display
from ipywidgets import interact, interactive, fixed, interact_manual
from django.db.models import ExpressionWrapper, F, FloatField
import operator 

global WIDGET_STYLE_ARGS 
WIDGET_STYLE_ARGS = {'description_width': 'initial'}
try:
    from IPython.display import clear_output
except ImportError as e:
    print('Failed to import clear_output')
    clear_output = lambda: None

CENTROID_EST_SAMPLES = 50

def _get_cluster_images(clusters, no_crop, n, c):
    cluster_images = [None] * len(clusters)
    for cluster_id, face_ids in clusters.items():
        im = faces_to_tiled_img(
            Face.objects.filter(id__in=face_ids).order_by('?')[:n],
            no_crop,
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
    for cluster_id, features in zip(cluster_clusters, face_embeddings.features(cluster_samples)):
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

def identity_clustering_workflow(
    name, date, zoom_in_out, examples_per_cluster=10,
    face_probability_threshold=0.9,
    merge_cluster_threshold=0.2,
    init_clusters=10,
    exclude_commercials=False,
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
            'channel' : x['face__frame__video__channel__name'],
            'screentime' : 3.,
            'time': x['face__frame__video__time']
        } for x in FaceIdentity.objects.filter(
            identity__name=name.lower(),
            probability__gt=face_probability_threshold,
            face__frame__sampler=FrameSampler.objects.get(name='3s'),
            **extra_kwargs
        ).values(
            'face__id', 'face__frame__video__channel__name', 
            'face__frame__video__time'
        )
    }
    clusters = defaultdict(list)
    PATH = name + ".txt"
    if os.path.isfile(PATH):
        with open(PATH) as json_file:
            clusters = json.load(json_file)
#         _create_export_json(name, clusters, face_id_to_info)
        _create_export_html(name, clusters, face_id_to_info)
        visualization_workflow(clusters, 'Dec 2, 2015', face_id_to_info, channels, name)
        return
        
    for face_id, cluster_id in face_embeddings.kmeans(list(face_id_to_info.keys()), k=init_clusters):
        clusters[cluster_id].append(face_id)
    clusters = _recluster_clusters(clusters, merge_cluster_threshold)
    intermediate_clusters = (clusters,face_id_to_info,channels, name)
    _manual_recluster(name, intermediate_clusters, date)
#     return (clusters,face_id_to_info,channels, name)
    #end of clustering algorithm 

def _create_export_json(name, clusters, face_id_to_info):
    PATH = name + "-export.txt"   
    final_arr = defaultdict(list)
    imgs = defaultdict(list)   
    final_arr["name"] = [name];
    for i in list(clusters.keys()): #'arr': export_face_img(Face.objects.get(id=x['id'])),
        final_arr[i] = [{'face_id': x['id'], 
                         'video_id': x['frame__video__id'],
                         'show_name': x['frame__video__show__canonical_show__name'], 
                         'channel': face_id_to_info[x['id']]['channel']} for x in Face.objects.filter(id__in=clusters[i]).values('id', 'frame__video__id','frame__video__show__canonical_show__name')]
        if len(final_arr[i]) < 6:
            del final_arr[i]
            continue
        name_arr = name.split(" ")
        file_name = name_arr[0].lower() + "-" + name_arr[len(name_arr)-1].lower() + "/" + i
        PATH_IMG =  "/app/data/tv-news-images/" + file_name + ".jpg"
        listofimages = []
#         if len(Face.objects.get(id=final_arr[i])) >= 6:
        for b in range(0,6):
            fin_img = export_face_img(Face.objects.get(id=final_arr[i][b]['face_id']))
            listofimages.append(fin_img)
        width, height = listofimages[0].size
        coll_img = create_collage(width,height, listofimages)
        coll_img.save(PATH_IMG)
    with open(PATH, 'w') as outfile:
        final = json.dump(final_arr, outfile)
    return final

def _create_export_html(name, clusters, face_id_to_info):
    with open('test1.html', 'w') as f:
        sample_str = "Name: " + name
        f.write(sample_str)
        f.close()
    webbrowser.open_new_tab('test1.html')
    PATH = name + "-export.txt"   
    final_arr = defaultdict(list)
    imgs = defaultdict(list)   
    final_arr["name"] = [name];
    for i in list(clusters.keys()): #'arr': export_face_img(Face.objects.get(id=x['id'])),
        final_arr[i] = [{'face_id': x['id'], 
                         'video_id': x['frame__video__id'],
                         'show_name': x['frame__video__show__canonical_show__name'], 
                         'channel': face_id_to_info[x['id']]['channel']} for x in Face.objects.filter(id__in=clusters[i]).values('id', 'frame__video__id','frame__video__show__canonical_show__name')]
        if len(final_arr[i]) < 6:
            del final_arr[i]
            continue
        name_arr = name.split(" ")
        file_name = name_arr[0].lower() + "-" + name_arr[len(name_arr)-1].lower() + "/" + i
        PATH_IMG =  "/app/data/tv-news-images/" + file_name + ".jpg"
        listofimages = []
#         if len(Face.objects.get(id=final_arr[i])) >= 6:
        for b in range(0,6):
            fin_img = export_face_img(Face.objects.get(id=final_arr[i][b]['face_id']))
            listofimages.append(fin_img)
        width, height = listofimages[0].size
        coll_img = create_collage(width,height, listofimages)
        coll_img.save(PATH_IMG)
    with open(PATH, 'w') as outfile:
        final = json.dump(final_arr, outfile)
    return final




def create_collage(width, height, listofimages):
    cols = 3 #len(listofimages)
    rows = 2
    thumbnail_width = width//cols
    thumbnail_height = height//rows
    size = thumbnail_width, thumbnail_height
    new_im = PIL.Image.new('RGB', (width, height))
#     new_im = cv2.cvtColor(first_im, cv2.COLOR_BGR2RGB)
    ims = []
    for p in listofimages:
        p.thumbnail(size)
        ims.append(p)
    i = 0
    x = 0
    y = 0
    for col in range(cols):
        for row in range(rows):
#             print(i)
            new_im.paste(ims[i], (x, y))
            i += 1
            y += thumbnail_height
        x += thumbnail_width
        y = 0
    return new_im
    
def _manual_recluster(name, intermediate_clusters, date, final_clusters={}, examples_per_cluster=10, merge_cluster_threshold=0.1):
    clusters = intermediate_clusters[0]
    selected_clusters = []
    selected_images = []
    def _get_random_image(face_ids): #new cluster_images
        im = faces_to_tiled_img(
            Face.objects.filter(id__in=face_ids).order_by('?')[:1],
            False,
            cols=1
        )
        return im 
    def _get_cluster_images_fxn(clusters, n):
        cluster_images = {} #defining the cluster_images dict
        for cluster_id, face_ids in clusters.items():
            cluster_images[cluster_id] = {}
            for i in range(0, n):
                im = faces_to_tiled_img(
                    Face.objects.filter(id__in=face_ids).order_by('?')[:1],
                    False,
                    cols=1)
                cluster_images[cluster_id][i] = im
        return cluster_images

    #Beginning of universal lists you want to keep track of and update
    final_clusters = {} #for final selected image clusters
    all_images = _get_cluster_images_fxn(clusters,examples_per_cluster) #for all images
    final_clusters = all_images
    def _get_remaining_clusters():
        key = list(all_images.keys())
        discard_cluster_set = set()
        return set(key) - set(selected_clusters)
    def _replace_images():
        #finish writing function
        key = list(all_images.keys())
    remaining_clusters = _get_remaining_clusters()
    
    def _update_clusters_dict(remaining_clusters):
        for i in set(list(all_images.keys())):
            if i not in remaining_clusters:
                del all_images[i]
                del clusters[i]
        
    def get_img_checkbox():
        img_checkbox = widgets.ToggleButton(
            layout=widgets.Layout(width='auto'),
            value=False,
            description='Select',
            disabled=False,
            button_style='',
            icon=''
        )
        def on_toggle(b):
            if img_checkbox.value:
                descr_elts = img_checkbox.description.split()
                if len(descr_elts) == 2:
                    selected_clusters.append(int(descr_elts[1]))
                else:
                    selected_images.append((int(descr_elts[1]),int(descr_elts[3])))
                img_checkbox.button_style = 'danger'
                img_checkbox.icon = 'check'
#                 faces_to_tiled_img(cluster_images[int(descr_elts[1])][int(descr_elts[3])], False, cols=12)
#                 im = faces_to_tiled_img(
#                     Face.objects.filter(id__in=int(descr_elts[1])).order_by('?')[:1],
#                     False,
#                     cols=1)
            else:
                descr_elts = img_checkbox.description.split()
                if len(descr_elts) == 2:
                    selected_clusters.remove(int(descr_elts[1]))
                else:
                    selected_images.remove((int(descr_elts[1]),int(descr_elts[3])))
                img_checkbox.button_style = ''
                img_checkbox.icon = ''
#                 im = faces_to_tiled_img(
#                     Face.objects.filter(id__in=int(descr_elts[1])).order_by('?')[:1],
#                     False,
#                     cols=1)
        img_checkbox.observe(on_toggle, names='value')
        return img_checkbox
    
    #2: Be able to delete entire cluster: TODO
        #Notes: to delete cluster:
          #Ideal: a blank panel at beginning of cluster to select the whole row and then a delete button to delete
          #First Working version goal: select every picture in the whole row and then a delete button to delete
    def get_delete_button():
        del_button = widgets.Button(
            style=WIDGET_STYLE_ARGS,
            description='Delete Cluster(s)',
            disabled=False,
            button_style='warning', # 'success', 'info', 'warning', 'danger' or ''
        )
        def on_del(b): 
            if selected_clusters != []:
                remaining_clusters = _get_remaining_clusters()
                _update_clusters_dict(remaining_clusters)
                _clear_selected_clusters()
                clear_output()
                _selection_buttons(False)
                _display_clusters(remaining_clusters, examples_per_cluster)
        del_button.on_click(on_del)
        return del_button
    
    def get_replace_button():
        rep_button = widgets.Button(
            style=WIDGET_STYLE_ARGS,
            description='Replace selection(s)',
            disabled=False,
            button_style='warning', # 'success', 'info', 'warning', 'danger' or ''
        )
        def on_replace(b):
            if selected_images != []:
                for tup in selected_images:
                    im = _get_random_image(clusters[tup[0]])
                    all_images[tup[0]][tup[1]] = im
                    #2: Replace the picture with new image
                clear_output()
                _selection_buttons(False)
                _display_clusters(clusters, examples_per_cluster)  
        rep_button.on_click(on_replace)
        return rep_button
    
    #3: Be able to merge 2+ clusters: TODO
        #Notes: to merge clusters:
            #a blank panel at beginning of cluster to select the whole row and then a merge button to combine
    def _clear_selected_clusters():
        selected_clusters[:] = []
    def get_merge_button(): 
        mer_button = widgets.Button(
            style=WIDGET_STYLE_ARGS,
            description='Merge Cluster(s)',
            disabled=False,
            button_style='warning', # 'success', 'info', 'warning', 'danger' or ''
        )
        def on_merge(b):
            for i in range(1, len(selected_clusters)):
                all_images[selected_clusters[0]].update(all_images[selected_clusters[i]])
                clusters[selected_clusters[0]]+=clusters[selected_clusters[i]]
                del all_images[selected_clusters[i]]
                del clusters[selected_clusters[i]]
            _clear_selected_clusters()
            clear_output()
            _selection_buttons(False)
            _display_clusters(all_images, examples_per_cluster)
        mer_button.on_click(on_merge)
        return mer_button
    
    def get_refresh_button():
        ref_button = widgets.ToggleButton(
            layout=widgets.Layout(width='auto'),
            style=WIDGET_STYLE_ARGS,
            description='Refresh selections',
            disabled=False,
            button_style='warning'
        )
        def on_refresh(b):
            _clear_selected_clusters()
            clear_output()
            _selection_buttons(False)
            _display_clusters(clusters, examples_per_cluster)  
        ref_button.observe(on_refresh)
        return ref_button
     
    def get_submit_button():
        sub_button = widgets.Button(
            layout=widgets.Layout(width='='),
            style={'description_width': 'initial'},
            description='Submit selections',
            disabled=False,
            button_style='success'
        )
        def on_sub(b):
            _get_json_info(name, clusters)
            clear_output()
            visualization_workflow(clusters,date,intermediate_clusters[1],intermediate_clusters[2],intermediate_clusters[3])
        sub_button.on_click(on_sub)
        return sub_button
    
    def img_to_widget(img):
        height, width, _ = img.shape
        f = io.BytesIO()
        PIL.Image.fromarray(img).save(f, 'jpeg')
        return widgets.Image(value=f.getvalue(), height=100,
                             width=100)
    
    #1: Display n clusters in a row of ~10 images
        #Notes: images should have:
                #-> a check box underneath
                #-> a nice format 
    #Possible updates: reinstate the loop until d is selected feature
    #Deal with edge cases

    def _selection_buttons(inactive):
        if inactive:
            delete_button.disabled = True
            merge_button.disabled = True
            replace_button.disabled = True
            refresh_button.disabled = True
        display(widgets.HBox([widgets.Label('Selections:'), 
                delete_button, merge_button,refresh_button,submit_button])) #refresh_button
    
    def _display_clusters(cluster_ids, n): #TODO: need to consolidate the arrays
        for cluster_id in cluster_ids:
            display_array = []
            img_checkbox = get_img_checkbox()    
            img_checkbox.description = 'Cluster {}'.format(cluster_id) 
            display(img_checkbox)
            for i in range(0,n): #FIX INDEXING 
                individual_img_checkbox = get_img_checkbox()    
                individual_img_checkbox.description = 'C {} P {}'.format(cluster_id, i)   
                img_widget = img_to_widget(cv2.cvtColor(all_images[cluster_id][i], cv2.COLOR_BGR2RGB))
                display_array.append(widgets.VBox([img_widget, individual_img_checkbox]))
            display(widgets.HBox(display_array[0:11]))

#     Setup:
#     0: Image to widget helper function
    delete_button = get_delete_button()
    merge_button = get_merge_button()
    replace_button = get_replace_button()
    refresh_button = get_refresh_button()
    submit_button = get_submit_button()
    _selection_buttons(False)
    _display_clusters(all_images, examples_per_cluster)  

def _get_json_info(name, clusters):
    final = ""
    PATH = name + ".txt"
    with open(PATH, 'w') as outfile:
        final = json.dump(clusters, outfile)
    return final
    
def visualization_workflow(clusters, date, face_id_to_info,channels,name, examples_per_cluster=10,face_probability_threshold=0.5,
                          merge_cluster_threshold=0.2,init_clusters=10,exclude_commercials=False,duration_label_unit='m',
                          show_titles=True,save_paths=None,):
    #Everything below here is fine-make sure to considering the outlying false positives
    def convert_date():
        date_arr = date.split()
        return int(date_arr[len(date_arr)-1])

    def _sort_clusters_by_screentime(clusters):
        return {
            i : v for i, v in enumerate(sorted(
                clusters.values(),
                key=lambda l: sum(face_id_to_info[x]['screentime'] for x in l)
            ))
        }
    clusters = _sort_clusters_by_screentime(clusters)

    cluster_images = _get_cluster_images(clusters, True, n=10, c=10)
    def _truncate_to_date(dt):
        return datetime(year=dt.year, month=dt.month, day=dt.day)
    #Visualize the clusters
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
        face_arr = {} #TODO: name better
        channels_to_date_to_screentime = defaultdict(lambda: defaultdict(float))
        for face_id in clusters[cluster_id]:
            face_info = face_id_to_info[face_id]
            face_year = face_info['time'].year
            if (face_year not in face_arr.keys()):
                face_arr[face_year] = {'Total':1}
            else:
                face_arr[face_year]['Total'] +=1
            channels_to_date_to_screentime[face_info['channel']
                                          ][_truncate_to_date(face_info['time'])] += face_info['screentime'] / 60
        #sketch of max alg
        max_year = list(face_arr)[0]
        for yr in face_arr.keys():
            if face_arr[max_year]['Total'] < face_arr[yr]['Total']:
                max_year = yr
        min_time = datetime(year=max_year, month=1, day=1)  
        #sketch of min alg
        min_year = max_year
        for yr in face_arr.keys():
            if yr > max_year and face_arr[min_year]['Total'] >= face_arr[yr]['Total']:
                min_year = yr
        max_time = datetime(year=min_year, month=12, day=1)  
        if min_time.year > convert_date():
            continue
        else:
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
    
    cluster_images = _get_cluster_images(clusters, False, n=10, c=10)
    plot_heatmap_with_images(
        raw_heatmap, channels, cluster_images,
        'Images of {} and Their Corresponding Screen Time As Distributed within a Channel'.format(name) if show_titles else '',
        heatmap_label_fn=heatmap_raw_label_fn,
        save_path=save_paths[0] if save_paths else None
    )
    plot_heatmap_with_images(
        raw_heatmap / raw_heatmap.sum(axis=0)[np.newaxis, :],
        channels, cluster_images,
        'Images of {} and Screen Time Distributed Within a Channel (Column Normalized)'.format(name) if show_titles else '',
        save_path=save_paths[2] if save_paths else None
    )
    plot_heatmap_with_images(
        raw_heatmap / raw_heatmap.sum(axis=1)[:, np.newaxis],
        channels, cluster_images,
        'Images of {} and Screen Time As Distributed Across Channels (Row Normalized)'.format(name) if show_titles else '',
        save_path=save_paths[1] if save_paths else None
    )
    
    raw_bar_chart = defaultdict(lambda: {}) # {CNN: [{Anderson Cooper: 360 mins}, ...], MSNBC:[{...},...,{...}]}
    cnndict = defaultdict(lambda: 0)
    msnbcdict = defaultdict(lambda: 0)
    foxdict = defaultdict(lambda: 0)
    for cluster_id in sorted(clusters):
        face_ids = clusters[cluster_id]
        show_name = Face.objects.filter(id__in=face_ids).values("id", "frame__video__show__canonical_show__name")
        for face_id_obj in show_name:
            show = face_id_obj["frame__video__show__canonical_show__name"]
            if face_id_to_info[face_id_obj["id"]]['channel'] == 'CNN':
                cnndict[show] += 1
            elif face_id_to_info[face_id_obj["id"]]['channel'] == 'MSNBC':
                msnbcdict[show] += 1
            else:
                foxdict[show] += 1
    raw_bar_chart['CNN']=cnndict
    raw_bar_chart['MSNBC']=msnbcdict
    raw_bar_chart['FOXNEWS']=foxdict
    plot_stacked_bar_chart(raw_bar_chart['CNN'], 'CNN')
    plot_stacked_bar_chart(raw_bar_chart['MSNBC'], 'MSNBC')
    plot_stacked_bar_chart(raw_bar_chart['FOXNEWS'], 'FOXNEWS')
    