#!/bin/bash
set -e

build_docker() {
    docker build -t $DOCKER_REPO:$1 --build-arg device=$1 app
    docker push $DOCKER_REPO:$1
    docker rmi -f $DOCKER_REPO:$1
}

docker login -u="$DOCKER_USER" -p="$DOCKER_PASS"
build_docker cpu
build_docker gpu
