#!/bin/bash
# Install CasaOS (with Docker) and PiGallery2 on the MRG5 Debian system.
# Run from Git Bash on the PC once the box has booted Debian from MRG5ROOT.
#
#   work/nas/install-casaos.sh <box-ip>
#
# CasaOS web UI: http://<box-ip>/        PiGallery2: http://<box-ip>:8088/
# Photos go in /DATA/Gallery/Pictures (visible in CasaOS Files and its Samba share).
set -euo pipefail

BOX=${1:?box ip}
HERE=$(cd "$(dirname "$0")" && pwd)
KEY=$HERE/../mrg5-test_ssh_ed25519
SSH="ssh -i $KEY -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@$BOX"

echo "== system"
$SSH 'uname -a; grep -E "MemTotal|SwapTotal" /proc/meminfo; df -h /; systemctl is-system-running || true'

echo "== CasaOS (installs Docker)"
$SSH 'curl -fsSL https://get.casaos.io | bash'

echo "== PiGallery2"
$SSH 'mkdir -p /DATA/Gallery/Pictures /DATA/AppData/pigallery2 &&
      docker compose -f /mrg5/pigallery2-compose.yaml up -d &&
      docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"'
