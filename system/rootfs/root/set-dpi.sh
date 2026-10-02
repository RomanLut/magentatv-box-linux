#!/bin/bash
# Make desktop text legible on the 1080i panel.
#
#   bash /root/set-dpi.sh [dpi]      dpi default 144, "-1" restores automatic
#
# Why: the desktop icon labels and window titles render at ~9 px, and the panel's
# 1080i output smears thin lines (checks/39), so they look faint on a TV even
# though the framebuffer capture measures about 7:1 contrast.  Raising the DPI
# makes the glyphs thicker, which interlaced output survives.
#
# Sets the Xft DPI in the xsettings channel (GTK font scaling) and raises the
# explicitly pinned font sizes, then restarts the session so xfsettingsd applies
# them - the window manager and xfdesktop read the DPI through the xsettings
# daemon, which only runs when the session starts.
#
# Revert:  bash /root/set-dpi.sh -1
set -u
DPI=${1:-144}
export DISPLAY=:0
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/0/bus

echo "== before =="
xfconf-query -c xsettings -p /Xft/DPI 2>&1
xfconf-query -c xsettings -p /Gtk/FontName 2>&1
xfconf-query -c xfwm4 -p /general/title_font 2>&1

if [ "$DPI" = "-1" ]; then
    echo "== restore automatic DPI =="
    xfconf-query -c xsettings -p /Xft/DPI -r 2>/dev/null || true
    xfconf-query -c xsettings -p /Gtk/FontName -s "Sans 10" 2>&1
    xfconf-query -c xfwm4 -p /general/title_font -s "Sans Bold 9" 2>&1
else
    echo "== set Xft/DPI=$DPI and larger base fonts =="
    xfconf-query -c xsettings -p /Xft/DPI -n -t int -s "$DPI" 2>&1 || \
        xfconf-query -c xsettings -p /Xft/DPI -s "$DPI" 2>&1
    xfconf-query -c xsettings -p /Gtk/FontName -s "Sans 11" 2>&1
    xfconf-query -c xfwm4 -p /general/title_font -s "Sans Bold 11" 2>&1
fi

echo "== after =="
xfconf-query -c xsettings -p /Xft/DPI 2>&1
xfconf-query -c xsettings -p /Gtk/FontName 2>&1
xfconf-query -c xfwm4 -p /general/title_font 2>&1

echo "== restart the session so xfsettingsd applies it =="
bash /root/stop-desktop.sh >/dev/null 2>&1
sleep 3
bash /root/start-desktop.sh >/root/r3-restart.log 2>&1
sleep 6
pgrep -a xfsettingsd | head -n 2
echo "  Xorg processes: $(pgrep -c -f 'Xorg .0')"
echo "  done"

