import argparse
import sys
import signal
import toml
import time
import subprocess as sp
import tempfile
import yaml
import os
import json
from pprint import pprint
import threading
import atexit
import multiprocessing as mp
import shlex
import signal

PROJECT_ID = os.environ['GOOGLE_PROJECT']
ZONE = os.environ['GOOGLE_ZONE']
SERVICE_KEY = os.environ['GOOGLE_APPLICATION_CREDENTIALS']
CLUSTER_ID = 'wc-test'
KUBE_VERSION = '1.8.4-gke.1'
USE_GPU = False
NUM_CPU = 2 if USE_GPU else 4
NUM_MEM = 16

CLUSTER_CMD = 'gcloud container clusters --zone {}'.format(ZONE)


# docker sends a sigterm to kill a container, this ensures Python dies when the
# signal is sent
def sigterm_handler(signum, frame):
    sys.exit(1)


def run(s):
    return sp.check_call(shlex.split(s))


def machine_type(cpu, mem):
    return 'custom-{}-{}'.format(cpu, mem * 1024)


def make_container(name):
    template = {
        'name': name,
        'image': 'gcr.io/{project}/scanner-{name}'.format(project=PROJECT_ID, name=name),
        'imagePullPolicy': 'Always',
        'volumeMounts': [{
            'name': 'service-key',
            'mountPath': '/secret'
        }],
        'env': [
            {'name': 'GOOGLE_APPLICATION_CREDENTIALS',
             'value': '/secret/service-key.json'},
            {'name': 'AWS_ACCESS_KEY_ID',
             'valueFrom': {'secretKeyRef': {
                 'name': 'aws-storage-key',
                 'key': 'AWS_ACCESS_KEY_ID'
             }}},
            {'name': 'AWS_SECRET_ACCESS_KEY',
             'valueFrom': {'secretKeyRef': {
                 'name': 'aws-storage-key',
                 'key': 'AWS_SECRET_ACCESS_KEY'
             }}},
            {'name': 'GLOG_minloglevel',
             'value': '0'},
            {'name': 'GLOG_logtostderr',
             'value': '1'},
            {'name': 'GLOG_v',
             'value': '1'}
        ],
        'resources': {
        }
    }  # yapf: disable
    if name == 'master':
        template['ports'] = [{
            'containerPort': 8080,
        }]
    elif name == 'worker':
        pod = get_master_pod()

        template['env'] += [{
            'name': 'SCANNER_MASTER_SERVICE_HOST',
            'value': pod['status']['podIP']
        }, {
            'name': 'SCANNER_MASTER_SERVICE_PORT',
            'value': '8080'
        }]

    if USE_GPU:
        limits = {
            'nvidia.com/gpu': 1
        }
    else:
        limits = {
            'cpu': 3
        }

    template['resources']['limits'] = limits

    return template


def make_deployment(name):
    template = {
        'apiVersion': 'apps/v1beta1',
        'kind': 'Deployment',
        'metadata': {'name': 'scanner-{}'.format(name)},
        'spec': {  # DeploymentSpec
            'replicas': 1,
            'template': {
                'metadata': {'labels': {'app': 'scanner-{}'.format(name)}},
                'spec': {  # PodSpec
                    'containers': [make_container(name)],
                    'volumes': [{
                        'name': 'service-key',
                        'secret': {
                            'secretName': 'service-key',
                            'items': [{
                                'key': 'service-key.json',
                                'path': 'service-key.json'
                            }]
                        }
                    }],
                    'nodeSelector': {
                        'cloud.google.com/gke-nodepool':
                        'default-pool' if name == 'master' else 'workers'
                    }
                }
            }
        }
    }  # yapf: disable

    return template


def create_object(template):
    with tempfile.NamedTemporaryFile() as f:
        f.write(yaml.dump(template))
        f.flush()

        sp.check_call(['kubectl', 'create', '-f', f.name])


def cluster_running():
    return sp.check_output(
        '{cmd} list --format=json | jq \'.[] | select(.name == "{id}")\''.format(
            cmd=CLUSTER_CMD, id=CLUSTER_ID),
        shell=True) != ''


def get_credentials(args):
    run('{cmd} get-credentials {id}'.format(cmd=CLUSTER_CMD, id=CLUSTER_ID))


def delete(args):
    run('{cmd} delete {id}'.format(cmd=CLUSTER_CMD, id=CLUSTER_ID))


def get_kube_info(kind):
    return json.loads(sp.check_output(shlex.split('kubectl get {} -o json'.format(kind))))


def get_object(info, name):
    for item in info['items']:
        if item['metadata']['name'] == name:
            return item
    return None


def create(args):
    if not cluster_running():
        print 'Creating cluster...'
        scopes = [
            "https://www.googleapis.com/auth/compute",
            "https://www.googleapis.com/auth/devstorage.read_write",
            "https://www.googleapis.com/auth/logging.write",
            "https://www.googleapis.com/auth/monitoring", "https://www.googleapis.com/auth/pubsub",
            "https://www.googleapis.com/auth/servicecontrol",
            "https://www.googleapis.com/auth/service.management.readonly",
            "https://www.googleapis.com/auth/trace.append"
        ]

        fmt_args = {
            'project': PROJECT_ID,
            'cluster_id': CLUSTER_ID,
            'zone': ZONE,
            'cluster_version': KUBE_VERSION,
            'machine_type': machine_type(NUM_CPU, NUM_MEM),
            'scopes': ','.join(scopes),
            'initial_size': 1,
            'accelerator': '--accelerator type=nvidia-tesla-k80,count=1' if USE_GPU else ''
        }

        cluster_cmd = """
gcloud alpha -q container --project "{project}" clusters create "{cluster_id}" \
        --enable-kubernetes-alpha \
        --zone "{zone}" \
        --cluster-version "{cluster_version}" \
        --machine-type "{machine_type}" \
        --image-type "COS" \
        --disk-size "30" \
        --scopes {scopes} \
        --num-nodes "1" \
        --enable-cloud-logging \
        {accelerator}
        """.format(**fmt_args)

        run(cluster_cmd)

        pool_cmd = """
gcloud alpha -q container node-pools create workers \
        --cluster "{cluster_id}" \
        --zone "{zone}" \
        --machine-type "{machine_type}" \
        --image-type "COS" \
        --disk-size "30" \
        --scopes {scopes} \
        --num-nodes "{initial_size}" \
        --enable-autoscaling \
        --min-nodes "0" \
        --max-nodes "1000" \
        --preemptible \
        {accelerator}
        """.format(**fmt_args)

        run(pool_cmd)

        # Authorize dashboard to access cluster info
        # https://github.com/kubernetes/helm/issues/2687
        # https://stackoverflow.com/questions/46307325/gke-clusterrolebinding-for-cluster-admin-fails-with-permission-error
        password = sp.check_output(
            '{cmd} describe {id} --format=json | jq ".masterAuth.password" -r'.format(
                cmd=CLUSTER_CMD, id=CLUSTER_ID),
            shell=True)
        sp.check_call(
            shlex.split(
                'kubectl --username=admin --password={} create clusterrolebinding add-on-cluster-admin \
                --clusterrole=cluster-admin --serviceaccount=kube-system:default'.format(password)))

        if USE_GPU:
            # Install GPU drivers
            sp.check_call(
                shlex.split(
                    'kubectl create -f https://raw.githubusercontent.com/GoogleCloudPlatform/container-engine-accelerators/k8s-1.8/device-plugin-daemonset.yaml'
                ))

    print 'Cluster created. Setting up kubernetes...'
    get_credentials(args)

    if args.reset:
        run('kubectl delete deploy --all')

    secrets = get_kube_info('secrets')
    print 'Making secrets...'
    if get_object(secrets, 'service-key') is None:
        run('kubectl create secret generic service-key --from-file={}'.format(SERVICE_KEY))

    if get_object(secrets, 'aws-storage-key') is None:
        run('kubectl create secret generic aws-storage-key --from-literal=AWS_ACCESS_KEY_ID={} --from-literal=AWS_SECRET_ACCESS_KEY={}'.
            format(os.environ['AWS_ACCESS_KEY_ID'], os.environ['AWS_SECRET_ACCESS_KEY']))

    deployments = get_kube_info('deployments')
    print 'Creating deployments...'
    if get_object(deployments, 'scanner-master') is None:
        create_object(make_deployment('master'))
        print 'Waiting for master to start...'
        while True:
            pod = get_master_pod()
            if pod['status']['phase'] == 'Running':
                break
        serve(args)

    if get_object(deployments, 'scanner-worker') is None:
        create_object(make_deployment('worker'))

    print 'Done!'


def get_master_pod():
    while True:
        rs = get_by_owner('rs', 'scanner-master')
        pod_name = get_by_owner('pod', rs)
        if "\n" not in pod_name and pod_name != "":
            break
        time.sleep(1)

    while True:
        pod = get_object(get_kube_info('pod'), pod_name)
        if pod is not None:
            return pod
        time.sleep(1)

def get_by_owner(ty, owner):
    return sp.check_output(
        'kubectl get {} -o json | jq \'.items[] | select(.metadata.ownerReferences[0].name == "{}") | .metadata.name\''.
        format(ty, owner),
        shell=True).strip()[1:-1]


PID_FILE = '/tmp/serving_process.pid'


def serve(args):
    if os.path.isfile(PID_FILE):
        try:
            sp.check_call(['kill', open(PID_FILE).read()])
        except sp.CalledProcessError:
            pass

    p = sp.Popen(shlex.split('python -c "import cluster; cluster.serve_process()"'))

    with open(PID_FILE, 'w') as f:
        f.write(str(p.pid))


def serve_process():
    if not cluster_running():
        return

    get_credentials(None)

    while True:
        rs = get_by_owner('rs', 'scanner-master')
        pod_name = get_by_owner('pod', rs)
        if "\n" not in pod_name and pod_name != '':
            print 'Forwarding ' + pod_name
            forward_process = sp.Popen(
                shlex.split('kubectl port-forward {} 8080:8080'.format(pod_name)))
            proxy_process = sp.Popen(
                shlex.split('kubectl proxy --address=0.0.0.0 --disable-filter=true'))
            break

    def cleanup_processes(signum, frame):
        proxy_process.terminate()
        forward_process.terminate()
        proxy_process.wait()
        forward_process.wait()
        exit()

    signal.signal(signal.SIGINT, cleanup_processes)
    signal.signal(signal.SIGTERM, cleanup_processes)
    signal.pause()


def resize(args):
    run('kubectl scale deploy/scanner-worker --replicas={}'.format(args.size))


def main():
    signal.signal(signal.SIGTERM, sigterm_handler)

    parser = argparse.ArgumentParser()
    command = parser.add_subparsers(dest='command')
    create = command.add_parser('create')
    create.add_argument('--reset', '-r', action='store_true', help='Delete current deployments')
    command.add_parser('delete')
    command.add_parser('get-credentials')
    command.add_parser('serve')
    resize = command.add_parser('resize')
    resize.add_argument('size', type=int, help='Number of nodes')

    args = parser.parse_args()
    globals()[args.command.replace('-', '_')](args)


if __name__ == "__main__":
    main()
