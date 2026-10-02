#!/bin/sh
set -u
cd /root/src/mupen64plus-libretro-nx
echo "=== core option keys for the RDP plugin ==="
grep -n 'rdp-plugin\|RDP_PLUGIN_ANGRYLION\|"angrylion"' libretro/libretro_core_options.h libretro/libretro.c 2>/dev/null | head -20
echo "=== install the core ==="
install -m 644 mupen64plus_next_libretro.so /usr/local/lib/libretro/
ln -sf retro-run /usr/local/bin/n64
ls -la /usr/local/lib/libretro/ /usr/local/bin/n64
echo "=== sha256 of the core ==="
sha256sum /usr/local/lib/libretro/mupen64plus_next_libretro.so
