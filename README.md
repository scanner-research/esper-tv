# Esper

Esper is a tool for exploratory analysis of large video collections.

* [Setup](https://github.com/scanner-research/esper#setup)
  * [Accessing the local database](https://github.com/scanner-research/esper#accessing-the-local-database)
  * [Using the cloud database](https://github.com/scanner-research/esper#using-the-cloud-database)
  * [Using a proxy](https://github.com/scanner-research/esper#using-a-proxy)
* [Processing videos](https://github.com/scanner-research/esper#processing-videos)
* [Using Tableau](https://github.com/scanner-research/esper#using-tableau)
* [Development](https://github.com/scanner-research/esper#development)

## Setup
First, [install Docker](https://docs.docker.com/engine/installation/#supported-platforms).

If you have a GPU and are running on Linux:
* [Install nvidia-docker.](https://github.com/NVIDIA/nvidia-docker#quick-start)
* For any command below that uses `docker-compose`, use `nvidia-docker-compose` instead.

```
export MYSQL_PASSWORD=<pick a password, save it to your shell .rc>
alias dc=docker-compose

pip install -r requirements.txt
python configure.py -c config/local.toml
dc pull
dc up -d
dc exec esper ./scripts/setup.sh
```

Then visit `http://yourserver.com`.


### Accessing the local database
The default Esper build comes with a local Postgres database, saved to `mysql-db` inside the Esper repository. It is exposed on the default port (3306) and comes with a root user whose password is what you specified in `MYSQL_PASSWORD`. Connect to the database with:
```
mysql -h <your server> -u root -p${MYSQL_PASSWORD} esper
```

_Note: that the root password will be set for good after the first time you run `dc up -d nginx`, so you need to either reset the database or run the `ALTER PASSWORD` SQL command to change the root password again._


### Using the cloud database

To use the Google Cloud SQL database, first [install git-crypt](https://github.com/AGWA/git-crypt/blob/master/INSTALL.md). Get the secret `esper.key` from Will and inside the repository run:

```
git-crypt unlock /path/to/esper.key
```

Then in `docker-compose.yml` under the `esper` service, uncomment `db-cloud` under `depends_on`. Re-run `dc down && dc up -d nginx`.

If you want to continue using your local MySQL database but just pull all the data from the cloud, then go into the `esper` container and run:
```
./scripts/load-cloud-db.sh
```

If you want to use the cloud database as the actual backend for your Django server, then
go to `docker-compose.yml` and modify the appropriate `environment` settings. Re-run `dc down && dc up -d nginx`.


### Using a proxy

If you're behind a proxy (e.g. the CMU PDL cluster), configure the [Docker proxy](https://docs.docker.com/engine/admin/systemd/#http-proxy). Make sure `https_proxy` is set in your environment as well.

Use `docker-compose` for any network operations like pulling or pushing (`nvidia-docker-compose` doesn't properly use a proxy yet). Make sure `http_proxy` is NOT set when you do `dc up -d nginx`.

You can then use an SSH tunnel to access the webserver from your local machine:
```
ssh -L 8080:127.0.0.1:80 <your_server>
```

Then go to [http://localhost:8080](http://localhost:8080) in your browser.


## Processing videos

To add videos to the database, add them somewhere in the `esper` directory (the directory containing `manage.py`) and create a file `paths` that contains a newline-separated list of relative paths to your videos. Open a shell in the Docker container by running `docker-compose exec esper bash` and then run:
```
python manage.py ingest paths
python manage.py face_detect paths
python manage.py face_cluster paths
```


## Using Jupyter

First, enter the Esper container:
```
dc exec esper bash
```

Then inside the container run:
```
python manage.py shell_plus --notebook
```

Then in your browser, visit the address of your server on port 8888.

## Using Tableau

Ask Will about getting permissions on the Esper project in Google Cloud. Then, install the [Google Cloud SDK](https://cloud.google.com/sdk/downloads). After that, run:
```
gcloud auth login
gcloud config set project visualdb-1046
gcloud auth application-default login
```

This sets up your machine for accessing any of the Google Cloud services. Then, download the [Google Cloud proxy tool](https://cloud.google.com/sql/docs/mysql/connect-admin-proxy#install) and run:
```
./cloud_sql_proxy -instances=visualdb-1046:us-west1:esper-shared=tcp:5432
```

Then download the Esper workbook with:

```
gsutil cp gs://esper/Esper.twb .
```

Open up Tableau ([download](https://www.tableau.com/academic/students#form)), do **File -> Open** and open the `Esper.twb` file. Replace the prompted user name with your own SQL user and click **Sign in**.

To use your own MySQL database:
1. Click **Data Source** in the bottom left.
2. Click the dropdown arrow in box labeled **127.0.0.1** in the top left underneath **Connections**.
3. Select **Edit connection...**.
4. Change the server to wherever your local instance is located.
5. Change the username to `root`.
6. Change the password to the value of your `$MYSQL_PASSWORD`.
7. Click **Sign in**.
8. Click **Update now** in the middle-bottom box.


## Development

While editing the SASS or JSX files, use the Webpack watcher:
```
./scripts/build-frontend.sh
```

This will automatically rebuild all the frontend files into `assets/bundles` when you change a relevant file.
