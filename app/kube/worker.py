from scannerpy import start_worker, ScannerException
import os

# TODO: vary num_workers w/ # of cores, don't fix 64

import scannerpy.libscanner as bindings
import scanner.metadata_pb2 as metadata_types
PROCESS_PER_CORE = os.environ['PROCESS_PER_CORE'] == 'True'
machine_params = metadata_types.MachineParameters()
machine_params.ParseFromString(bindings.default_machine_params())
if PROCESS_PER_CORE:
    machine_params.num_load_workers = 1
    machine_params.num_save_workers = 1

start_worker(
    '{}:{}'.format(os.environ['SCANNER_MASTER_SERVICE_HOST'],
                   os.environ['SCANNER_MASTER_SERVICE_PORT']),
    block=True,
    watchdog=False,
    prefetch_table_metadata=True,
    machine_params=machine_params.SerializeToString(),
    port=5002,
    num_workers=2 if PROCESS_PER_CORE else None)
