from scannertools import kube
from esper.scannerutil import ScannerWrapper
import os
import shlex
from contextlib import contextmanager

image_path = 'gcr.io/{project}/esper-base:{device}'.format(
    project=os.environ['GOOGLE_PROJECT'],
    device='cpu')

cloud_config = kube.CloudConfig(project=os.environ['GOOGLE_PROJECT'])

master_config = kube.MachineConfig(
    image=image_path,
    type=kube.MachineTypeName(name='n1-highmem-32'),
    disk=100)

def worker_config(machine_type):
    return kube.MachineConfig(
        image=image_path,
        type=kube.MachineTypeName(name=machine_type),
        disk=100,
        preemptible=True)

def cluster_config(**kwargs):
    return kube.ClusterConfig(
        id='wc-test',
        autoscale=True,
        master=master_config,
        **kwargs)

def cluster(cluster_config, sql_pool=None, **kwargs):
    containers = []
    if sql_pool is not None:
        proxy_port = 5431
        containers.append({
            'name': 'dbpool',
            'image': 'edoburu/pgbouncer',
            'env': [
                {'name': 'DATABASE_URL', 'value': 'postgres://{}:{}@0.0.0.0:5431/esper'.format(
                    os.environ['DJANGO_DB_USER'], os.environ['DJANGO_DB_PASSWORD']
                )},
                {'name': 'DEFAULT_POOL_SIZE', 'value': str(sql_pool)},
                {'name': 'MAX_CLIENT_CONN', 'value': '1000'},  # Allow any num. of client connections
                {'name': 'QUERY_WAIT_TIMEOUT', 'value': '0'},  # Don't timeout long queries
            ]
        })
    else:
        proxy_port = 5432

    containers.append({
        'name': 'db',
        'image': 'gcr.io/cloudsql-docker/gce-proxy:1.09',
        'command': shlex.split(
            '/cloud_sql_proxy -instances={}:us-east1-d:esper-dev=tcp:0.0.0.0:{} -credential_file=/config/service-key.json' \
            .format(os.environ['GOOGLE_PROJECT'], proxy_port)),
        'volumeMounts': [{
            'name': 'service-key',
            'mountPath': '/config'
        }]
    })

    return kube.Cluster(cloud_config, cluster_config, containers=containers, **kwargs)

@contextmanager
def make_cluster(*args, **kwargs):
    with cluster(*args, **kwargs) as c:
        yield ScannerWrapper.create(cluster=c, enable_watchdog=False)

if __name__ == '__main__':
    cluster(cluster_config(num_workers=1, worker=worker_config('n1-standard-16'))).cli()
