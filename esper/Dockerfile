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

RUN apt-get install -y postgresql libpq-dev cron python-tk emacs24 sqlite3 npm nodejs && \
    ln -s /usr/bin/nodejs /usr/bin/node

ADD requirements.txt .
RUN pip install -r requirements.txt

ADD .scanner.toml /root/.scanner.toml

ENV PYTHONPATH=/usr/src/app/deps/face_recognizer:/usr/src/app/deps/openface:$PYTHONPATH
ENV GLOG_minloglevel=1

WORKDIR /usr/src/app
CMD ["gunicorn", "--log-file=-", "-c", "gunicorn_conf.py", "esper.wsgi:application", "--reload"]
