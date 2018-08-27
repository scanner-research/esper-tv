#!/bin/bash
redis-cli -h 10.0.0.3 -p 6379 -n 0 llen celery
