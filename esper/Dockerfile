FROM scannerresearch/scanner:gpu
ARG https_proxy
ENV DJANGO_CONFIGURATION Docker
ENV https_proxy=$https_proxy
ENV http_proxy=$https_proxy
ENV TERM=xterm

# Need sudo so Torch can install
RUN apt-get update && apt-get install -y sudo

# Torch
# Have to run this in bash for the torch bashrc settings to get propagated
RUN git clone https://github.com/torch/distro.git /opt/torch --recursive && \
    cd /opt/torch && bash install-deps && ./install.sh -b && \
    . /opt/torch/install/bin/torch-activate && \
    for NAME in torch dpnn nn optim optnet csvigo cutorch cunn fblualib torchx tds; \
        do luarocks install $NAME; \
    done

# Misc apt dependencies
RUN apt-get update && \
    apt-get install -y postgresql libpq-dev cron python-tk emacs24 sqlite3 \
    npm nodejs vim mysql-client libmysqlclient-dev && \
    ln -s /usr/bin/nodejs /usr/bin/node

# Google Cloud SDK
RUN echo "deb http://packages.cloud.google.com/apt cloud-sdk-xenial main" | \
    tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add - && \
    apt-get update && apt-get install -y google-cloud-sdk

# Python dependencies
ADD requirements.txt .
RUN pip install -r requirements.txt

ADD .scanner.toml /root/.scanner.toml

ENV PYTHONPATH=/usr/src/app/deps/face_recognizer:/usr/src/app/deps/openface:/usr/src/app/deps/rude-carnie:/usr/src/app/deps/facenet/src:$PYTHONPATH
ENV GLOG_minloglevel=1

WORKDIR /usr/src/app

# TODO(wcrichto): don't run this if running without --cloud-files
ADD visualdb-key.json .
ENV GOOGLE_APPLICATION_CREDENTIALS=/usr/src/app/visualdb-key.json
RUN gcloud config set project visualdb-1046 && \
    gcloud auth activate-service-account --key-file=$GOOGLE_APPLICATION_CREDENTIALS

CMD ["gunicorn", "--log-file=-", "-c", "gunicorn_conf.py", "esper.wsgi:application", "--reload"]
