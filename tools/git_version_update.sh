#!/bin/bash

cd /config

git add .HA_VERSION
git commit -m "$@"
git push -u origin master

exit
