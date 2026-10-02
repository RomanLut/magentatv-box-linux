#!/bin/bash
# build-luanti.sh (checks/41, "Games and emulators"): build and install Luanti (the voxel game
# engine formerly called Minetest) from source on the box.
#
#   systemd-run --unit=luanti-build /root/luanti/build-luanti.sh      # on the box, as root
#
# Debian 12 has only minetest 5.6.1 and Luanti publishes no 32-bit ARM Linux build, so the
# release is built natively (4 cores, about an hour). Build dependencies as in the release's
# doc/compiling/linux.md; the box's patched Mesa is held and not touched (its -dev packages
# are installed already). Installs to /usr/local: /usr/local/bin/luanti,
# /usr/local/share/luanti/, the menu entry org.luanti.luanti.desktop. Luanti ships no game since
# 5.8, and none is installed here (the owner's choice, 2026-09-30): games come from Luanti's own
# content browser into ~/.minetest/games.
# Log: /root/luanti/build-<version>.log.
set -euo pipefail
VER=${VER:-5.17.0}
SRC=/usr/local/src/luanti-$VER
LOG=/root/luanti/build-$VER.log
mkdir -p /root/luanti
exec > >(tee "$LOG") 2>&1
step() { echo; echo "== $(date +%T) $*"; }

step "build dependencies"
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    git g++ make libc6-dev cmake libpng-dev libjpeg-dev libgl1-mesa-dev libsqlite3-dev \
    libogg-dev libvorbis-dev libopenal-dev libcurl4-gnutls-dev libfreetype-dev zlib1g-dev \
    libgmp-dev libjsoncpp-dev libzstd-dev libluajit-5.1-dev gettext libsdl2-dev

step "LuaJIT (v2.1 branch, static, /opt/luajit)"
# Debian 12's LuaJIT (2.1.0~beta3+git20220320) computes 64-bit FFI integers wrongly on 32-bit
# ARM: Mineclonia's self-test stops its world with "PRNG validation failed ... Your LuaJIT
# installation ... is out-of-date" (mcl_levelgen/random.lua, seed_from_position in plain Lua
# and in LuaJIT's uint64 disagree). A current v2.1 is built into Luanti statically, in its own
# prefix, so Debian's libluajit and everything else using it stay as they are.
LJ=/usr/local/src/luajit-2.1
if [ ! -d "$LJ/.git" ]; then
    git clone --branch v2.1 https://github.com/LuaJIT/LuaJIT.git "$LJ"
fi
git -C "$LJ" log -1 --format='%h %cd' --date=short
make -C "$LJ" -j"$(nproc)" PREFIX=/opt/luajit
make -C "$LJ" install PREFIX=/opt/luajit

step "source $VER"
if [ ! -d "$SRC/.git" ]; then
    git clone --depth 1 --branch "$VER" https://github.com/luanti-org/luanti.git "$SRC"
fi
git -C "$SRC" describe --tags

step "configure"
rm -rf "$SRC/build"
mkdir -p "$SRC/build"
cd "$SRC/build"
cmake .. -DCMAKE_BUILD_TYPE=Release -DRUN_IN_PLACE=FALSE -DCMAKE_INSTALL_PREFIX=/usr/local \
    -DBUILD_CLIENT=TRUE -DBUILD_SERVER=FALSE -DBUILD_UNITTESTS=FALSE -DENABLE_GETTEXT=TRUE \
    -DLUA_INCLUDE_DIR=/opt/luajit/include/luajit-2.1 -DLUA_LIBRARY=/opt/luajit/lib/libluajit-5.1.a

step "compile (make -j$(nproc))"
make -j"$(nproc)"

step "install"
make install

step "done"
/usr/local/bin/luanti --version
if ldd /usr/local/bin/luanti | grep -q luajit; then
    echo "WARNING: luanti links a shared libluajit, not /opt/luajit's static one"
else
    echo "LuaJIT linked statically (no libluajit in ldd)"
fi
