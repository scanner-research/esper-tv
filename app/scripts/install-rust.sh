#!/bin/bash
curl https://sh.rustup.rs -sSf | sh -s -- -y --default-toolchain nightly
rustup default nightly
