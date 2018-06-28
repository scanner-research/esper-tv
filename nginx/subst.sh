#!/bin/bash

for f in /tmp/*.template
do
    full=$(basename $f)
    name="${full%.*}"
    envsubst '$ESPER_ENV $BUCKET $PORT $DATA_PATH $HOSTNAME' < $f > /etc/nginx/$name
done

nginx -g "daemon off;"
