# Esper [![Build Status](https://travis-ci.org/scanner-research/esper.svg?branch=master)](https://travis-ci.org/scanner-research/esper)

Esper is a framework for exploratory analysis of large video collections. Esper takes as input set of videos and a database of metadata about the videos (e.g. bounding boxes, poses, tracks). Esper provides a web UI (shown below) and a programmatic interface ([Jupyter](http://jupyter.org/) notebook) for visualizing and analyzing this metadata.

* [Setup](https://github.com/scanner-research/esper#setup)
* [Demo](https://github.com/scanner-research/esper#demo)
* [Getting started](https://github.com/scanner-research/esper#demo)

![Esper interface](https://user-images.githubusercontent.com/663326/33038924-e656a51a-cdfb-11e7-835d-9d215b3dd93c.png)


## Setup
First, install [Docker](https://docs.docker.com/engine/installation/#supported-platforms), [Python 2.7](https://www.python.org/downloads/), and [pip](https://pip.pypa.io/en/stable/installing/).

If you have a GPU and are running on Linux, then [install nvidia-docker.](https://github.com/NVIDIA/nvidia-docker#quick-start). For any command below that uses `docker-compose`, use `nvidia-docker-compose` instead.

Next, you will need to configure your Esper installation. If you are using Google Cloud, follow the instructions in [Getting started with Google Cloud](https://github.com/scanner-research/esper/blob/master/guides/google.md) and replace `local.toml` with `google.toml` below. Otherwise, edit any relevant configuration values in `config/local.toml`. Then run:

```
echo "\nalias dc=docker-compose" >> $HOME/.profile && source $HOME/.profile
pip install -r requirements.txt
python configure.py --config config/local.toml --dataset default
dc pull
dc up -d
dc exec app ./scripts/setup.sh
```

You have successfully setup Esper! Visit [http://localhost](http://localhost) (or whatever server you're running this on) to see the frontend. You will see a query interface, but we can't do anything with it until we get some data. Go through the [Demo](https://github.com/scanner-research/esper#demo) below to visualize some sample videos and metadata we have provided.



### Troubleshooting

* **Cannot connect to the Docker daemon**: make sure that Docker is actually running (e.g. `docker ps` should not fail). On Linux, make sure you have non-sudo permissions (run `sudo adduser $USER docker`). On OS X, make sure the Docker application is open (should see a whale in your icon tray).

* **Permissions errors with pip**: either run pip with `sudo` or consider using a [virtualenv](https://virtualenv.pypa.io/en/stable/installation/).

* **`sh: 0: getcwd() failed: No such file or directory`**: please file an issue w/ reproducible steps if this happens. Should only occur on OS X.


## Demo
First, enter the Esper application container with `dc exec app bash`. Then run:
```
wget https://storage.googleapis.com/esper/example-dataset.tar.gz
tar -xf example-dataset.tar.gz
esper-run query/datasets/default/import.py
```

Then visit [http://localhost](http://localhost) to see the web UI. Try running some queries!

Next, check out the Jupyter programming environment by visiting [http://localhost:8888/notebooks/notebooks/example.ipynb](http://localhost:8888/notebooks/notebooks/example.ipynb). To log into the Jupyter notebook, get the token by running `./scripts/jupyter-token.sh` outside the container.


## Getting started

TODO(wcrichto): getting started with your own dataset
