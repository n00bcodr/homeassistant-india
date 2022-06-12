#!/bin/bash
cd /config
git add .
git commit -m "$@"
sleep 2s
git status
git push -u origin master
sleep 7s
