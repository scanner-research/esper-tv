import argparse
import yaml
import toml
import subprocess as sp
import shlex

USER = 'pari'
PROJECT = 'visualdb-1046'
ZONE = 'us-central1'
NAME = None
NGINX_PORT = '80'
BUCKET = 'scanner-data'
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

db_cloud = yaml.load("""
image: gcr.io/cloudsql-docker/gce-proxy:1.09
command: /cloud_sql_proxy -instances={project}:{zone}:esper=tcp:0.0.0.0:3306 -credential_file=/config
volumes: ["./visualdb-key.json:/config"]
environment: []
ports: ["3306"]
""".format(project=PROJECT, zone=ZONE))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cloud-db', action='store_true')
    parser.add_argument('--cloud-files', action='store_true')
    parser.add_argument('--dataset', default='tvnews')
    args = parser.parse_args()

    if args.cloud_db:
        config['services'][svc('db')] = db_cloud
        config['services'][svc('esper')]['environment'] = [
            "DJANGO_DB_USER=will",
        ]
    else:
        config['services'][svc('db')] = db_local
        config['services'][svc('esper')]['environment'] = [
            "DJANGO_DB_USER=root",
            "DJANGO_DB_PASSWORD=${MYSQL_PASSWORD}",
        ]

    scanner_config = {}
    if args.cloud_files:
        esper_env = 'google'
        scanner_config['storage'] = {'type': 'gcs', 'bucket': BUCKET, 'db_path': 'scanner_db'}
        config['services'][svc('esper')]['environment'].extend([
            'AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}',
            'AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}',
        ])
    else:
        esper_env = 'local'
        scanner_config['storage'] = {'type': 'posix', 'db_path': '/usr/src/app/scanner_db'}

    for service in config['services'].values():
        service['environment'].extend([
            'ESPER_ENV={}'.format(esper_env), 'DATASET={}'.format(args.dataset),
            'BUCKET={}'.format(BUCKET)
        ])

    with open('esper/.scanner.toml', 'w') as f:
        f.write(toml.dumps(scanner_config))

    with open('docker-compose.yml', 'w') as f:
        f.write(yaml.dump(config))

    print 'Successfully configured Esper.'


if __name__ == '__main__':
    main()
