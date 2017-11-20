#!/bin/bash
docker-compose logs app | grep "?token" | sed 's/.*\?token=\(.*\)/\1/p' | tail -n 1
