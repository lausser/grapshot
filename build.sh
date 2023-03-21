#! /bin/bash
set -ex
shopt -s expand_aliases
if [ -z "$(which podman 2>/dev/null)" ]; then
  alias podman="docker"
elif [ -z "$(which docker 2>/dev/null)" ]; then
  alias docker="podman"
fi
USERNAME=lausser
IMAGE=grapshot
podman build -t $USERNAME/$IMAGE:latest .
