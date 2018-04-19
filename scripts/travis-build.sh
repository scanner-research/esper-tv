#!/bin/bash
set -e

if [ "$TRAVIS_BRANCH" = "master" -a "$TRAVIS_PULL_REQUEST" = "false" ]; then
    PUSH=0
else
    PUSH=1
fi

build_docker() {
    python3 configure.py -c config/local.toml
    docker build -f app/Dockerfile.app -t $DOCKER_REPO:$1 --build-arg device=$1 --build-arg device2=$1 app

    if [ $PUSH -eq 0 ]; then
        docker push $DOCKER_REPO:$1
        docker rmi -f $DOCKER_REPO:$1
    fi
}

if [ $PUSH -eq 0 ]; then
    yes | docker login -u="$DOCKER_USER" -p="$DOCKER_PASS"
fi

build_docker cpu
# build_docker gpu
