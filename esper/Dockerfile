FROM scannerresearch/scanner:gpu
ARG https_proxy ""
ENV DJANGO_CONFIGURATION Docker
ENV https_proxy=$https_proxy
ENV http_proxy=$https_proxy
ENV TERM=xterm

# Torch
RUN git clone https://github.com/torch/distro.git /opt/torch --recursive && \
    cd /opt/torch && bash install-deps && ./install.sh -b && \
    source ~/.bashrc &&
    for NAME in torch dpnn nn optim optnet csvigo cutorch cunn fblualib torchx tds; \
        do luarocks install $NAME; \
    done

RUN apt-get update && \
    apt-get install -y postgresql libpq-dev cron python-tk emacs24 sudo

ADD requirements.txt .
RUN pip install -r requirements.txt

ENV PYTHONPATH=/usr/src/app/deps/face_recognizer:/usr/src/app/deps/openface:$PYTHONPATH

WORKDIR /usr/src/app
CMD ["gunicorn", "--log-file=-", "-c", "gunicorn_conf.py", "esper.wsgi:application", "--reload"]
