#!/bin/bash

esper-run query/datasets/default/export.py
tar -czf example-dataset.tar.gz example.mp4 paths assets/thumbnails db-dump.sql
