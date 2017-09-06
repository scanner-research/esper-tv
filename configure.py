import argparse
import yaml

USER = 'pari'
PROJECT = 'visualdb-1046'
ZONE = 'us-central1'
NAME = 'esper'

config = yaml.load("""
version: '2'
services:
  nginx-{name}:
    build: ./nginx
    image: scannerresearch/esper-nginx
    volumes:
      - ./esper:/usr/src/app
    depends_on:
      - esper-{name}
    ports:
      - "80:80"

  esper-{name}:
    build:
      context: ./esper
      args:
        https_proxy: "${{https_proxy}}"
    image: scannerresearch/esper
    volumes:
      - ./esper:/usr/src/app
      - ${{HOME}}/.bash_history:/root/.bash_history
    ports:
      - "8000"
""".format(name=USER))

db_local = yaml.load("""
image: mysql
environment:
  - MYSQL_DATABASE=esper
  - MYSQL_ROOT_PASSWORD=${MYSQL_PASSWORD}
volumes:
  - ./mysql-db:/var/lib/mysql
ports:
  - "3306:3306"
""")

db_cloud = yaml.load("""
image: gcr.io/cloudsql-docker/gce-proxy:1.09
command: /cloud_sql_proxy -instances={project}:{zone}:{name}=tcp:0.0.0.0:3306 -credential_file=/config
volumes:
  - ./visualdb-key.json:/config
ports:
  - "3306"
""".format(project=PROJECT, zone=ZONE, name=NAME))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cloud', action='store_true')
    args = parser.parse_args()

    if args.cloud:
        config['services']['db-cloud-{name}'.format(name=USER)] = db_cloud
        config['services']['esper-{name}'.format(name=USER)]['depends_on'] = ['db-cloud-{name}'.format(name=USER)]
        config['services']['esper-{name}'.format(name=USER)]['environment'] = [
            "DJANGO_DB_HOST=db-cloud-{name}".format(name=USER),
            "DJANGO_DB_USER=will"
        ]
    else:
        config['services']['db-local-{name}'.format(name=USER)] = db_local
        config['services']['esper-{name}'.format(name=USER)]['depends_on'] = ['db-local-{name}'.format(name=USER)]
        config['services']['esper-{name}'.format(name=USER)]['environment'] = [
            "DJANGO_DB_HOST=db-local-{name}".format(name=USER),
            "DJANGO_DB_PASSWORD=${MYSQL_PASSWORD}",
            "DJANGO_DB_USER=root"
        ]

    with open('docker-compose.yml', 'w') as f:
        f.write(yaml.dump(config))

if __name__ == '__main__':
    main()
