FROM nginx
RUN apt-get update && apt-get install -y openssl
RUN openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout /etc/nginx/cert.key -out /etc/nginx/cert.crt -subj "/C=US"
ADD nginx.conf /etc/nginx/nginx.conf.template
CMD envsubst '$OAUTH_TOKEN $MEDIA_URL $BUCKET' < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf && \
    nginx -g "daemon off;"
