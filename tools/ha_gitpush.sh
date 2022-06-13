#!/bin/bash
cd /config
git config core.sshCommand 'ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -i /config/.ssh/id_rsa -F /dev/null'
git add .
git commit -m "$@"
git status
git push -u origin HEAD
sleep 7s
exit
