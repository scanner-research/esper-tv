ARG device=cpu
FROM scannerresearch/scanner:${device}
# ARGS before FROM aren't accessible after the FROM, so we need to replicate the device arg.
ARG device2=cpu
ARG cores=1
ARG https_proxy
ENV DJANGO_CONFIGURATION Docker
ENV https_proxy=$https_proxy
ENV http_proxy=$https_proxy
ENV TERM=xterm

# Misc apt dependencies
RUN apt-get update && \
    apt-get install -y postgresql libpq-dev cron python-tk sqlite3 \
    npm nodejs curl && \
    ln -s /usr/bin/nodejs /usr/bin/node

# OpenPose
WORKDIR /opt
ADD .deps/Makefile.config .
RUN git clone https://github.com/CMU-Perceptual-Computing-Lab/openpose/ && \
    cd openpose && \
    mv ../Makefile.config . && \
    make all -j${cores} && \
    cd models && ./getModels.sh && cd .. && \
    mv .build_release /tmp/openpose && \
    cp -r include models /tmp/openpose && \
    rm -rf /opt/openpose && \
    mv /tmp/openpose /opt

WORKDIR /app/deps
RUN git clone https://github.com/scanner-research/openpose-scanner.git && \
    cd openpose-scanner && \
    mkdir build && \
    cd build && \
    echo '\n\
scanner_path = "/opt/scanner"\n\
[storage]\n\
type = "posix"\n\
db_path = "/tmp"'  > /root/.scanner.toml && \
    cmake .. && \
    make

# Google Cloud SDK
RUN echo "deb http://packages.cloud.google.com/apt cloud-sdk-xenial main" | \
    tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add - && \
    apt-get update && apt-get install -y google-cloud-sdk

# Python dependencies
ADD requirements.txt .
RUN (if [ "$device2" = "cpu" ]; then pip install tensorflow==1.2.0; else pip install tensorflow-gpu==1.2.0; fi) && \
    pip install -r requirements.txt && \
    jupyter nbextension enable --py --sys-prefix widgetsnbextension && \
    python -c "import matplotlib"

# Fix npm hanging on OS X
# https://github.com/npm/npm/issues/7862#issuecomment-220798263
RUN npm config set registry http://registry.npmjs.org && \
    npm config set strict-ssl false

ADD .deps/esper-run /usr/bin

ENV APPDIR=/app
WORKDIR ${APPDIR}

ENV PYTHONPATH=${APPDIR}:${APPDIR}/deps/face_recognizer:${APPDIR}/deps/openface:${APPDIR}/deps/rude-carnie:${APPDIR}/deps/facenet/src:$PYTHONPATH
ENV GLOG_minloglevel=1
ENV GOOGLE_APPLICATION_CREDENTIALS=${APPDIR}/service-key.json

CMD cp .scanner.toml /root/ && \
    ./scripts/google-setup.sh && \
    supervisord -c supervisord.conf
