#!/bin/sh

DB_NAME=esper
CLOUD_HOST=104.197.78.40

read -p "This will delete everything in your local database. Are you sure? [y/N] " choice
case "$choice" in
    y|Y )
        echo "Resetting database with cloud data"
        MYSQL="mysql -h db -u root ${DB_NAME}"
        echo "drop database ${DB_NAME}; create database ${DB_NAME};" | ${MYSQL}
        mysqldump --set-gtid-purged=off -h ${CLOUD_HOST} -u will ${DB_NAME} | ${MYSQL};;
    * )
        echo "Not doing anything"
esac
