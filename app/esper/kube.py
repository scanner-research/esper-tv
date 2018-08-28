from scannertools import kube
import os

image_path = 'gcr.io/{project}/esper-base:{device}'.format(
    project=os.environ['GOOGLE_PROJECT'],
    device='cpu')

cloud_config = kube.CloudConfig(project=os.environ['GOOGLE_PROJECT'])

master_config = kube.MachineConfig(
    image=image_path,
    type=kube.MachineTypeName(name='n1-standard-32'),
    disk=100)

worker_config = kube.MachineConfig(
    image=image_path,
    type=kube.MachineTypeName(name='n1-highmem-96'),
    disk=100,
    preemptible=True)

cluster_config = kube.ClusterConfig(
    id='wc-test1',
    num_workers=3,
    autoscale=True,
    master=master_config,
    worker=worker_config)

cluster = kube.Cluster(cloud_config, cluster_config)

if __name__ == '__main__':
    cluster.cli()
