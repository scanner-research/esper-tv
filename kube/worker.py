from scannerpy import start_worker, ScannerException
import os
import time

start_worker(
    '{}:{}'.format(os.environ['SCANNER_MASTER_SERVICE_HOST'],
                   os.environ['SCANNER_MASTER_SERVICE_PORT']),
    block=True,
    watchdog=False,
    prefetch_table_metadata=True)
