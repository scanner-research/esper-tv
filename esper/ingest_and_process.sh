#!/bin/bash
while IFS='' read -r line || [[ -n "$line" ]]; do
    echo $line > temppaths
    cat temppaths
    ./manage.py ingest_test temppaths < /dev/null
    ./manage.py face_detect_mtcnn temppaths < /dev/null
    ./manage.py face_gender temppaths < /dev/null
done < "$1"
