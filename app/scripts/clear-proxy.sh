#!/bin/bash

if [ -z "$https_proxy" ]; then
   unset https_proxy;
   unset http_proxy;
fi
