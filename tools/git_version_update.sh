#!/bin/bash
cd /config
git add .HA_VERSION
git commit -m "$@"
sleep 2s
git status
git push -u origin master
sleep 1s
git tag -a "$@"
sleep 7s
exit