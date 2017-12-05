#!/bin/bash
set -e

gsutil mv app/example-dataset.tar.gz gs://esper/
gsutil acl ch -u AllUsers:R gs://esper/example-dataset.tar.gz
