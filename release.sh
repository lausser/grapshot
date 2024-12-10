#! /bin/bash
set -ex
shopt -s expand_aliases
USERNAME=lausser
IMAGE=grapshot
if [ -z "$(which podman 2>/dev/null)" ]; then
  alias podman="docker"
  OPTS=""
elif [ -z "$(which docker 2>/dev/null)" ]; then
  alias docker="podman"
  OPTS="--security-opt label=disable"
fi
git pull
# bump version
docker run --rm $OPTS -v "$PWD":/app docker.io/treeder/bump patch
version=`cat VERSION`
echo "version: $version"
# run build
./build.sh
# tag it
##git add -A # dont add everything without an explicit approval
##git commit -m "version $version"
git commit -a -m "version $version"
git tag -a "$version" -m "version $version"
git push
git push --tags
docker tag $USERNAME/$IMAGE:latest $USERNAME/$IMAGE:$version
# push it
docker push ghcr.io/$USERNAME/$IMAGE:latest
docker push ghcr.io/$USERNAME/$IMAGE:$version
