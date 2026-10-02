#!/bin/sh
# install-dlna.sh (checks/41, "DLNA and Spotify"): the DLNA receiver "MRG5 TV", Spotify Connect
# "MRG5 TV", AirPlay "MRG5 TV" and the DLNA media server "MRG5 Media" on a box. Run as root from this folder; it is
# safe to run again. Pinned versions, each download checked against its SHA-256:
#   Macast 0.65.post1 (xfangfang/Macast, GPL-3.0, PyPI) in /opt/macast, with pystray 0.19.5
#   (LGPL-3.0) because Macast imports its tray code even in its command-line mode, and our patch
#   for sharing UDP 1900 with minidlna; its other modules come from Debian
#   raspotify 0.48.3 = librespot v0.8.0 (MIT), the armhf package from dtcooper/raspotify
#   minidlna and shairport-sync (AirPlay) from Debian
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=/root/src/dlna
MACAST=macast-0.65.post1.tar.gz;  MACAST_SHA=c13fe8b9d9c3893cf97d1bfd800bbadc8cc178f92f1c01209022a9a53c75d1b3
PYSTRAY=pystray-0.19.5-py2.py3-none-any.whl; PYSTRAY_SHA=a0c2229d02cf87207297c22d86ffc57c86c227517b038c0d3c59df79295ac617
RASPOTIFY=raspotify_0.48.3.librespot.v0.8.0-939dc5e_armhf.deb; RASPOTIFY_SHA=538a4dc511aa4ba79d88a24708484c21ba5ee4abff8baa25e5a2cc40d79b8f95
RASPOTIFY_URL=https://github.com/dtcooper/raspotify/releases/download/0.48.3/$RASPOTIFY

fetch() { # <file> <sha256> <url>
    [ -f "$SRC/$1" ] || curl -fsSL -o "$SRC/$1" "$3"
    echo "$2  $SRC/$1" | sha256sum -c --quiet || { echo "checksum mismatch: $1"; exit 1; }
}
mkdir -p "$SRC"

echo "== packages"
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    minidlna python3-venv python3-cherrypy3 python3-lxml python3-netifaces python3-appdirs \
    python3-pyperclip python3-pil python3-six patch >/dev/null

echo "== Spotify Connect (raspotify)"
fetch "$RASPOTIFY" "$RASPOTIFY_SHA" "$RASPOTIFY_URL"
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$SRC/$RASPOTIFY" >/dev/null
if ! grep -q '^LIBRESPOT_BACKEND="pulseaudio"' /etc/raspotify/conf; then
    cat >> /etc/raspotify/conf <<'EOF'

# MagentaTV Box Linux (checks/41, "DLNA and Spotify"): the name and icon in Spotify's device list,
# and sound through the system-wide PulseAudio, which holds the HDMI sound card (ALSA direct
# cannot open it while PulseAudio runs)
LIBRESPOT_NAME="MRG5 TV"
LIBRESPOT_DEVICE_TYPE="tv"
LIBRESPOT_BACKEND="pulseaudio"
PULSE_SERVER="unix:/var/run/pulse/native"
EOF
fi
systemctl enable raspotify >/dev/null 2>&1; systemctl restart raspotify

echo "== AirPlay (shairport-sync)"
# Debian's 3.3.8: classic AirPlay (audio) from iPhone, iPad, Mac; output into PulseAudio
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends shairport-sync >/dev/null
C=/etc/shairport-sync.conf
[ -f $C.debian ] || cp $C $C.debian
sed -i 's|^//\tname = "%H";|\tname = "MRG5 TV"; // MagentaTV Box Linux (checks/41, "DLNA and Spotify")|
        s|^//\toutput_backend = "alsa";|\toutput_backend = "pa"; // the system-wide PulseAudio holds the HDMI card|
        s|^//\tserver = "host";|\tserver = "unix:/var/run/pulse/native";|
        s|^//\tapplication_name = "Shairport Sync";|\tapplication_name = "AirPlay";|' $C
usermod -aG pulse-access shairport-sync
systemctl enable shairport-sync >/dev/null 2>&1; systemctl restart shairport-sync

echo "== DLNA receiver (Macast)"
fetch "$MACAST" "$MACAST_SHA" "https://files.pythonhosted.org/packages/source/m/macast/$MACAST"
fetch "$PYSTRAY" "$PYSTRAY_SHA" "https://files.pythonhosted.org/packages/py2.py3/p/pystray/$PYSTRAY"
[ -x /opt/macast/bin/python3 ] || python3 -m venv --system-site-packages /opt/macast
/opt/macast/bin/pip install -q --no-deps --no-build-isolation "$SRC/$MACAST" "$SRC/$PYSTRAY" 2>&1 |
    grep -v DEPRECATION || true
SP=$(echo /opt/macast/lib/python3*/site-packages)
grep -q 'MagentaTV Box Linux: minidlna on the same box' "$SP/macast/ssdp.py" ||
    patch -s -p1 -d "$SP" < "$HERE/macast-0.65.post1-reuseaddr.patch"
install -m 755 "$HERE/mrg5-dlna-receiver" /usr/local/bin/mrg5-dlna-receiver
install -m 644 "$HERE/mrg5-dlna-receiver.service" /etc/systemd/system/mrg5-dlna-receiver.service
systemctl daemon-reload
systemctl enable mrg5-dlna-receiver >/dev/null 2>&1; systemctl restart mrg5-dlna-receiver

echo "== DLNA media server (minidlna)"
C=/etc/minidlna.conf
[ -f $C.debian ] || cp $C $C.debian
if grep -q '^media_dir=/var/lib/minidlna$' $C; then
    sed -i 's|^media_dir=/var/lib/minidlna$|# the data folder (checks/41, "DLNA and Spotify"): films, music and TV in Media, photos in Gallery\nmedia_dir=/DATA/Media\nmedia_dir=P,/DATA/Gallery\nmedia_dir=/DATA/Downloads|' $C
fi
sed -i 's|^#friendly_name=.*|friendly_name=MRG5 Media|; s|^#inotify=yes|inotify=yes|' $C
# EMMC Only has no shared folders (checks/54): the media server stays off there
if grep -q '^edition=emmc$' /etc/mrg5-release 2>/dev/null; then
    systemctl disable --now minidlna >/dev/null 2>&1 || true
else
    systemctl enable minidlna >/dev/null 2>&1; systemctl restart minidlna
fi

sleep 5
for s in raspotify shairport-sync mrg5-dlna-receiver minidlna; do echo "$s: $(systemctl is-active $s)"; done
