#!/bin/bash
curl https://sh.rustup.rs -sSf | sh -s -- -y --default-toolchain nightly
source /root/.cargo/env
rustup default nightly
