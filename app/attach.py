from scannerpy import Database, DeviceType, BulkJob, Job

with Database(master='localhost:8080', start_cluster=False, prefetch_table_metadata=False) as db:
    db.wait_on_current_job()
