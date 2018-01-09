from scannerpy import Database
from concurrent.futures import ThreadPoolExecutor
import os
import pickle
from tqdm import tqdm

WORKER_ID = int(os.environ['WORKER_ID'])
BATCH_SIZE = int(os.environ['BATCH_SIZE'])

print('Connecting to database')
with Database() as db:
    print('Reading tables')
    with open('/app/tables') as f:
        tables = [s.strip()
                  for s in f.readlines()][(WORKER_ID * BATCH_SIZE):((WORKER_ID + 1) * BATCH_SIZE)]

    db._load_db_metadata()

    def load(t):
        return (t, list(db.table(t).column('histogram').load()))

    print('Loading {} tables'.format(len(tables)))
    with ThreadPoolExecutor(max_workers=8) as executor:
        loaded = list(tqdm(executor.map(load, tables), total=len(tables)))

    print('Writing out megafile')
    db._storage.write('tmp/hist_{}.pkl'.format(WORKER_ID),
                      pickle.dumps(loaded, pickle.HIGHEST_PROTOCOL))
