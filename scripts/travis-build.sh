#!/bin/bash
set -e


build_docker() {
    python configure.py -c config/local.toml --no-build-kube
    docker build -f app/Dockerfile.app -t $DOCKER_REPO:$1 --build-arg device=$1 --build-arg device2=$1 app

    if [ "$TRAVIS_BRANCH" = "master" -a "$TRAVIS_PULL_REQUEST" = "false" ]; then
        docker push $DOCKER_REPO:$1
        docker rmi -f $DOCKER_REPO:$1
    fi
}

docker login -u="$DOCKER_USER" -p="$DOCKER_PASS"
build_docker cpu
build_docker gpu
