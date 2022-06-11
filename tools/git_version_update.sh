#!/bin/bash
cd /config
git add .HA_VERSION
git commit -m "$@"
sleep 5s
git push -u origin master

exit