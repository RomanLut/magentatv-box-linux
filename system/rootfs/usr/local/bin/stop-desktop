#!/bin/bash
# Stop the hand-started X/Xfce session and give tty1 back to the framebuffer
# console.
set -u
LOG=/var/log/mrg5-desktop.log     # as start-desktop.sh
say() { echo "$@" | tee -a "$LOG"; }

say "== stop-desktop $(date -Is) =="
for p in $(pgrep -f 'xfce4-session' 2>/dev/null); do kill "$p" 2>/dev/null; done
sleep 2
for p in $(pgrep -f 'Xorg .0' 2>/dev/null); do kill "$p" 2>/dev/null; done
sleep 2
for p in $(pgrep -x xinit 2>/dev/null); do kill "$p" 2>/dev/null; done
# leftovers of the session, harmless but untidy
for name in xfwm4 xfdesktop xfce4-panel xfsettingsd xfconfd xterm twm thunar; do
    for p in $(pgrep -x "$name" 2>/dev/null); do kill "$p" 2>/dev/null; done
done
sleep 1

say "== start the console again =="
systemctl start getty@tty1 2>/dev/null || true
systemctl is-active getty@tty1 | tee -a "$LOG"

say "remaining X processes: $(pgrep -c -f 'Xorg .0' 2>/dev/null || echo 0)"
