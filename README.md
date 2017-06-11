# Esper

Esper is a tool for exploratory analysis of large video collections.

* [Setup](https://github.com/scanner-research/esper#setup)
  * [Using a proxy](https://github.com/scanner-research/esper#using-a-proxy)
* [Processing videos](https://github.com/scanner-research/esper#processing-videos)
* [Development](https://github.com/scanner-research/esper#development)
* [Accessing the cloud database](https://github.com/scanner-research/esper#accessing-the-cloud-database)

## Setup
First, [install Docker](https://docs.docker.com/engine/installation/#supported-platforms).

If you have a GPU and are running on Linux:
* [Install nvidia-docker.](https://github.com/NVIDIA/nvidia-docker#quick-start)
* `pip install nvidia-docker-compose`
* For any command below that uses `docker-compose`, use `nvidia-docker-compose` instead.

If you do not have a GPU or are not running Linux: `pip install docker-compose`

```
alias dc=docker-compose
dc build
dc up -d
dc exec esper ./setup.sh
```

Then visit `http://yourserver.com`.

### Using a proxy

If you're behind a proxy (e.g. the CMU PDL cluster), configure the [Docker proxy](https://docs.docker.com/engine/admin/systemd/#http-proxy). Make sure `https_proxy` is set in your environment as well.

Use `docker-compose` for any network operations like pulling or pushing (`nvidia-docker-compose` doesn't properly use a proxy yet). Make sure `http_proxy` is NOT set when you do `ndc up -d`.

You can then use an SSH tunnel to access the webserver from your local machine:
```
ssh -L 8080:127.0.0.1:80 <your_server>
```

Then go to [http://localhost:8080](http://localhost:8080) in your browser.

See "Accessing the cloud database" for setting up the Google Cloud proxy. Make sure to modify your database settings in `esper/esper/settings.py` to change the host to `127.0.0.1`.


## Processing videos

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

By default, a development instance will use a local database. You can change to use the cloud database by modifying `DJANGO_DB_TYPE` and `DJANGO_DB_USER` in `esper/Dockerfile` and re-running `dc build`.

You can also dump the cloud database into your local instance by running:

```
cd esper
./dump-db.sh > cloud_db.sql
sqlite3 db.sqlite3 < cloud_db.sql
```

## Accessing the cloud database
To access the Google Cloud SQL database (e.g. for Tableau), first install the [Google Cloud SDK](https://cloud.google.com/sdk/downloads). Then run:

```
gcloud auth login
gcloud set project id visualdb-1046
gcloud auth application-default login
```

This sets up your machine for accessing any of the Google Cloud services. To set up the proxy to Google Cloud SQL, follow steps 2 and 4 here: [https://cloud.google.com/sql/docs/mysql/connect-admin-proxy](https://cloud.google.com/sql/docs/mysql/connect-admin-proxy)

Then connect to the database with host `127.0.0.1`. Ask Will about getting a SQL username.
