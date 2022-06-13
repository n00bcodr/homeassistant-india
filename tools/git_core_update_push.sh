#!/bin/bash
cd /config
git config core.sshCommand 'ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -i /config/.ssh/id_rsa -F /dev/null'
git add .HA_VERSION
git commit -m "$@"
git push -u origin master
git tag -a "$@"
exit