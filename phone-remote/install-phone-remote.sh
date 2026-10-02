#!/bin/sh
# install-phone-remote.sh (checks/41, "Phone remote"): the phone remote on a box. Run as root from
# this folder, with the binary from build-remote-touchpad.sh copied beside this script as
# remote-touchpad (or already in /usr/local/bin). Safe to run again. The QR code in the launcher's
# settings needs the launcher's Main.qml/launcher.py from 2026-10-04 (work/launcher/install.sh).
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
# remote-touchpad v1.5.5 (commit d7cd061), Go 1.26.8, -tags x11, built in mrg5-cores-bookworm
SHA=123bde9d61e6ced2a2bab90a2def42ae57b4773cbb6c5aa6277d4fe1d6b63276

DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3-qrcode libxtst6 libxrandr2 >/dev/null
if [ -f "$HERE/remote-touchpad" ]; then
    install -m 755 "$HERE/remote-touchpad" /usr/local/bin/remote-touchpad
fi
[ -x /usr/local/bin/remote-touchpad ] || { echo "no remote-touchpad: build it with build-remote-touchpad.sh"; exit 1; }
echo "$SHA  /usr/local/bin/remote-touchpad" | sha256sum -c --quiet ||
    echo "note: remote-touchpad is not the build recorded here (checks/41)"
install -m 755 "$HERE/mrg5-phone-remote" /usr/local/bin/mrg5-phone-remote
install -m 644 "$HERE/mrg5-phone-remote.service" /etc/systemd/system/mrg5-phone-remote.service
systemctl daemon-reload
systemctl enable mrg5-phone-remote >/dev/null 2>&1
systemctl restart mrg5-phone-remote
sleep 2
echo "mrg5-phone-remote: $(systemctl is-active mrg5-phone-remote)"
