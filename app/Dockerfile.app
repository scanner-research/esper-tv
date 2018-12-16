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

# Install baseline Jupyter extensions
COPY .deps/nbconfig /root/.jupyter/nbconfig
COPY .deps/beakerx.json /root/.jupyter/beakerx.json
COPY .deps/ipython_config.py /root/.ipython/profile_default/ipython_config.py
RUN jupyter nbextension enable --py --sys-prefix widgetsnbextension && \
    jupyter contrib nbextension install --user && \
    jupyter nbextensions_configurator enable --user && \
    jupyter nbextension enable hide_input/main && \
    jupyter nbextension enable toc2/main && \
    jupyter nbextension enable code_prettify/autopep8 && \
    jupyter nbextension enable execute_time/ExecuteTime && \
    beakerx install && \
    python3 -c "import matplotlib"

# Fix npm hanging on OS X
# https://github.com/npm/npm/issues/7862#issuecomment-220798263
RUN npm config set registry http://registry.npmjs.org && \
    npm config set strict-ssl false

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
