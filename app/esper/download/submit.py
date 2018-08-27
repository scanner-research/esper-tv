from tasks import download
from tqdm import tqdm

remaining = [s.strip() for s in open('remaining-videos.txt', 'r').readlines()]

for video in tqdm(remaining):
    download.delay(video)
