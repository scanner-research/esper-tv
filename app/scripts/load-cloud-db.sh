#!/bin/sh

pg_dump -h db -U will esper > cloud_db.sql

# read -p "This will delete everything in your local database. Are you sure? [y/N] " choice
# case "$choice" in
#     y|Y )
#         echo "Resetting database with cloud data"
#         FLAGS="-h db -U ${DJANGO_DB_USER}"
#         #echo "drop database esper; create database esper;" | psql ${FLAGS} -d postgres
#         mysqldump --set-gtid-purged=off -h db-cloud -u will ${DB_NAME} | ${MYSQL};;
#     * )
#         echo "Not doing anything"
# esac
