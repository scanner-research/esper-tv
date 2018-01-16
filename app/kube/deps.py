# This is separate from worker.py because apparently if we download code, we can't import it in the same session,
# even if it should already be on the PYTHONPATH. Maybe Python interpreter does some pre-eval checking of files on
# the path to optimize module lookups?
import subprocess as sp
import os
deps = os.environ['DEPS'].split(',')
if deps != ['']:
    sp.check_call(' && '.join(['./scripts/install-{}.sh'.format(dep) for dep in deps]), shell=True)
