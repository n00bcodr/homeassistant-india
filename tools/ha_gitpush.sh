#!/bin/bash
cd /config
git add .
git commit -m "$@"
sleep 5s
git push -u origin master

exit