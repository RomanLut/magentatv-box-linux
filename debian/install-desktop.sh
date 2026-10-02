#!/bin/bash
# Merge the Xfce bundle into the local (offline) apt repository on the box and
# install the desktop.
#
#   bash /root/install-desktop.sh
#
# The box has no route off its own /24, so everything comes from the file://
# repository in /srv/mrg5-x11 (built from work/desktop/bundle* in WSL).
# dpkg-scanpackages is not installed on the box, so the index shipped with the
# Xfce bundle is appended to the existing one; duplicate entries are harmless.
set -euo pipefail

REPO=/srv/mrg5-x11
LIST=/etc/apt/sources.list.d/mrg5-local.list
PKGS="xfce4 xfce4-terminal xfwm4 xfce4-panel xfdesktop4 xfce4-session \
xfce4-settings xfconf thunar mousepad xfce4-taskmanager dbus-x11"

if [ -f /tmp/xfce-Packages ]; then
    echo "== merging the Xfce packages into $REPO/debs =="
    mkdir -p "$REPO/debs" /root/xfce-debs
    if [ -d /root/xfce-debs ] && [ "$(ls /root/xfce-debs | wc -l)" -gt 0 ]; then
        cp -n /root/xfce-debs/*.deb "$REPO/debs/" 2>/dev/null || true
    fi
    echo "   debs now: $(ls "$REPO/debs" | wc -l)"
    if ! grep -q "^Package: xfce4-session$" "$REPO/Packages" 2>/dev/null; then
        cat /tmp/xfce-Packages >> "$REPO/Packages"
        gzip -9 -kf "$REPO/Packages"
    fi
    echo "   entries in index: $(grep -c '^Package:' "$REPO/Packages")"
fi

echo "== install =="
DEBIAN_FRONTEND=noninteractive apt-get \
    -o Dir::Etc::sourcelist="$LIST" \
    -o Dir::Etc::sourceparts=/dev/null \
    -o APT::Get::List-Cleanup=0 \
    -o Acquire::Retries=0 \
    -o APT::Sandbox::User=root \
    update

DEBIAN_FRONTEND=noninteractive apt-get \
    -o Dir::Etc::sourcelist="$LIST" \
    -o Dir::Etc::sourceparts=/dev/null \
    -o APT::Sandbox::User=root \
    -y --no-install-recommends install $PKGS

echo "== result =="
for p in $PKGS; do
    v=$(dpkg-query -W -f='${Version}' "$p" 2>/dev/null || echo MISSING)
    printf '  %-22s %s\n' "$p" "$v"
done
ls -l /usr/bin/xfce4-session 2>&1
echo DESKTOP_INSTALL_DONE
