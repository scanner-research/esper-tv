# Esper

## Setup
First, install Docker, docker-compose, Postgres, and npm. For Ubuntu:
* Docker: [instructions](https://docs.docker.com/engine/installation/linux/ubuntu/#prerequisites)
* docker-compose: [instructions](https://github.com/docker/compose/releases/tag/1.11.2)
* Postgres: `sudo apt-get install postgresql libpq-dev`
* npm: `sudo apt-get install npm`

If you're behind a proxy (e.g. the CMU PDL cluster), configure the [Docker proxy](https://docs.docker.com/engine/admin/systemd/#http-proxy). Make sure `https_proxy` is set as well.

```
docker-compose build
pip install -r requirements.txt
cd esper
npm install
./node_modules/.bin/webpack --config webpack.config.js
python manage.py migrate
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

## Development
While editing the SASS or JSX files, use the Webpack watcher:
```
./node_modules/.bin/webpack --config webpack.config.js --watch
```