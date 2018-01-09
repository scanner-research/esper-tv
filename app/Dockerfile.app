ARG device=cpu
FROM scannerresearch/esper-base:${device}
# ARGS before FROM aren't accessible after the FROM, so we need to replicate the device arg.
ARG tf_version=1.2.0
ARG build_tf=off
ARG device2=cpu
ARG cores=1
ARG https_proxy
ENV DJANGO_CONFIGURATION Docker
ENV https_proxy=$https_proxy
ENV http_proxy=$https_proxy
ENV TERM=xterm

# Misc apt dependencies
RUN apt-get update && \
    apt-get install -y postgresql-9.5 libpq-dev cron python-tk npm nodejs curl unzip jq gdb psmisc && \
    ln -s /usr/bin/nodejs /usr/bin/node

# Google Cloud SDK
RUN echo "deb http://packages.cloud.google.com/apt cloud-sdk-xenial main" | \
    tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add - && \
    apt-get update && apt-get install -y google-cloud-sdk kubectl

# Python setup
ADD .deps/nbconfig /root/.jupyter/nbconfig
ADD requirements.app.txt ./
RUN pip install -r requirements.app.txt && \
    jupyter nbextension enable qgrid --py --sys-prefix && \
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

ADD .deps/esper-run /usr/bin

ENV GLOG_minloglevel=1
ENV GOOGLE_APPLICATION_CREDENTIALS=${APPDIR}/service-key.json

CMD cp .scanner.toml /root/ && \
    ./scripts/google-setup.sh && \
    python scripts/set-jupyter-password.py && \
    . ./scripts/clear-proxy.sh && \
    supervisord -c supervisord.conf
