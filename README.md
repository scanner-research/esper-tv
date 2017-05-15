# Esper

## Setup
First, install Docker, docker-compose, Postgres, and npm. For Ubuntu:
* Docker: [instructions](https://docs.docker.com/engine/installation/linux/ubuntu/#prerequisites)
* docker-compose: `pip install docker-compose`

If you're behind a proxy (e.g. the CMU PDL cluster), configure the [Docker proxy](https://docs.docker.com/engine/admin/systemd/#http-proxy). Make sure `https_proxy` is set as well.

```bash
docker-compose build
docker-compose up -d
docker-compose exec esper ./setup.sh
```

Then visit `http://yourserver.com`.

To add videos to the database, add them somewhere in the `esper` directory (the directory containing `manage.py`) and create a file `paths` that contains a newline-separated list of relative paths to your videos. Open a shell in the Docker container by running `docker-compose exec esper bash` and then run:

```bash
python manage.py ingest paths
python manage.py face_detect paths
python manage.py face_cluster paths
```

## Development
While editing the SASS or JSX files, use the Webpack watcher:
```bash
./node_modules/.bin/webpack --config webpack.config.js --watch
```
