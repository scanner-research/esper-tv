#!/bin/bash
set -e

if [ "$build_tf" = "on" ]; then
    # Install bazel
    apt-get update && apt-get install -y openjdk-8-jdk mlocate
    echo "deb [arch=amd64] http://storage.googleapis.com/bazel-apt stable jdk1.8" | \
        tee /etc/apt/sources.list.d/bazel.list
    curl https://bazel.build/bazel-release.pub.gpg | apt-key add -
    apt-get update && apt-get install -y bazel

    # Install python deps
    pip3 install six numpy wheel

    git clone -b v${tf_version} https://github.com/tensorflow/tensorflow/
    cd tensorflow
    updatedb

    if [ "$device2" = "cpu" ]; then
        # TODO(wcrichto): getting internal errors w/ MKL on GCE

        PYTHON_BIN_PATH=$(which python3) \
                       PYTHON_LIB_PATH=/usr/local/lib/python3.5/site-packages \
                       TF_NEED_MKL=0 \
                       CC_OPT_FLAGS=-march=core-avx2 \
                       TF_NEED_JEMALLOC=1 \
                       TF_NEED_GCP=0 \
                       TF_NEED_S3=0 \
                       TF_NEED_GDR=0 \
                       TF_NEED_MPI=0 \
                       TF_NEED_HDFS=0 \
                       TF_ENABLE_XLA=0 \
                       TF_NEED_VERBS=0 \
                       TF_NEED_OPENCL=0 \
                       TF_NEED_CUDA=0 \
                       ./configure

        bazel build \
              --config=opt \
              --incompatible_load_argument_is_label=false \
              //tensorflow/tools/pip_package:build_pip_package
    else
        echo "No GPU TF support yet"
        exit 1
    fi

    bazel-bin/tensorflow/tools/pip_package/build_pip_package /tmp/tensorflow_pkg
    pip3 install /tmp/tensorflow_pkg/*
    cd ..
    rm -rf tensorflow

else
    if [ "$device" = "cpu" ]; then
        pip3 install tensorflow==${tf_version};
    else
        pip3 install tensorflow-gpu==${tf_version};
    fi
fi
