#!/bin/bash
# Build Mesa's V3D driver from Debian's own mesa 22.3.6 source with both
# patches and all later V3D 3.3 fix scripts, natively on the box.
# Keep the entire mesa/ directory together beside this script.
#
# Same version, same distribution toolchain and libraries as the installed
# libEGL_mesa / libgbm / libglapi, so the driver stays ABI-compatible with them.
# Only the Gallium v3d (+ kmsro) driver is built: no LLVM, no Vulkan.
#
# Output: /root/mesa-v3d/v3d_dri.so  (install with install-mesa-v3d.sh)
# Log:    /root/mesa-v3d/build.log
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
W=/root/mesa-v3d
mkdir -p "$W"
cd "$W"
exec > >(tee -a "$W/build.log") 2>&1
echo "== build-mesa-v3d $(date -Is)"

# source packages
if [ ! -f /etc/apt/sources.list.d/deb-src.list ]; then
    cat > /etc/apt/sources.list.d/deb-src.list <<'EOF'
deb-src http://deb.debian.org/debian bookworm main
deb-src http://deb.debian.org/debian bookworm-updates main
deb-src http://deb.debian.org/debian-security bookworm-security main
EOF
fi
apt-get update -qq

apt-get -y -qq --no-install-recommends install \
    dpkg-dev meson ninja-build pkg-config python3-mako bison flex patch g++ \
    libdrm-dev libexpat1-dev zlib1g-dev libzstd-dev \
    libx11-dev libxext-dev libxfixes-dev libx11-xcb-dev libxcb-glx0-dev \
    libxcb-shm0-dev libxcb-dri2-0-dev libxcb-dri3-dev libxcb-present-dev \
    libxcb-sync-dev libxcb-randr0-dev libxcb-xfixes0-dev libxshmfence-dev \
    libxxf86vm-dev libxrandr-dev libwayland-dev libwayland-bin \
    wayland-protocols libwayland-egl-backend-dev

# the exact version that is installed
VER=$(dpkg-query -W -f='${Version}' libgl1-mesa-dri:armhf)
echo "== installed libgl1-mesa-dri: $VER"
if [ ! -d "$W/src" ]; then
    apt-get source -qq "mesa=$VER"
    mv "$(ls -d mesa-*/ | head -1)" src
fi
cd "$W/src"

if ! grep -q "A single-threaded shader (V3D 3.x" src/broadcom/compiler/nir_to_vir.c; then
    patch -p1 < "$HERE/mesa-22.3.6-v3d33.patch"
fi
# the one that makes the hardware draw at all: vpmwt on V3D 3.x (checks/53)
grep -q "c->devinfo->ver <= 42)" src/broadcom/compiler/nir_to_vir.c ||
    { echo "v3d33 patch: vpmwt hunk missing"; exit 1; }
# and the one that makes alpha blending work: the 32-bit Blend Cfg payload
grep -q 'name="VG mode"' src/broadcom/cle/v3d_packet_v33.xml ||
    { echo "v3d33 patch: Blend Cfg hunk missing"; exit 1; }

# our KMS driver on kmsro's list (work/kms-20260921/mesa-22.3.6-kmsro-mrg5.patch)
if ! grep -q "DEFINE_LOADER_DRM_ENTRYPOINT(mrg5)" src/gallium/targets/dri/target.c; then
    patch -p1 < "$HERE/mesa-22.3.6-kmsro-mrg5.patch"
fi

bash "$HERE/apply-fixes.sh" "$W/src"

if [ ! -d build ]; then
    meson setup build \
        -Dbuildtype=release -Db_ndebug=true \
        -Dplatforms=x11,wayland \
        -Dgallium-drivers=v3d,kmsro \
        -Dvulkan-drivers= \
        -Dllvm=disabled \
        -Dglx=dri -Degl=enabled -Dgbm=enabled \
        -Dgles1=enabled -Dgles2=enabled -Dshared-glapi=enabled \
        -Dgallium-vdpau=disabled -Dgallium-va=disabled \
        -Dgallium-xa=disabled -Dgallium-nine=false \
        -Dgallium-opencl=disabled -Dosmesa=false \
        -Dvalgrind=disabled -Dlibunwind=disabled -Dlmsensors=disabled \
        -Dbuild-tests=false
fi

echo "== ninja $(date -Is)"
ninja -C build src/gallium/targets/dri/libgallium_dri.so
cp build/src/gallium/targets/dri/libgallium_dri.so "$W/v3d_dri.so"
ls -l "$W/v3d_dri.so"
sha256sum "$W/v3d_dri.so"
echo "== done $(date -Is)"
