#!/bin/sh
# install.sh (checks/41, "Games and emulators"): run on the box from a copy of work/luanti after
# build-luanti.sh. Installs the luanti-tv start command, the desktop icon and the launcher tile.
set -e
cd "$(dirname "$0")"
install -m 755 luanti-tv /usr/local/bin/luanti-tv
install -m 755 luanti.desktop /root/Desktop/luanti.desktop
T=/etc/mrg5-launcher/tiles.xml
if ! grep -q 'luanti-tv' "$T"; then
	cp "$T" "$T.bak-luanti"
	sed -i 's|^</launcher>|  <tile title="Luanti"       icon="/usr/local/share/icons/hicolor/scalable/apps/luanti.svg" color="#2f6b3a"\n        exec="/usr/local/bin/luanti-tv"/>\n</launcher>|' "$T"
fi
echo "installed; the tile appears after: systemctl restart mrg5-launcher"
