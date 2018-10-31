from scannertools import kube
import os
import shlex

image_path = 'gcr.io/{project}/esper-base:{device}'.format(
    project=os.environ['GOOGLE_PROJECT'],
    device='cpu')

cloud_config = kube.CloudConfig(project=os.environ['GOOGLE_PROJECT'])

master_config = kube.MachineConfig(
    image=image_path,
    type=kube.MachineTypeName(name='n1-highmem-32'),
    disk=100)

worker_config = kube.MachineConfig(
    image=image_path,
    type=kube.MachineTypeName(name='n1-highmem-16'),
    disk=100,
    preemptible=True)

cluster_config = kube.ClusterConfig(
    id='wc-test2',
    num_workers=10,
    autoscale=True,
    master=master_config,
    worker=worker_config,
    workers_per_node=4)

def make_cluster(**kwargs):
    return kube.Cluster(cloud_config, cluster_config, containers=[{
        'name': 'db',
        'image': 'gcr.io/cloudsql-docker/gce-proxy:1.09',
        'command': shlex.split(
            '/cloud_sql_proxy -instances={}:us-east1-d:esper-dev=tcp:0.0.0.0:5432 -credential_file=/config/service-key.json'.format(os.environ['GOOGLE_PROJECT'])),
        'volumeMounts': [{
            'name': 'service-key',
            'mountPath': '/config'
        }],
        'ports': [{'containerPort': 5432}]
    }], **kwargs)

if __name__ == '__main__':
    make_cluster().cli()
