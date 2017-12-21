#!/bin/sh

# FIXME(wcrichto): this script is probably broken

DB_NAME=esper

read -p "This will delete everything in your local database. Are you sure? [y/N] " choice
case "$choice" in
    y|Y )
        echo "Resetting database with cloud data"
        MYSQL="mysql -h db-local -u root -p${DJANGO_DB_PASSWORD} ${DB_NAME}"
        echo "drop database ${DB_NAME}; create database ${DB_NAME};" | ${MYSQL}
        mysqldump --set-gtid-purged=off -h db-cloud -u will ${DB_NAME} | ${MYSQL};;
    * )
        echo "Not doing anything"
esac
