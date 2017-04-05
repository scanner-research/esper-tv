# Esper

## Setup
First, install Docker, docker-compose, Postgres, and npm. For Ubuntu:
* Docker: [instructions](https://docs.docker.com/engine/installation/linux/ubuntu/#prerequisites)
* docker-compose: [instructions](https://github.com/docker/compose/releases/tag/1.11.2)
* Postgres: `sudo apt-get install postgresql libpq-dev`
* npm: `sudo apt-get install npm`

If you're behind a proxy (e.g. the CMU PDL cluster), configure the [Docker proxy](https://docs.docker.com/engine/admin/systemd/#http-proxy). Make sure `https_proxy` is set as well.

```
pip install -r requirements.txt
cd django && python manage.py migrate && cd ..
docker-compose build
```

## Running Esper
To start the server:
```
docker-compose up -d
```

Then visit `http://yourserver.com`.

To stop the server:
```
docker-compose down
```
