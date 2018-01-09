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
    pip install six numpy wheel

    git clone -b v${tf_version} https://github.com/tensorflow/tensorflow/
    cd tensorflow
    updatedb

    if [ "$device2" = "cpu" ]; then
       PYTHON_BIN_PATH=$(which python) \
                      PYTHON_LIB_PATH=/usr/local/lib/python2.7/site-packages \
                      TF_NEED_MKL=1 \
                      TF_DOWNLOAD_MKL=1 \
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
             --config=mkl \
             --incompatible_load_argument_is_label=false \
             //tensorflow/tools/pip_package:build_pip_package
    else
        echo "No GPU TF support yet"
        exit
    fi

    bazel-bin/tensorflow/tools/pip_package/build_pip_package /tmp/tensorflow_pkg
    pip install /tmp/tensorflow_pkg/*
    cd ..
    rm -rf tensorflow

else
    if [ "$device2" = "cpu" ]; then
        pip install tensorflow==${tf_version};
    else
        pip install tensorflow-gpu==${tf_version};
    fi
fi
