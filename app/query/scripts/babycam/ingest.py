from query.scripts.prelude import *
from query.scripts.ingest import ingest
import csv
from datetime import datetime

with open('spreadsheet.csv', 'rb') as f:
    reader = csv.reader(f)
    header = next(reader)
    rows = [{k: v for (k, v) in zip(header, l)} for l in reader]
    sessions = {r['session-id']: r for r in rows}

def ingestor(video, local_path):
    session_id = video.path.split('/')[-2].split('-')[0]
    s = sessions[session_id]
    video.session_id = int(s['session-id'])
    video.session_name = s['session-name']
    video.session_date = datetime.strptime(s['session-date'], '%Y-%m-%d')
    video.participant_id = int(s['participant-ID'])
    video.participant_birthdate = datetime.strptime(s['participant-birthdate'], '%Y-%m-%d')
    video.participant_gender = s['participant-gender']
    video.context_setting = s['context-setting']
    video.context_country = s['context-country']
    video.context_state = s['context-state']

ingest(['babycam/videos/9188-XS_0801/25294-XS_0801_objs.mov.mp4'], ingestor)
