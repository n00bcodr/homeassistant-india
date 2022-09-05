#!/bin/bash
cd /config
git config core.sshCommand 'ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -i /config/.ssh/id_rsa -F /dev/null'
ver=$(<.HA_VERSION)
git add .HA_VERSION -f
git commit -m "📦⬆ Core Version Update to $ver"
git push -u origin master
git tag -a "$ver" -m "📦⬆ Core Version Update to $ver"
git push origin "$ver"
exit