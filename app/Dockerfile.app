ARG device=cpu
FROM esper-base:${device}
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
RUN curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py && python get-pip.py && pip install supervisor==3.3.3
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

RUN git clone https://github.com/scanner-research/vgrid /opt/vgrid && \
    cd /opt/vgrid && npm link

RUN git clone https://github.com/scanner-research/vgrid_jupyter /opt/vgrid_jupyter && \
    cd /opt/vgrid_jupyter/js && npm link vgrid &&  \
    cd /opt/vgrid_jupyter && pip3 install -e . && \
    jupyter nbextension install vgrid_jupyter --py --symlink --sys-prefix && \
    jupyter nbextension enable vgrid_jupyter --py --sys-prefix

COPY .deps/esper-run .deps/esper-ipython /usr/bin/
COPY .deps/common.sh /tmp
RUN cat /tmp/common.sh >> /root/.bashrc

ENV GLOG_minloglevel 1
ENV GOOGLE_APPLICATION_CREDENTIALS ${APPDIR}/service-key.json
ENV LD_LIBRARY_PATH $LD_LIBRARY_PATH:/usr/local/lib:/usr/local/lib/python3.5/dist-packages/hwang
ENV PYTHONPATH $PYTHONPATH:/app
ENV PYTHONPATH /opt/scannertools:$PYTHONPATH

CMD cp .scanner.toml /root/ && \
    ./scripts/google-setup.sh && \
    ./scripts/jupyter-setup.sh && \
    supervisord -c supervisord.conf
