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
    # keras_*: https://github.com/bazelbuild/continuous-integration/issues/305
    pip3 install six numpy wheel keras_applications keras_preprocessing

    git clone -b v${tf_version} https://github.com/tensorflow/tensorflow/
    cd tensorflow
    updatedb

    if [ "$device" = "cpu" ]; then
        # TODO(wcrichto): getting internal errors w/ MKL on GCE

        PYTHON_BIN_PATH=$(which python3) \
                       PYTHON_LIB_PATH=/usr/local/lib/python3.5/dist-packages \
                       TF_NEED_MKL=0 \
                       CC_OPT_FLAGS=-march=core-avx2 \
                       TF_NEED_GCP=0 \
                       TF_NEED_S3=0 \
                       TF_NEED_GDR=0 \
                       TF_NEED_MPI=0 \
                       TF_NEED_HDFS=0 \
                       TF_ENABLE_XLA=0 \
                       TF_NEED_VERBS=0 \
                       TF_NEED_OPENCL=0 \
                       TF_NEED_CUDA=0 \
                       TF_NEED_IGNITE=0 \
                       TF_NEED_OPENCL_SYCL=0 \
                       TF_NEED_ROCM=0 \
                       TF_DOWNLOAD_CLANG=0 \
                       TF_SET_ANDROID_WORKSPACE=0 \
                       ./configure

        # ares: https://github.com/tensorflow/tensorflow/issues/23402#issuecomment-436932197
        bazel build \
              --config=opt \
              --define=grpc_no_ares=true \
              --incompatible_remove_native_http_archive=false \
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
