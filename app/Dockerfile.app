ARG base_name
ARG device=cpu
FROM ${base_name}:${device}
ARG cores=1
ENV DJANGO_CONFIGURATION Docker
ENV TERM=xterm

# Misc apt dependencies
RUN apt-get update && \
    apt-get install -y cron npm nodejs curl unzip jq gdb psmisc zsh && \
    ln -s /usr/bin/nodejs /usr/bin/node

# Google Cloud SDK
RUN echo "deb http://packages.cloud.google.com/apt cloud-sdk-xenial main" | \
    tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add - && \
    apt-get update && apt-get install -y google-cloud-sdk kubectl

# Python setup
COPY requirements.app.txt ./
RUN pip3 install -r requirements.app.txt

# supervisor only works with python2, so have to specially download old pip to install it
RUN curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py && python get-pip.py && pip install supervisor==3.3.3

# IPython config
COPY .deps/ipython_config.py /root/.ipython/profile_default/ipython_config.py
RUN mkdir -p /root/.ipython/profile_local/startup
COPY .deps/ipython_config.py /root/.ipython/profile_local/ipython_config.py
COPY .deps/00-load-django.py /root/.ipython/profile_local/startup/00-load-django.py

# Fix npm hanging on OS X
# https://github.com/npm/npm/issues/7862#issuecomment-220798263
RUN npm config set registry http://registry.npmjs.org && \
    npm config set strict-ssl false

RUN npm i -g npm n && n stable

# Install npm packages in ~/.local by default so they persist across container restarts
RUN npm config set prefix /root/.local

# Setup bash helpers
COPY .deps/esper-run .deps/esper-ipython /usr/bin/
COPY .deps/common.sh /tmp
RUN cat /tmp/common.sh >> /root/.bashrc

# Fix Google Cloud Storage URL library dependencies
RUN unset PYTHONPATH && pip2 install cryptography

ENV GLOG_minloglevel 1
ENV GOOGLE_APPLICATION_CREDENTIALS ${APPDIR}/service-key.json
ENV LD_LIBRARY_PATH $LD_LIBRARY_PATH:/usr/local/lib:/usr/local/lib/python3.5/dist-packages/hwang
ENV PYTHONPATH $PYTHONPATH:/app
ENV PYTHONPATH /opt/scannertools:$PYTHONPATH

CMD cp .scanner.toml /root/ && \
    ./scripts/google-setup.sh && \
    ./scripts/jupyter-setup.sh && \
    supervisord -c supervisord.conf
