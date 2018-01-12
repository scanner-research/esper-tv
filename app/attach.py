from query.datasets.prelude import *

with make_scanner_db(kube=True) as db:
    db.wait_on_current_job()
