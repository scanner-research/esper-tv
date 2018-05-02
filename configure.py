import argparse
import yaml
import toml
import subprocess as sp
import shlex
from dotmap import DotMap
import multiprocessing
import shutil

NGINX_PORT = '80'
IPYTHON_PORT = '8888'

cores = multiprocessing.cpu_count()

extra_services = {
    'spark':
    DotMap(
        yaml.load("""
build:
  context: ./spark
ports: ['8080:8080', '8081:8081', '7077']
environment: []
depends_on: [db]
volumes:
  - ./app:/app
""")),
    'gentle':
    DotMap(
        yaml.load("""
image: lowerquality/gentle
environment: []
ports: ['8765']
command: bash -c "cd /gentle && python serve.py --ntranscriptionthreads 8"
"""))
}

extra_processes = {
    'subserver': 'bash -c "cd subserver && source /root/.cargo/env && cargo run --release"',
    'npm': 'npm run watch --color'
}

config = DotMap(
    yaml.load("""
version: '2.3'
services:
  nginx:
    build:
      context: ./nginx
    command: ["bash", "/tmp/subst.sh"]
    volumes:
      - ./app:/app
      - ./nginx:/tmp
    depends_on: [app, frameserver]
    ports: ["{nginx_port}:{nginx_port}"]
    environment: ["PORT={nginx_port}"]

  frameserver:
    image: scannerresearch/frameserver
    ports: ['7500:7500']
    environment:
      - 'WORKERS={workers}'

  app:
    build:
      context: ./app
      dockerfile: Dockerfile.app
      args:
        https_proxy: "${{https_proxy}}"
        cores: {cores}
    depends_on: [db, frameserver]
    volumes:
      - ./app:/app
      - ${{HOME}}/.esper/.bash_history:/root/.bash_history
      - ${{HOME}}/.esper/.cargo:/root/.cargo
      - ${{HOME}}/.esper/.rustup:/root/.rustup
      - ./service-key.json:/app/service-key.json
    ports: ["8000", "{ipython_port}:{ipython_port}"]
    environment: ["IPYTHON_PORT={ipython_port}", "JUPYTER_PASSWORD=esperjupyter"]
    tty: true # https://github.com/docker/compose/issues/2231#issuecomment-165137408
""".format(nginx_port=NGINX_PORT, ipython_port=IPYTHON_PORT, cores=cores, workers=cores * 2)))

db_local = DotMap(
    yaml.load("""
build:
    context: ./db
environment:
  - POSTGRES_USER=will
  - POSTGRES_PASSWORD=foobar
  - POSTGRES_DB=esper
volumes: ["./db/data:/var/lib/postgresql/data", "./app:/app"]
ports: ["5432"]
"""))

db_google = DotMap(
    yaml.load("""
image: gcr.io/cloudsql-docker/gce-proxy:1.09
volumes: ["./service-key.json:/config"]
environment: []
ports: ["5432"]
"""))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', '-c', required=True)
    parser.add_argument('--dataset', default='default')
    parser.add_argument('--extra-processes', nargs='*', default=[], choices=extra_processes.keys())
    parser.add_argument('--extra-services', nargs='*', default=[], choices=extra_services.keys())
    parser.add_argument(
        '--build', nargs='*', default=['base', 'local'], choices=['base', 'local', 'kube', 'tf'])
    parser.add_argument('--kube-device', default='cpu')
    args = parser.parse_args()

    # TODO(wcrichto): validate config file
    base_config = DotMap(toml.load(args.config))

    if 'google' in base_config:
        config.services.app.environment.extend([
            'GOOGLE_PROJECT={}'.format(base_config.google.project), 'GOOGLE_ZONE={}'.format(
                base_config.google.zone)
        ])
        config.services.app.ports.append('8001:8001')  # for kubectl proxy

    if 'compute' in base_config:
        if 'gpu' in base_config.compute:
            device = 'gpu' if base_config.compute.gpu else 'cpu'
        else:
            device = 'cpu'
    else:
        device = 'cpu'

    config.services.app.build.args.device = device
    if device == 'gpu':
        config.services.app.runtime = 'nvidia'

    config.services.app.environment.append('DEVICE={}'.format(device))
    config.services.app.image = 'scannerresearch/esper:{}'.format(device)

    for svc in args.extra_services:
        config.services[svc] = extra_services[svc]
        config.services.app.depends_on.append(svc)

    # Create supervisord.conf with any additoinal processes
    with open('app/.deps/supervisord.conf', 'r') as f:
        supervisor_conf = f.read()
    for process in args.extra_processes:
        supervisor_conf += """
\n[program:{}]
command={}
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0""".format(process, extra_processes[process])
    with open('app/supervisord.conf', 'w') as f:
        f.write(supervisor_conf)

    if base_config.database.type == 'google':
        assert 'google' in base_config
        config.services.db = db_google
        config.services.db['command'] = \
            '/cloud_sql_proxy -instances={project}:{zone}:{name}=tcp:0.0.0.0:5432 -credential_file=/config'.format(
                project=base_config.google.project, zone=base_config.google.zone, name=base_config.database.name)
    else:
        config.services.db = db_local

    config.services.app.environment.append('DJANGO_DB_USER={}'.format(
        base_config.database.user if 'user' in base_config.database else 'root'))

    if 'password' in base_config.database:
        config.services.app.environment.extend([
            'DJANGO_DB_PASSWORD={}'.format(base_config.database.password), 'PGPASSWORD={}'.format(
                base_config.database.password)
        ])

    scanner_config = {'scanner_path': '/opt/scanner'}
    if base_config.storage.type == 'google':
        assert 'google' in base_config
        scanner_config['storage'] = {
            'type': 'gcs',
            'bucket': base_config.storage.bucket,
            'db_path': '{}/scanner_db'.format(base_config.storage.path)
        }
    else:
        scanner_config['storage'] = {'type': 'posix', 'db_path': '/app/scanner_db'}

    config.services.frameserver.environment.append('FILESYSTEM={}'.format(base_config.storage.type))

    for service in list(config.services.values()):
        env_vars = [
            'ESPER_ENV={}'.format(base_config.storage.type), 'DATASET={}'.format(args.dataset),
            'DATA_PATH={}'.format(base_config.storage.path)
        ]

        if base_config.storage.type == 'google':
            env_vars.extend([
                'BUCKET={}'.format(base_config.storage.bucket),
                'AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}',
                'AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}',
            ])

        service.environment.extend(env_vars)

    with open('app/.scanner.toml', 'w') as f:
        f.write(toml.dumps(scanner_config))

    with open('docker-compose.yml', 'w') as f:
        f.write(yaml.dump(config.toDict()))

    if 'base' in args.build:
        devices = list(
            set(([device] if 'local' in args.build else []) +
                ([args.kube_device] if 'kube' in args.build else [])))

        for device in devices:
            build_args = {
                'cores': cores,
                'tag': 'cpu' if device == 'cpu' else 'gpu-9.1-cudnn7',
                'device': device,
                'tf_version': '1.5.0',
                'build_tf': 'on' if 'tf' in args.build else 'off'
            }

            sp.check_call(
                'docker build -t scannerresearch/esper-base:{device} {build_args} -f app/Dockerfile.base app'.
                format(
                    device=device,
                    build_args=' '.join(
                        ['--build-arg {}={}'.format(k, v) for k, v in build_args.items()])),
                shell=True)

    if 'kube' in args.build:
        if 'google' in base_config:
            base_url = 'gcr.io/{project}'.format(project=base_config.google.project)

            def build(tag):
                fmt_args = {'base_url': base_url, 'tag': tag, 'device': args.kube_device}
                sp.check_call(
                    'docker build -t {base_url}/scanner-{tag}:{device} --build-arg device={device} -f app/kube/Dockerfile.{tag} app'.
                    format(**fmt_args),
                    shell=True)
                sp.check_call(
                    'gcloud docker -- push {base_url}/scanner-{tag}:{device}'.format(**fmt_args),
                    shell=True)

            build('master')
            build('worker')
            # build('loader')

    print('Successfully configured Esper.')


if __name__ == '__main__':
    main()
