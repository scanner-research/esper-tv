#!/bin/bash

pushd /app
cargo install protobuf-codegen -q || true
protoc --python_out=esper --rust_out=subserver/src -I=.deps datatypes.proto
popd
