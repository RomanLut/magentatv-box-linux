#!/bin/sh
# Set up Chromium as the user "browser" on the root desktop (checks/53): Raspberry
# Pi's Chromium build (unpacked under /opt/rpi-chromium) in GPU mode, the box's
# default browser. Run on the box as root with Chromium closed; copy
# chromium-as-browser, chromium-single, chromium and chromium.desktop from
# work/chromium/ to /root first.
#
#   sh setup-browser-user.sh          user, launchers, menu entry, default browser
set -eu
U=browser
id $U > /dev/null 2>&1 || useradd -m -U -s /usr/sbin/nologin \
	-c "Chromium on the desktop (checks/53)" -G pulse-access,audio,video,render $U
# lingering: logind keeps /run/user/<uid> and the user's D-Bus session
loginctl enable-linger $U
install -m 0755 /root/chromium-as-browser /usr/local/bin/chromium-as-browser
install -m 0755 /root/chromium-single /usr/local/bin/chromium-single
install -m 0755 /root/chromium /usr/local/bin/chromium
ln -sf chromium /usr/local/bin/chromium-browser
install -D -m 0644 /root/chromium.desktop /usr/local/share/applications/chromium.desktop
for s in /opt/rpi-chromium/usr/share/icons/hicolor/*/apps/chromium.png; do
	install -D -m 0644 "$s" \
		"/usr/local/share/icons/hicolor/$(basename "$(dirname "$(dirname "$s")")")/apps/chromium.png"
done
# the default browser for x-www-browser, Xfce (exo) and xdg-open
update-alternatives --install /usr/bin/x-www-browser x-www-browser /usr/local/bin/chromium 250
update-alternatives --set x-www-browser /usr/local/bin/chromium
mkdir -p /root/.config/xfce4
if grep -q '^WebBrowser=' /root/.config/xfce4/helpers.rc 2>/dev/null; then
	sed -i 's/^WebBrowser=.*/WebBrowser=chromium/' /root/.config/xfce4/helpers.rc
else
	echo "WebBrowser=chromium" >> /root/.config/xfce4/helpers.rc
fi
xdg-settings set default-web-browser chromium.desktop 2> /dev/null || true
# the profile: Debian Chromium's (moved from root earlier) is copied once for
# the newer Raspberry Pi build, the original kept
P=/home/$U/.config
if [ -d $P/chromium ] && [ ! -d $P/chromium-rpi ]; then
	cp -a $P/chromium $P/chromium-rpi
	rm -f $P/chromium-rpi/Singleton*
fi
mkdir -p /home/$U/Downloads $P
chown -R $U:$U /home/$U/Downloads $P
id $U
ls -ld /run/user/$(id -u $U)
