FROM ubuntu:16.04

RUN apt-get update -y && \
    apt-get install -y python-pip python-dev ffmpeg

ADD requirements.txt .
RUN pip install -r requirements.txt

ADD *.py ./

ENV FLASK_APP=server.py
CMD gunicorn --config gunicorn_config.py server:app
