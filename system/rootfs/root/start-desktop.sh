#!/bin/bash
# Start the Xfce desktop on the MRG5's HDMI output.
#
#   /root/start-desktop.sh          # start it (needs the Xfce packages)
#   /root/stop-desktop.sh           # stop it and give tty1 back to the console
#
# The TV launcher (mrg5-launcher.service) is what starts at boot; its "XFCE Desktop" tile
# starts mrg5-desktop.service, which runs this. It is also the manual start (the `start`
# word at the admin console, start-desktop over SSH). X runs on tty1 (the
# framebuffer console is stopped for the session) with the X config that
# desktop-accel.sh selected (checks/41, "Desktop").
set -u
# in /var/log: a RAM disk on the release and USB systems, so the session's steady stream of
# warnings does not wear the flash (checks/54, eMMC writes)
LOG=/var/log/mrg5-desktop.log
say() { echo "$@" | tee -a "$LOG"; }

: > "$LOG"
say "== start-desktop $(date -Is) =="

if ! [ -x /usr/bin/xfce4-session ]; then
    say "ERROR: xfce4-session is not installed; install the xfce bundle first"
    exit 1
fi

# an already running session: refuse to start a second one
if pgrep -f 'Xorg :0' >/dev/null 2>&1; then
    say "X is already running on :0"
    exit 0
fi

say "== stop the framebuffer console on tty1 =="
systemctl stop getty@tty1 2>/dev/null || true

export XDG_RUNTIME_DIR=/run/user/0
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

# a session bus is required by most Xfce components; if systemd already provides
# one, reuse it
if [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
    if [ -S /run/user/0/bus ]; then
        export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/0/bus"
    else
        eval "$(dbus-launch --sh-syntax 2>/dev/null)" || true
    fi
fi
say "  DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS:-<none>}"

say "== start X and the Xfce session =="
cd /root
# the getty is started again as soon as xinit returns, so logging out of the
# desktop gives the console login back without stop-desktop
setsid nohup bash -c \
    'xinit /etc/X11/xinit/xinitrc.xfce -- /usr/bin/Xorg :0 vt1 -nolisten tcp;
     systemctl start getty@tty1' \
    >>"$LOG" 2>&1 </dev/null &

for i in $(seq 1 30); do
    sleep 1
    pgrep -f 'Xorg :0' >/dev/null && break
done
sleep 8

say "== processes =="
ps -eo pid,%cpu,%mem,rss,etime,comm --sort=-rss | head -n 15 | tee -a "$LOG"

say "== X clients =="
DISPLAY=:0 xlsclients 2>/dev/null | head -n 10 | tee -a "$LOG"

say "== input devices seen by X =="
if [ -r /var/log/Xorg.0.log ]; then
    grep -E "libinput|Adding (input|extended)|No input driver|event[0-9]" /var/log/Xorg.0.log |
        tail -n 12 | tee -a "$LOG"
fi
ls -l /dev/input/ 2>&1 | tee -a "$LOG"

say "== resource use =="
free -m | tee -a "$LOG"

say "== done; /root/stop-desktop.sh stops it =="
