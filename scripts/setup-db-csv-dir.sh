#!/bin/bash

docker-compose exec db bash -c "mkdir -p /app/pg && chown postgres /app/pg"
