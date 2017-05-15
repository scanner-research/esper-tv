# Esper

## Setup
First, [install Docker](https://docs.docker.com/engine/installation/#supported-platforms).

If you have a GPU and are running on Linux:
* [Install nvidia-docker.](https://github.com/NVIDIA/nvidia-docker#quick-start)
* `pip install nvidia-docker-compose`
* For any command below that uses `docker-compose`, use `nvidia-docker-compose` instead.

If you do not have a GPU or are not running Linux: `pip install docker-compose`

If you're behind a proxy (e.g. the CMU PDL cluster), configure the [Docker proxy](https://docs.docker.com/engine/admin/systemd/#http-proxy). Make sure `https_proxy` is set in your environment as well.

```
docker-compose build
docker-compose up -d
docker-compose exec esper ./setup.sh
```

Then visit `http://yourserver.com`.

To add videos to the database, add them somewhere in the `esper` directory (the directory containing `manage.py`) and create a file `paths` that contains a newline-separated list of relative paths to your videos. Open a shell in the Docker container by running `docker-compose exec esper bash` and then run:

```
python manage.py ingest paths
python manage.py face_detect paths
python manage.py face_cluster paths
```

## Development
While editing the SASS or JSX files, use the Webpack watcher:
```
./node_modules/.bin/webpack --config webpack.config.js --watch
```
