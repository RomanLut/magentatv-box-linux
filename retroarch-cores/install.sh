#!/bin/sh
# Install the game launchers on the box. Run on the box from a copy of this
# directory: sh install.sh. Expects the packages and the three built cores
# (see checks/41, "Games and emulators").
set -e
cd "$(dirname "$0")"

install -m 755 quake /usr/local/bin/quake
# Quake's shareware data on first use (checks/41, "Quake"); the menu entry and the desktop icon
# start /usr/local/bin/quake
install -d /usr/local/lib/mrg5-games /usr/local/share/applications
install -m 755 quake-shareware-setup.py /usr/local/lib/mrg5-games/quake-shareware-setup.py
install -m 644 quake.desktop /usr/local/share/applications/quake.desktop
[ -f /root/Desktop/quake.desktop ] && sed -i 's|^Exec=/usr/games/quake$|Exec=/usr/local/bin/quake|' /root/Desktop/quake.desktop
install -m 755 retro-run /usr/local/bin/retro-run
install -m 755 bios-check /usr/local/bin/bios-check
for s in nes snes gb gbc gba megadrive genesis mastersystem gamegear megacd pce psx n64 \
	doom wolf3d quake2 scummvm rick; do
	ln -sf retro-run /usr/local/bin/$s
done

install -d /usr/local/share/mrg5-games /usr/local/lib/libretro
install -m 644 retroarch-mrg5.cfg retroarch-mrg5-kms.cfg bios-manifest.txt \
	/usr/local/share/mrg5-games/
install -m 644 /root/src/pcsx_rearmed/pcsx_rearmed_libretro.so \
	/root/src/Genesis-Plus-GX/genesis_plus_gx_libretro.so \
	/root/src/mupen64plus-libretro-nx/mupen64plus_next_libretro.so \
	/usr/local/lib/libretro/

install -d -m 777 /DATA/Games
chmod 777 /DATA/Games
for d in bios nes snes gb gba megadrive pce psx n64 psp doom wolf3d quake2 scummvm downloads; do
	install -d -m 777 /DATA/Games/$d
done
install -m 666 bios-README.txt /DATA/Games/bios/README.txt
echo installed
