#!/bin/bash

# We pass https_proxy from host to container by default. However, if host doesn't have proxy set, then https_proxy
# is set to an empty string in the container. This causes grpc to raise annoying (but benign) errors whenever it's
# run, namely through Scanner. This script unsets those variables if they are set to a blank string to avoid this.

# Also, note that this script MUST be run in the form:
#   $ . ./scripts/clear-proxy
# i.e. with the dot in front, as this ensures that the unset clears variables in the caller's shell, not in just
# this the context of this script.

if [ -z "$https_proxy" ]; then
   unset https_proxy;
   unset http_proxy;
fi
