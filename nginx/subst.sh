#!/bin/bash

for f in /tmp/*.template
do
    full=$(basename $f)
    name="${full%.*}"
    envsubst '$ESPER_ENV $BUCKET $PORT' < $f > /etc/nginx/$name
done

nginx -g "daemon off;"
