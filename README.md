# Esper [![Build Status](https://travis-ci.org/scanner-research/esper.svg?branch=master)](https://travis-ci.org/scanner-research/esper)

Esper is a tool for exploratory analysis of large video collections.

* [Setup](https://github.com/scanner-research/esper#setup)
* [Demo](https://github.com/scanner-research/esper#demo)
* [Development](https://github.com/scanner-research/esper#development)

![Esper interface](https://user-images.githubusercontent.com/663326/33038924-e656a51a-cdfb-11e7-835d-9d215b3dd93c.png)


## Setup
First, install [Docker](https://docs.docker.com/engine/installation/#supported-platforms), [Python 2.7](https://www.python.org/downloads/), and [pip](https://pip.pypa.io/en/stable/installing/).

If you have a GPU and are running on Linux:
* [Install nvidia-docker.](https://github.com/NVIDIA/nvidia-docker#quick-start)
* For any command below that uses `docker-compose`, use `nvidia-docker-compose` instead.

Next, you will need to configure your Esper installation. If you are using Google Cloud, follow the instructions in [Getting started with Google Cloud](https://github.com/scanner-research/esper/blob/master/guides/google.md) and replace `local.toml` with `google.toml` below. Otherwise, edit any relevant configuration values in `config/local.toml`. Then run:

```
echo "\nalias dc=docker-compose" >> $HOME/.profile && source $HOME/.profile
pip install -r requirements.txt
python configure.py --config config/local.toml --dataset default
dc pull
dc up -d
dc exec app ./scripts/setup.sh
```

You have successfully setup Esper! Visit [http://localhost](http://localhost) (or whatever server you're running this on) to see the frontend.


[http://localhost:8888](http://localhost:8888) to see the Jupyter notebook. To log into the Jupyter notebook, get the token by running `./scripts/jupyter-token.sh`.

### Troubleshooting

* **Cannot connect to the Docker daemon**: make sure that Docker is actually running (e.g. `docker ps` should not fail). On Linux, make sure you have non-sudo permissions (run `sudo adduser $USER docker`). On OS X, make sure the Docker application is open (should see a whale in your icon tray).

* **Permissions errors with pip**: either run pip with `sudo` or consider using a [virtualenv](https://virtualenv.pypa.io/en/stable/installation/).

* **`sh: 0: getcwd() failed: No such file or directory`**: please file an issue w/ reproducible steps if this happens. Should only occur on OS X.

## Demo
First, enter the container with `dc exec app bash`. Then run: outside the container, run:
```
wget https://storage.googleapis.com/esper/example-dataset.tar.gz
tar -xf example-dataset.tar.gz
esper-run query/datasets/default/import.py
```

Then visit [http://localhost](http://localhost). Try running some queries!
