#!/bin/bash
cd /config
git config core.sshCommand 'ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -i /config/.ssh/id_rsa -F /dev/null'
git add .HA_VERSION -f
git commit -m "Core Version Update to $@"
git push -u origin master
git tag -a "$@" -m "Core Version Update to $@"
git push origin "$@"
exit