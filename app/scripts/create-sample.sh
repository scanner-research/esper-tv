#!/bin/bash

rm -rf example-dataset.tar.gz example.mp4 paths db-dump.sql assets/thumbnails
youtube-dl "https://www.youtube.com/watch?v=dQw4w9WgXcQ" -f mp4 -o example.mp4
echo "example.mp4" > paths
python manage.py cleanup Video
esper-run query/datasets/default/ingest.py
python manage.py face_detect paths
python manage.py pose_detect paths
esper-run query/datasets/default/export.py
tar -czf example-dataset.tar.gz example.mp4 paths assets/thumbnails db-dump.sql
