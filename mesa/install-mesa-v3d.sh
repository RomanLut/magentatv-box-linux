#!/bin/sh
# Install the patched Mesa megadriver (build-mesa-v3d.sh) as v3d_dri.so and
# mrg5_dri.so, or put Debian's back with "restore".
#
# The installed *_dri.so names are hardlinks of one megadriver, so each name is
# removed first and the new file copied in: writing through the link would
# replace every other driver name too.  A libgl1-mesa-dri upgrade would
# overwrite both names, and the driver is built against this exact Mesa, so
# "install" puts every installed package of the mesa source on hold (apt and
# GNOME Software then skip their updates) and "restore" releases them
# (checks/53).
set -eu
D=/usr/lib/arm-linux-gnueabihf/dri
W=/root/mesa-v3d
KEEP=$W/v3d_dri.so.debian
P=$(dpkg-query -W -f='${Package} ${source:Package}\n' | awk '$2 == "mesa" {print $1}')

case "${1:-install}" in
install)
	[ -f "$W/v3d_dri.so" ] || { echo "no $W/v3d_dri.so - build first"; exit 1; }
	[ -f "$KEEP" ] || cp "$D/v3d_dri.so" "$KEEP"
	for n in v3d mrg5; do
		rm -f "$D/${n}_dri.so"
		install -m 0644 "$W/v3d_dri.so" "$D/${n}_dri.so"
	done
	apt-mark hold $P > /dev/null
	;;
restore)
	[ -f "$KEEP" ] || { echo "no saved Debian driver at $KEEP"; exit 1; }
	rm -f "$D/v3d_dri.so" "$D/mrg5_dri.so"
	install -m 0644 "$KEEP" "$D/v3d_dri.so"
	apt-mark unhold $P > /dev/null
	;;
*)
	echo "usage: $0 [install|restore]"; exit 1 ;;
esac

sha256sum "$D/v3d_dri.so" "$D/kms_swrast_dri.so"
[ -f "$D/mrg5_dri.so" ] && sha256sum "$D/mrg5_dri.so"
echo "saved Debian driver: $(sha256sum "$KEEP" | cut -c1-16)…"
echo "held: $(apt-mark showhold | grep -c .) packages"
