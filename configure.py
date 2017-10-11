import argparse
import yaml
import toml
import subprocess as sp
import shlex
from dotmap import DotMap

NAME = None
NGINX_PORT = '80'
SUFFIX = '-{}'.format(NAME) if NAME is not None else ''


def svc(s):
    return '{}{}'.format(s, SUFFIX)


config = yaml.load("""
version: '2'
services:
  nginx{suffix}:
    image: nginx
    command: ["bash", "/tmp/subst.sh"]
    volumes:
      - ./esper:/usr/src/app
      - ./nginx:/tmp
    depends_on: [esper{suffix}]
    ports: ["{port}:{port}"]
    environment: ["PORT={port}"]

  esper{suffix}:
    build:
      context: ./esper
      args:
        https_proxy: "${{https_proxy}}"
    image: scannerresearch/esper
    privileged: true
    depends_on: [db{suffix}]
    volumes:
      - ./esper:/usr/src/app
      - ${{HOME}}/.bash_history:/root/.bash_history
      - ./visualdb-key.json:/usr/src/app/visualdb-key.json
      - /mnt/gcs:/usr/src/app/gcs
    ports: ["8000"]
""".format(port=NGINX_PORT, suffix=SUFFIX))

db_local = yaml.load("""
image: mysql
environment:
  - MYSQL_DATABASE=esper
  - MYSQL_ROOT_PASSWORD=${MYSQL_PASSWORD}
volumes: ["./mysql-db:/var/lib/mysql", "./mysql.cnf:/etc/mysql/mysql.cnf"]
ports: ["3306"]
""")

db_google = yaml.load("""
image: gcr.io/cloudsql-docker/gce-proxy:1.09
volumes: ["./visualdb-key.json:/config"]
environment: []
ports: ["5432"]
""")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', '-c')
    parser.add_argument('--dataset', default='tvnews')
    args = parser.parse_args()

    if args.config:
        # TODO(wcrichto): validate config file
        base_config = DotMap(toml.load(args.config))
    else:
        base_config = DotMap({
            'storage': {
                'type': 'local'
            },
            'database': {
                'type': 'local',
                'name': 'esper'
            }
        })

    if base_config.database.type == 'google':
        config['services'][svc('db')] = db_google
        config['services'][svc('db')]['command'] = \
            '/cloud_sql_proxy -instances={project}:{zone}:{name}=tcp:0.0.0.0:5432 -credential_file=/config'.format(
                project=base_config.google.project, zone=base_config.google.zone, name=base_config.database.name)
    else:
        config['services'][svc('db')] = db_local
    config['services'][svc('esper')]['environment'] = [
        'DJANGO_DB_USER={}'.format(base_config.database.user
                                   if 'user' in base_config.database else 'root'),
    ]
    if 'password' in base_config.database:
        config['services'][svc('esper')]['environment'].append(
            "DJANGO_DB_PASSWORD={}".format(base_config.database.password))

    scanner_config = {}
    if base_config.storage.type == 'google':
        scanner_config['storage'] = {
            'type': 'gcs',
            'bucket': base_config.storage.bucket,
            'db_path': '{}/scanner_db'.format(base_config.storage.path)
        }
        config['services'][svc('esper')]['environment'].extend([
            'AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}',
            'AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}',
        ])
    else:
        scanner_config['storage'] = {'type': 'posix', 'db_path': '/usr/src/app/scanner_db'}

    for service in config['services'].values():
        env_vars = [
            'ESPER_ENV={}'.format(base_config.storage.type), 'DATASET={}'.format(args.dataset),
            'DATA_PATH={}'.format(base_config.storage.path)
        ]

        if base_config.storage.type == 'google':
            env_vars.append('BUCKET={}'.format(base_config.storage.bucket))

        service['environment'].extend(env_vars)

    with open('esper/.scanner.toml', 'w') as f:
        f.write(toml.dumps(scanner_config))

    with open('docker-compose.yml', 'w') as f:
        f.write(yaml.dump(config))

    print 'Successfully configured Esper.'


if __name__ == '__main__':
    main()
