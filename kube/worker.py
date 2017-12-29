from scannerpy import start_worker
import os

start_worker(
    '{}:{}'.format(os.environ['SCANNER_MASTER_SERVICE_HOST'],
                   os.environ['SCANNER_MASTER_SERVICE_PORT']),
    block=True,
    watchdog=False)
