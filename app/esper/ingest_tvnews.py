import subprocess as sp

with open('/app/all-videos.txt', 'r') as f:
    all_videos = [s.strip() for s in f.readlines()]

downloaded = [s.strip().split('/')[-1][:-4] for s in sp.check_output('gsutil ls "gs://esper/tvnews/videos/*.mp4"', shell=True).decode('utf-8').splitlines()]

remaining = set(all_videos) - set(downloaded)

with open('/app/remaining-videos.txt', 'w') as f:
    f.write('\n'.join(list(remaining)))
