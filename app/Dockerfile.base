ARG tag
FROM scannerresearch/scannertools:${tag}-latest
# ARGS before FROM aren't accessible after the FROM, so we need to replicate the device arg.
ARG build_tf=off
ARG tf_version=1.12.0
ARG device=cpu
ARG cores=1

ENV APPDIR=/app
WORKDIR ${APPDIR}

RUN apt-get update && apt-get install -y default-jre postgresql-9.5 libpq-dev gdb
COPY ./scripts ./scripts
COPY ./requirements.base.txt ./
RUN ./scripts/build-tf.sh
RUN pip3 install -r requirements.base.txt

COPY ./.deps/.dummy scannerpatc[h] ./
RUN if [ -f /app/scannerpatch ]; then \
    cd /opt/scanner && \
    git apply /app/scannerpatch && \
    ./build.sh; \
    fi

COPY ./.scanner.toml /root/.scanner/config.toml
