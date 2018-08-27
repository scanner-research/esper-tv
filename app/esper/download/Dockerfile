FROM ubuntu:16.04
WORKDIR /app
RUN apt update && apt install -y python3 python3-pip curl
RUN pip3 install tqdm celery[redis] internetarchive
# Google Cloud SDK
COPY service-key.json .
COPY ia.ini /root/.config/ia.ini
ENV GOOGLE_APPLICATION_CREDENTIALS /app/service-key.json
RUN echo "deb http://packages.cloud.google.com/apt cloud-sdk-xenial main" | \
    tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add - && \
    apt-get update && apt-get install -y google-cloud-sdk kubectl && \
    gcloud config set project visualdb-1046 && \
    gcloud auth activate-service-account --key-file=$GOOGLE_APPLICATION_CREDENTIALS
COPY tasks.py .
CMD celery -A tasks worker -c 20