#! /bin/bash
set -ex
shopt -s expand_aliases
if [ -z "$(which podman)" ]; then
  alias podman="docker"
fi
USERNAME=lausser
IMAGE=grapshot
podman build -t $USERNAME/$IMAGE:latest .
