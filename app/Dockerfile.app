ARG device=cpu
FROM scannerresearch/esper-base:${device}
ARG https_proxy
ARG cores=1
ENV DJANGO_CONFIGURATION Docker
ENV https_proxy=$https_proxy
ENV http_proxy=$https_proxy
ENV TERM=xterm

# Misc apt dependencies
RUN apt-get update && \
    apt-get install -y cron python-tk npm nodejs curl unzip jq gdb psmisc zsh libgnutls-dev && \
    ln -s /usr/bin/nodejs /usr/bin/node

# Custom install of ffmpeg to include gnutls so we can do remote access to video files
RUN git clone https://git.ffmpeg.org/ffmpeg.git ffmpeg && \
    cd ffmpeg && \
    ./configure --prefix=/usr/local --extra-version=0ubuntu0.16.04.1 --toolchain=hardened --cc=cc --cxx=g++ --enable-gpl --enable-shared --disable-stripping --disable-decoder=libschroedinger --enable-avresample --enable-libx264 --enable-nonfree --enable-gnutls && \
    make install -j${cores} && \
    cd .. && \
    rm -rf ffmpeg

# Google Cloud SDK
RUN echo "deb http://packages.cloud.google.com/apt cloud-sdk-xenial main" | \
    tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add - && \
    apt-get update && apt-get install -y google-cloud-sdk kubectl

# Python setup
COPY requirements.app.txt ./
RUN pip install -r requirements.app.txt
COPY .deps/nbconfig /root/.jupyter/nbconfig
COPY .deps/ipython_config.py /root/.ipython/profile_default/ipython_config.py
RUN jupyter nbextension enable qgrid --py --sys-prefix && \
    jupyter nbextension install --sys-prefix --py vega && \
    jupyter nbextension enable vega --py --sys-prefix && \
    jupyter nbextension enable --py --sys-prefix widgetsnbextension && \
    jupyter contrib nbextension install --user && \
    jupyter nbextensions_configurator enable --user && \
    jupyter nbextension enable hide_input/main && \
    jupyter nbextension enable toc2/main && \
    jupyter nbextension enable code_prettify/autopep8 && \
    python -c "import matplotlib"

# Fix npm hanging on OS X
# https://github.com/npm/npm/issues/7862#issuecomment-220798263
RUN npm config set registry http://registry.npmjs.org && \
    npm config set strict-ssl false

COPY .deps/esper-run /usr/bin
COPY .deps/common.sh /tmp
RUN cat /tmp/common.sh >> /root/.bashrc

ENV GLOG_minloglevel=1
ENV GOOGLE_APPLICATION_CREDENTIALS=${APPDIR}/service-key.json
ENV LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/lib

RUN python -m spacy download en

CMD cp .scanner.toml /root/ && \
    ./scripts/google-setup.sh && \
    python scripts/set-jupyter-password.py && \
    supervisord -c supervisord.conf
