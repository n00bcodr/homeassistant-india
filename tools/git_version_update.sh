#!/bin/bash

cd /config

git add .HA_VERSION -f
git status
git commit -m "$@"

exit