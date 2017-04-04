#FROM ubuntu:16.04
FROM scannerresearch/scanner:cpu
ARG https_proxy
ENV DJANGO_CONFIGURATION Docker
ENV https_proxy=$https_proxy
ENV http_proxy=$https_proxy
RUN apt-get update && \
    apt-get install -y ffmpeg python-pip postgresql libpq-dev cron python-tk
ADD requirements.txt .
RUN pip install -r requirements.txt
WORKDIR /usr/src/app
CMD ["gunicorn", "--log-file=-", "-c", "gunicorn_conf.py", "--chdir", "django", "esper.wsgi:application", "--reload"]
# VOLUME /home/alexhall/www/film_grammar/static
