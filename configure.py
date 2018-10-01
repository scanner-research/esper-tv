import argparse
import yaml
import toml
import subprocess as sp
import shlex
from dotmap import DotMap
import multiprocessing
import shutil
import socket
import os

NGINX_PORT = '80'
IPYTHON_PORT = '8888'
TF_VERSION = '1.5.0'

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

tsize = shutil.get_terminal_size()
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
    ports: ["{nginx_port}:{nginx_port}", "{ipython_port}:{ipython_port}"]
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
        cores: {cores}
    depends_on: [db, frameserver, redis]
    volumes:
      - ./app:/app
      - ${{HOME}}/.esper/.bash_history:/root/.bash_history
      - ${{HOME}}/.esper/.cargo:/root/.cargo
      - ${{HOME}}/.esper/.rustup:/root/.rustup
      - ${{HOME}}/scannertools:/opt/scannertools
      - ${{HOME}}/vgrid:/opt/vgrid
      - ${{HOME}}/vgrid_jupyter:/opt/vgrid_jupyter
      - ./service-key.json:/app/service-key.json
    ports: ["8000", "{ipython_port}"]
    environment:
      - IPYTHON_PORT={ipython_port}
      - JUPYTER_PASSWORD=esperjupyter
      - COLUMNS={columns}
      - LINES={lines}
      - TERM={term}
      - RUST_BACKTRACE=full
    tty: true # https://github.com/docker/compose/issues/2231#issuecomment-165137408
    privileged: true # make perf work
    security_opt: # make gdb work
      - seccomp=unconfined

  redis:
    image: redis:4
    ports: ['6379:6379']
    environment: []
""".format(
        nginx_port=NGINX_PORT,
        ipython_port=IPYTHON_PORT,
        cores=cores,
        workers=cores * 2,
        columns=tsize.columns,
        lines=tsize.lines,
        term=os.environ.get('TERM'))))

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
    parser.add_argument('--extra-processes', nargs='*', default=[], choices=extra_processes.keys())
    parser.add_argument('--extra-services', nargs='*', default=[], choices=extra_services.keys())
    parser.add_argument('--no-build', action='store_true')
    parser.add_argument('--build-tf', action='store_true')
    parser.add_argument('--build-device', default='cpu')
    parser.add_argument('--base-only', action='store_true')
    parser.add_argument('--no-pull', action='store_true')
    parser.add_argument('--hostname')
    args = parser.parse_args()

    # TODO(wcrichto): validate config file
    base_config = DotMap(toml.load(args.config))

    # Google Cloud config
    if 'google' in base_config:
        if not os.path.isfile('service-key.json'):
            raise Exception("Missing required service key file service-key.json")

        config.services.app.environment.extend([
            'GOOGLE_PROJECT={}'.format(base_config.google.project), 'GOOGLE_ZONE={}'.format(
                base_config.google.zone)
        ])
        config.services.app.ports.append('8001:8001')  # for kubectl proxy

    # GPU settings
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

    # Additional Docker services
    for svc in args.extra_services:
        config.services[svc] = extra_services[svc]
        config.services.app.depends_on.append(svc)

    # Additional supervisord proceseses
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

    # SQL database
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

    # Scanner config
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

    # Frameserver
    config.services.frameserver.environment.append('FILESYSTEM={}'.format(base_config.storage.type))

    # Universal environment variables
    if args.hostname is not None:
        hostname = args.hostname
    else:
        is_google = b'Metadata-Flavor: Google' in sp.check_output(
            'curl metadata.google.internal -i -s', shell=True)
        if is_google:
            hostname = sp.check_output(
                """
            gcloud compute instances list --format=json | \
            jq ".[] | select(.name == \\"$(hostname)\\") | \
                .networkInterfaces[0].accessConfigs[] | \
                select(.name == \\"External NAT\\") | .natIP" -r
            """,
                shell=True).decode('utf-8').strip()
        else:
            hostname = socket.gethostbyname(socket.gethostname())

    for service in list(config.services.values()):
        env_vars = [
            'ESPER_ENV={}'.format(base_config.storage.type),
            'DATA_PATH={}'.format(base_config.storage.path), 'HOSTNAME={}'.format(hostname)
        ]

        if base_config.storage.type == 'google':
            env_vars.extend([
                'BUCKET={}'.format(base_config.storage.bucket),
                'AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}',
                'AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}',
            ])

        service.environment.extend(env_vars)

    # Write out generated configuration files
    with open('app/.scanner.toml', 'w') as f:
        f.write(toml.dumps(scanner_config))

    with open('docker-compose.yml', 'w') as f:
        f.write(yaml.dump(config.toDict()))

    # Build Docker images where necessary
    if not args.no_build:
        build_args = {
            'cores': cores,
            'tag': 'cpu' if args.build_device == 'cpu' else 'gpu-9.1-cudnn7',
            'device': args.build_device,
            'tf_version': TF_VERSION,
            'build_tf': 'on' if args.build_tf else 'off'
        }

        sp.check_call(
            'docker build {pull} -t esper-base:{device} {build_args} -f app/Dockerfile.base app'.
            format(
                device=args.build_device,
                pull='--pull' if not args.no_pull else '',
                build_args=' '.join(
                    ['--build-arg {}={}'.format(k, v) for k, v in build_args.items()])),
            shell=True)

        if 'google' in base_config:
            base_url = 'gcr.io/{project}'.format(project=base_config.google.project)
            sp.check_call(
                'docker tag esper-base:{device} {base_url}/esper-base:{device} && \
                gcloud docker -- push {base_url}/esper-base:{device}'.format(
                    device=args.build_device,
                    base_url=base_url),
                shell=True)

        if not args.base_only:
            sp.check_call('docker-compose build', shell=True)

    print('Successfully configured Esper. To start Esper, run:')
    print('$ docker-compose up -d')


if __name__ == '__main__':
    main()
