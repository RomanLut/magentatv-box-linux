#!/bin/bash
# Install the X11 package set on the box from the debs shipped in /srv/mrg5-x11.
#
# The box has no route off its own /24 (no default gateway, no DNS), so it cannot
# use the Debian mirrors: this uses a file:// apt source built from the bundle.
# Packages already installed are listed in /root/mrg5-already-installed.txt and
# are covered by the real dpkg state.
set -euo pipefail

REPO=/srv/mrg5-x11
LIST=/etc/apt/sources.list.d/mrg5-local.list

PKGS="xserver-xorg-core xserver-xorg-video-fbdev xserver-xorg-input-libinput xinit xterm twm"

echo "== 1. apt: drop the unreachable network sources, add the local repo =="
cat > "$LIST" <<EOF
deb [trusted=yes] file:$REPO ./
EOF
cat "$LIST"

echo "== 2. packages already installed (excluded from the install set) =="
INSTALLED=""
if [ -f /root/mrg5-already-installed.txt ]; then
  # keep only names that actually are installed, as a safety net
  INSTALLED=$(while read -r p; do
      dpkg-query -W -f='${Status}\n' "$p" 2>/dev/null | grep -q 'install ok installed' && echo "$p"
    done < /root/mrg5-already-installed.txt | tr '\n' ' ')
fi
echo "already installed: ${INSTALLED:-none}"

echo "== 3. install =="
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
  -y --no-install-recommends install $PKGS $INSTALLED

echo "== 4. result =="
for p in $PKGS; do
  v=$(dpkg-query -W -f='${Version}' "$p" 2>/dev/null || echo MISSING)
  echo "$p $v"
done
ls -l /usr/bin/Xorg /usr/bin/startx /usr/bin/xinit /usr/bin/xterm /usr/bin/twm 2>&1
echo "INSTALL_DONE"
