import argparse
import yaml
import toml

PROJECT = 'visualdb-1046'
ZONE = 'us-central1'
NAME = 'esper'
NGINX_PORT = '443'
BUCKET = 'scanner-data'

config = yaml.load("""
version: '2'
services:
  nginx:
    build: ./nginx
    image: scannerresearch/esper-nginx
    volumes:
      - ./esper:/usr/src/app
      - /mnt/gcs:/usr/src/app/gcs
    depends_on: [esper]
    ports: ["{port}:{port}"]
    environment: []

  esper:
    build:
      context: ./esper
      args:
        https_proxy: "${{https_proxy}}"
    image: scannerresearch/esper
    privileged: true
    volumes:
      - ./esper:/usr/src/app
      - ${{HOME}}/.bash_history:/root/.bash_history
      - ./visualdb-key.json:/usr/src/app/visualdb-key.json
      - /mnt/gcs:/usr/src/app/gcs
    ports: ["8000"]
""".format(port=NGINX_PORT))

db_local = yaml.load("""
image: mysql
environment:
  - MYSQL_DATABASE=esper
  - MYSQL_ROOT_PASSWORD=${MYSQL_PASSWORD}
volumes: ["./mysql-db:/var/lib/mysql"]
ports: ["3306"]
""")

db_cloud = yaml.load("""
image: gcr.io/cloudsql-docker/gce-proxy:1.09
command: /cloud_sql_proxy -instances={project}:{zone}:{name}=tcp:0.0.0.0:3306 -credential_file=/config
volumes: ["./visualdb-key.json:/config"]
ports: ["3306"]
""".format(project=PROJECT, zone=ZONE, name=NAME))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cloud-db', action='store_true')
    parser.add_argument('--cloud-files', action='store_true')
    args = parser.parse_args()

    if args.cloud_db:
        config['services']['db-cloud'] = db_cloud
        config['services']['esper']['depends_on'] = ['db-cloud']
        config['services']['esper']['environment'] = [
            "DJANGO_DB_HOST=db-cloud",
            "DJANGO_DB_USER=will",
        ]
    else:
        config['services']['db-local'] = db_local
        config['services']['esper']['depends_on'] = ['db-local']
        config['services']['esper']['environment'] = [
            "DJANGO_DB_HOST=db-local",
            "DJANGO_DB_PASSWORD=${MYSQL_PASSWORD}",
            "DJANGO_DB_USER=root",
        ]

    scanner_config = {}
    if args.cloud_files:
        esper_env = 'google'
        scanner_config['storage'] = {
            'type': 'gcs',
            'bucket': BUCKET,
            'db_path': 'scanner_db'
        }
        media_url = 'https://storage.googleapis.com'
        config['services']['esper']['environment'].extend([
            'AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}',
            'AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}'
        ])
        config['services']['nginx']['environment'].extend([
            'BUCKET={}'.format(BUCKET),
            'OAUTH_TOKEN=${OAUTH_TOKEN}'
        ])
    else:
        esper_env = 'local'
        scanner_config['storage'] = {
            'type': 'posix',
            'db_path': '/usr/src/app/scanner_db'
        }
        media_url = '/'

    config['services']['nginx']['environment'].append('MEDIA_URL={}'.format(media_url))
    config['services']['esper']['environment'].append('ESPER_ENV={}'.format(esper_env))
    with open('esper/.scanner.toml', 'w') as f:
        f.write(toml.dumps(scanner_config))

    with open('docker-compose.yml', 'w') as f:
        f.write(yaml.dump(config))

if __name__ == '__main__':
    main()
