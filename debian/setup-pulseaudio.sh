#!/bin/bash
# Give the desktop a working volume indicator.
#
# The Xfce panel applet is xfce4-pulseaudio-plugin: it talks to PulseAudio and to nothing else, so
# with no daemon running it shows a crossed-out icon.  That cross meant "no sound server here", not
# "muted" - applications were playing by opening the ALSA PCM directly, which bypasses the applet
# entirely.
#
# PulseAudio refuses to run as root, and this box's desktop session IS root, so it is run in system
# mode - the configuration intended for appliances with a single seat.  That also settles two other
# things: Firefox gets a native PulseAudio sink instead of the apulse shim, and several
# applications can mix, which dmix would not do on this card.
set -u
cd /mnt/d/Github/MagentaTVBox || exit 1
K=/tmp/k
[ -f "$K" ] || { cp work/mrg5-test_ssh_ed25519 "$K"; chmod 600 "$K"; }
H=192.168.3.60
OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes -o ConnectTimeout=8 -o LogLevel=ERROR"

cat > /tmp/pa.sh <<'EOF'
set -e
export DEBIAN_FRONTEND=noninteractive
command -v pulseaudio >/dev/null || apt-get install -y -qq pulseaudio 2>&1 | tail -4

# system mode: the daemon runs as the `pulse` user; clients need to be in pulse-access
adduser root pulse-access >/dev/null 2>&1 || true
adduser pulse audio >/dev/null 2>&1 || true

cat > /etc/pulse/system.pa <<'PA'
#!/usr/bin/pulseaudio -nF
# System-mode configuration for the MRG5 box: one card, one sink, no autodetection games.
load-module module-native-protocol-unix auth-anonymous=1
# keep the sink's volume and mute across restarts and reboots (the remote's volume keys set
# them); loaded before the sink so it is restored as the sink appears, as default.pa does
load-module module-device-restore
# 4 x 2048 bytes = 43 ms of sink buffer (the driver adds 21 ms in its ring); 4 x 8192 made 170 ms
load-module module-alsa-sink device=hw:MRG5HDMI,0 sink_name=mrg5_hdmi rate=48000 channels=2 format=s16le tsched=0 fragments=4 fragment_size=2048
load-module module-always-sink
load-module module-suspend-on-idle timeout=0
set-default-sink mrg5_hdmi
# Bluetooth audio (headphones, speakers): registers the A2DP/HFP endpoints with BlueZ, as
# Debian's default.pa does; without them BlueZ refuses to connect any audio device
# (br-connection-profile-unavailable). A connected one becomes the default sink and the
# streams move to it; when it goes, they fall back to the TV.
.ifexists module-bluetooth-policy.so
load-module module-bluetooth-policy
.endif
.ifexists module-bluetooth-discover.so
load-module module-bluetooth-discover
.endif
load-module module-switch-on-connect
PA

cat > /etc/systemd/system/pulseaudio.service <<'UNIT'
[Unit]
Description=PulseAudio system-wide sound server (MRG5)
After=sound.target

[Service]
Type=notify
ExecStart=/usr/bin/pulseaudio --system --disallow-exit --disallow-module-loading=false --log-target=journal
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

# clients find the system daemon through this (Debian's file has both keys commented out)
mkdir -p /etc/pulse
grep -q '^default-server' /etc/pulse/client.conf 2>/dev/null || \
	printf 'default-server = unix:/var/run/pulse/native\nautospawn = no\n' >> /etc/pulse/client.conf

# No per-user daemons: Debian enables pulseaudio.service/.socket for every user, so the first
# session of any user (Chromium's `browser` at boot) started one, which took BlueZ's HSP/HFP
# profiles before the system daemon ("RegisterProfile() failed: UUID already registered"),
# then quit and released them: Bluetooth headphones could not connect after a reboot.
systemctl --global mask pulseaudio.service pulseaudio.socket

systemctl daemon-reload
systemctl enable pulseaudio.service >/dev/null 2>&1
systemctl restart pulseaudio.service
sleep 6
systemctl --no-pager -l status pulseaudio.service 2>&1 | head -12
EOF

timeout 900 ssh -i "$K" $OPTS root@"$H" 'bash -s' < /tmp/pa.sh 2>&1

echo
echo "=== does PulseAudio see the card? ==="
timeout 180 ssh -i "$K" $OPTS root@"$H" '
export PULSE_SERVER=unix:/var/run/pulse/native
pactl info 2>&1 | head -8
echo "--- sinks ---"
pactl list short sinks 2>&1
' 2>&1
