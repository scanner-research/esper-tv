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
import math

PROJECT_ID = os.environ['GOOGLE_PROJECT']
#ZONE = os.environ['GOOGLE_ZONE']
ZONE = 'us-east1-d'
SERVICE_KEY = os.environ['GOOGLE_APPLICATION_CREDENTIALS']
CLUSTER_ID = 'wc-test-2'
KUBE_VERSION = '1.8.5-gke.0'
USE_GPU = False
USE_PREEMPTIBLE = True
USE_AUTOSCALING = True
MASTER_CPU = 4  # Cores
MASTER_MEM = 96  # GB
MASTER_DISK = 50  # GB
# WORKER_CPU = 4
# WORKER_MEM = 26
WORKER_GPU = 4
WORKER_CPU = int(4 * WORKER_GPU if USE_GPU else 64)
WORKER_MEM = int(WORKER_CPU * 4.0)
WORKER_DISK = 500
WORKERS_PER_NODE = 6
DEPS = ['rudecarnie']

assert (not USE_GPU or WORKERS_PER_NODE == 1)
assert (not USE_PREEMPTIBLE or (USE_PREEMPTIBLE and USE_AUTOSCALING))

CLUSTER_CMD = 'gcloud alpha container --project {} clusters --zone {}'.format(PROJECT_ID, ZONE)


# docker sends a sigterm to kill a container, this ensures Python dies when the
# signal is sent
def sigterm_handler(signum, frame):
    sys.exit(1)


def run(s):
    return sp.check_call(shlex.split(s))


def machine_type(cpu, mem):
    name = 'custom-{}-{}'.format(cpu, mem * 1024)
    if float(mem) / cpu > 6.5:
        name += '-ext'
    return name


def make_container(name):
    template = {
        'name': name,
        'image': 'gcr.io/{project}/scanner-{name}:{device}'.format(project=PROJECT_ID, name=name, device='gpu' if USE_GPU else 'cpu'),
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
             'value': '1'},
            {'name': 'WORKERS_PER_NODE',
             'value': str(WORKERS_PER_NODE)},
            {'name': 'DEPS',
             'value': ','.join(DEPS)},
            # HACK(wcrichto): GPU decode for interlaced videos is broken, so forcing CPU
            # decode instead for now.
            {'name': 'FORCE_CPU_DECODE',
             'value': '1'}
        ],
        'resources': {},
        'securityContext': {'capabilities': {
            'add': ['SYS_PTRACE']  # Allows gdb to work in container
        }}
    }  # yapf: disable
    if name == 'master':
        template['ports'] = [{
            'containerPort': 8080,
        }]

    if name == 'loader':
        template['resources']['requests'] = {'cpu': WORKER_CPU / 2.0 + 0.1}
    else:
        if USE_GPU:
            template['resources']['limits'] = {'nvidia.com/gpu': WORKER_GPU}
        else:
            if name == 'worker':
                template['resources']['requests'] = {'cpu': WORKER_CPU / 2.0 + 0.1}

    return template


def make_deployment(name, replicas):
    template = {
        'apiVersion': 'apps/v1beta1',
        'kind': 'Deployment',
        'metadata': {'name': 'scanner-{}'.format(name)},
        'spec': {  # DeploymentSpec
            'replicas': replicas,
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


def get_kube_info(kind, namespace='default'):
    return json.loads(
        sp.check_output(shlex.split('kubectl get {} -o json -n {}'.format(kind, namespace))))


def get_object(info, name):
    for item in info['items']:
        if item['metadata']['name'] == name:
            return item
    return None


def create(args):
    # TODO(wcrichto): memoize all operations under this if guard
    if not cluster_running() or args.force:
        print('Creating cluster...')
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
            'cmd': CLUSTER_CMD,
            'cluster_id': CLUSTER_ID,
            'cluster_version': KUBE_VERSION,
            'master_machine': machine_type(MASTER_CPU, MASTER_MEM),
            'master_disk': MASTER_DISK,
            'worker_machine': machine_type(WORKER_CPU, WORKER_MEM),
            'worker_disk': WORKER_DISK,
            'scopes': ','.join(scopes),
            'initial_size': args.num_workers,
            'accelerator': '--accelerator type=nvidia-tesla-p100,count={}'.format(WORKER_GPU) if USE_GPU else '',
            'preemptible': '--preemptible' if USE_PREEMPTIBLE else '',
            'autoscaling': '--enable-autoscaling --min-nodes 0 --max-nodes {}'.format(args.num_workers) if USE_AUTOSCALING else ''
        }  # yapf: disable

        cluster_cmd = """
{cmd} -q create "{cluster_id}" \
        --enable-kubernetes-alpha \
        --cluster-version "{cluster_version}" \
        --machine-type "{master_machine}" \
        --image-type "COS" \
        --disk-size "{master_disk}" \
        --scopes {scopes} \
        --num-nodes "1" \
        --enable-cloud-logging \
        {accelerator}
        """.format(**fmt_args)

        run(cluster_cmd)

        fmt_args['cmd'] = fmt_args['cmd'].replace('clusters', 'node-pools')
        pool_cmd = """
{cmd} -q create workers \
        --cluster "{cluster_id}" \
        --machine-type "{worker_machine}" \
        --image-type "COS" \
        --disk-size "{worker_disk}" \
        --scopes {scopes} \
        --num-nodes "{initial_size}" \
        {autoscaling} \
        {preemptible} \
        {accelerator}
        """.format(**fmt_args)

        run(pool_cmd)

        # Wait for cluster to enter reconciliation if it's going to occur
        if args.num_workers > 1:
            time.sleep(60)

        # If we requested workers up front, we have to wait for the cluster to reconcile while they are
        # being allocated
        while True:
            cluster_status = sp.check_output(
                '{cmd} list --format=json | jq -r \'.[] | select(.name == "{id}") | .status\''.
                format(cmd=CLUSTER_CMD, id=CLUSTER_ID),
                shell=True).strip()

            if cluster_status == 'RECONCILING':
                time.sleep(5)
            else:
                if cluster_status != 'RUNNING':
                    raise Exception(
                        'Expected cluster status RUNNING, got: {}'.format(cluster_status))
                break

        # Install dashboard addons cpu/memory count
        dashboard_pod = get_pod('kubernetes-dashboard', namespace='kube-system')
        sp.check_call(
            'kubectl create -f https://raw.githubusercontent.com/kubernetes/heapster/master/deploy/kube-config/influxdb/influxdb.yaml && \
            kubectl create -f https://raw.githubusercontent.com/kubernetes/heapster/master/deploy/kube-config/influxdb/grafana.yaml && \
            (kubectl get pod {} -n kube-system -o yaml | kubectl replace --force -f -)'.format(
                dashboard_pod['metadata']['name']),
            shell=True)

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
                --clusterrole=cluster-admin --serviceaccount=kube-system:kubernetes-dashboard'
                .format(password)))

        if USE_GPU:
            # Install GPU drivers
            sp.check_call(
                shlex.split(
                    'kubectl create -f https://raw.githubusercontent.com/GoogleCloudPlatform/container-engine-accelerators/k8s-1.8/device-plugin-daemonset.yaml'
                ))

        serve(args)

    print('Cluster created. Setting up kubernetes...')
    get_credentials(args)

    deploy = get_object(get_kube_info('deployments'), 'scanner-worker')
    if deploy is not None and args.num_workers == 1:
        num_workers = deploy['status']['replicas']
    else:
        num_workers = args.num_workers

    if args.reset:
        run('kubectl delete service --all')
        run('kubectl delete deploy --all')

    secrets = get_kube_info('secrets')
    print('Making secrets...')
    if get_object(secrets, 'service-key') is None:
        run('kubectl create secret generic service-key --from-file={}'.format(SERVICE_KEY))

    if get_object(secrets, 'aws-storage-key') is None:
        run('kubectl create secret generic aws-storage-key --from-literal=AWS_ACCESS_KEY_ID={} --from-literal=AWS_SECRET_ACCESS_KEY={}'.
            format(os.environ['AWS_ACCESS_KEY_ID'], os.environ['AWS_SECRET_ACCESS_KEY']))

    deployments = get_kube_info('deployments')
    print('Creating deployments...')
    if get_object(deployments, 'scanner-master') is None:
        create_object(make_deployment('master', 1))

    services = get_kube_info('services')
    if get_object(services, 'scanner-master') is None:
        run('kubectl expose deploy/scanner-master --type=NodePort --port=8080')

    if get_object(deployments, 'scanner-worker') is None:
        create_object(make_deployment('worker', num_workers))

    print('Done!')


def get_pod(deployment, namespace='default'):
    while True:
        rs = get_by_owner('rs', deployment, namespace)
        pod_name = get_by_owner('pod', rs, namespace)
        if "\n" not in pod_name and pod_name != "":
            break
        time.sleep(1)

    while True:
        pod = get_object(get_kube_info('pod', namespace), pod_name)
        if pod is not None:
            return pod
        time.sleep(1)


def get_by_owner(ty, owner, namespace='default'):
    return sp.check_output(
        'kubectl get {} -o json -n {} | jq \'.items[] | select(.metadata.ownerReferences[0].name == "{}") | .metadata.name\''.
        format(ty, namespace, owner),
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
            print('Forwarding ' + pod_name)
            proxy_process = sp.Popen(
                shlex.split('kubectl proxy --address=0.0.0.0 --disable-filter=true'))
            break

    def cleanup_processes(signum, frame):
        proxy_process.terminate()
        proxy_process.wait()
        exit()

    signal.signal(signal.SIGINT, cleanup_processes)
    signal.signal(signal.SIGTERM, cleanup_processes)
    signal.pause()


def resize(args):
    if not USE_AUTOSCALING:
        run('{cmd} resize {id} --node-pool=workers --size={size}'.format(
            cmd=CLUSTER_CMD, id=CLUSTER_ID, size=args.size))
    else:
        run('{cmd} update {id} --node-pool=workers --enable-autoscaling --max-nodes={size}'.format(
            cmd=CLUSTER_CMD, id=CLUSTER_ID, size=args.size))

    run('kubectl scale deploy/scanner-worker --replicas={}'.format(args.size))


LOAD_BATCH = 1000


def load(args):
    with open('/app/tables') as f:
        num_tables = len(f.readlines())

    num_workers = int(math.ceil(num_tables / float(LOAD_BATCH)))

    for i in range(num_workers):
        container = make_container('loader')
        container['env'].extend([
            {
                'name': 'WORKER_ID',
                'value': str(i)
            },
            {
                'name': 'BATCH_SIZE',
                'value': str(LOAD_BATCH)
            },
        ])

        job = {
            'apiVersion': 'batch/v1',
            'kind': 'Job',
            'metadata': {'name': 'load-{}'.format(i)},
            'spec': {'template': {
                'metadata': {'name': 'load-{}'.format(i)},
                'spec': {
                    'containers': [container],
                    'restartPolicy': 'Never',
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
                        'cloud.google.com/gke-nodepool': 'workers'
                    }
                }
            }}
        }  # yapf: disable

        create_object(job)


def main():
    signal.signal(signal.SIGTERM, sigterm_handler)

    parser = argparse.ArgumentParser()
    command = parser.add_subparsers(dest='command')
    create = command.add_parser('create')
    create.add_argument('--reset', '-r', action='store_true', help='Delete current deployments')
    create.add_argument(
        '--num-workers', '-n', type=int, default=1, help='Initial number of workers')
    create.add_argument('--force', '-f', action='store_true', help='Force re-creation of cluster')
    command.add_parser('delete')
    command.add_parser('get-credentials')
    command.add_parser('serve')
    resize = command.add_parser('resize')
    resize.add_argument('size', type=int, help='Number of nodes')
    command.add_parser('load')

    args = parser.parse_args()
    globals()[args.command.replace('-', '_')](args)


if __name__ == "__main__":
    main()
