# Building from source

Everything in the release images that this project made or changed is in this repository: the
kernel and its rescue initramfs, the device tree, the patched GPU and X drivers, the programs
built from upstream sources, our system files, and the scripts that make the images. Binaries of
other projects are not kept here; the scripts download their sources and check them by SHA-256.

| Folder | What | License |
|---|---|---|
| [kernel/](kernel) | `linux-6.18-mrg5.patch` (all changes against Linux 6.18), `config-mrg5` (the released configuration), `build-kernel.sh` | GPL-2.0 |
| [initramfs/](initramfs) | the rescue system built into the kernel: boot scripts, init wrapper, BusyBox configuration, `build-initramfs.sh` | GPL-2.0 (BusyBox), MIT (Dropbear), ours |
| [firmware/](firmware) | `fetch-firmware.sh`: Realtek's Bluetooth firmware (downloaded, not kept here) and its config | Realtek's own; script ours |
| [devicetree/](devicetree) | `dtb-mrg5-release.bin` (the device tree the images boot), its source `.dts`, the scripts that added our nodes | see below |
| [mesa/](mesa) | Mesa 22.3.6 V3D 3.3 fixes: patches, fix scripts, build and install scripts | MIT |
| [xorg/](xorg) | the X.Org modesetting driver with Raspberry Pi's msdri3 and our changes | MIT |
| [retroarch-cores/](retroarch-cores) | build scripts of the RetroArch cores | per core |
| [luanti/](luanti) | Luanti 5.17 and LuaJIT 2.1 build, TV start command | LGPL-2.1 (Luanti), MIT (LuaJIT) |
| [chromium/](chromium) | the setup of Raspberry Pi's Chromium (browser user, start commands) | ours |
| [debian/](debian) | the Debian 12 base system, the desktop's package set, CasaOS, PulseAudio | ours |
| [system/](system) | our system files at their target paths (`rootfs/`), `install.sh` | ours; the TV launcher and the Quake setup GPL-3.0-or-later (they use PyQt5; files listed in [LICENSE.txt](LICENSE.txt)) |
| [build-release/](build-release) | `make-release.sh`, `make-image.sh`, `make-uninstall.sh`, the installer, the first-start services | ours |

"Ours" is the project's own work, under the license in [LICENSE.txt](LICENSE.txt).

## The kernel

```sh
sudo apt-get install gcc-arm-linux-gnueabihf make bc bison flex libssl-dev libelf-dev cpio xz-utils bzip2 curl python3 file
kernel/build-kernel.sh            # result: kernel/.build/zImage-mrg5
```

`build-kernel.sh`:
1. downloads Linux 6.18 from kernel.org and applies `linux-6.18-mrg5.patch`;
2. builds the initramfs (`initramfs/build-initramfs.sh`: BusyBox 1.37.0, musl 1.2.5,
   Dropbear 2025.88 linked statically against musl, and the init wrapper). musl is built from
   SHA-256-checked source using Ubuntu/Debian's ARM compiler; its source is downloaded from
   Buildroot's mirror with upstream as a fallback. No prebuilt musl.cc toolchain is needed;
3. fetches the Bluetooth firmware and makes its config (`firmware/fetch-firmware.sh`);
4. builds `zImage` with `config-mrg5`;
5. checks the generated initramfs (including its compressed copy linked into `vmlinux`)
   for an empty rescue `authorized_keys` and absence of key material, then writes
   `zImage-mrg5.release` with the kernel and initramfs hashes. A failed build or check leaves
   no certificate for that output image.

The GitHub Action [build-kernel.yml](.github/workflows/build-kernel.yml) runs the same on every
change to these folders and keeps the zImage and its `.release` certificate as the run's artifact. The released kernel was built
with Ubuntu 24.04's `arm-linux-gnueabihf-gcc` 13.3. A rebuild is the same source and configuration,
but not bit-identical, because the build time and host are part of the image.

The rescue system (the initramfs, when no system partition is found) has a console shell. Its
SSH server accepts keys only and has none (`initramfs/root/root/.ssh/authorized_keys` is empty,
and `build-initramfs.sh` refuses a key there), so nobody can log in over the network.

## The device tree

`dtb-mrg5-release.bin` is the box's own device tree with our nodes added: the V3D GPU
(`add-v3d-node.py`), the KMS display driver (`add-kms-node.py`), the 512 MiB GPU memory pool
(`add-v3d-pool.py`, `resize-v3d-pool.py`), the Bluetooth chip (`add-bt-node.py`). The Ethernet
MAC address is not in it: the bootloader writes each box's own address in when it starts the
kernel, and `mrg5-macaddr` reads it from the boot flash as well.

## Mesa and the X driver

Debian's Mesa packages stay installed and are put on hold; only the Gallium driver
(`v3d_dri.so`, `mrg5_dri.so`) is replaced by one built from Debian's own Mesa 22.3.6 source with
`mesa-22.3.6-v3d33.patch` (defects 1-11), `mesa-22.3.6-kmsro-mrg5.patch` and the fix scripts for
defects 12-36, applied in this order: `mesa-tfuphys.py`, `mesa-ownscanout.py`, `mesa-tbo33.py`,
`mesa-thrsw1.py`, `mesa-unifa33.py`, `mesa-nospill33.py`, `mesa-r3merge33.py`, `mesa-noscratch33.py`,
`mesa-tex1d33.py`, `mesa-vpmthrsw33.py`, `mesa-indepblend33.py`, `mesa-lodclamp33.py`,
`mesa-d32f33.py`, `mesa-tlbvec33.py`, `mesa-tf33.py`, `mesa-vpmread33.py`, `mesa-centroid33.py`,
`mesa-emptybin33.py`, `mesa-tex4words33.py`, `mesa-vecalign33.py`, `mesa-xoruif33.py`,
`mesa-samplemask33.py`, `mesa-mszs33.py`, `mesa-loadflush33.py`, `mesa-mstex33.py`,
`mesa-vid33.py`, `mesa-blittfu33.py` (`mesa-ldvary.py` is defect 11 of the patch as a script).
`build-mesa-v3d.sh` builds on the box: it applies both patches and calls `apply-fixes.sh`
to run all 27 later fix scripts above with their required source directories, before compiling.
Keep the entire `mesa/` directory together; patches and scripts are found beside the build
script. `install-mesa-v3d.sh` installs and sets the hold.

`retroarch-cores/build-cores.sh` pins PrBoom, ECWolf, vitaQuake 2, XRick and ScummVM to the
full commit IDs from the original release build. It fetches those exact commits, checks them
out detached, and refuses existing source trees with local changes. It does not track upstream
branch heads. Toolchains and Debian packages still come from the configured repositories;
this is source revision pinning, not a promise of bit-identical binaries.

The X server's modesetting driver is Raspberry Pi's xorg-server 21.1.7-3+rpt3+deb12u12 with its
msdri3 patches (0001-0003) and ours (`mrg5-msdri3-*.py`), built by `build-msdri3.sh` and installed
with `dpkg-divert`.

## The release images

The images are copies of a running, installed system, made on the box itself:

First build the kernel as above. Copy **both** `kernel/.build/zImage-mrg5` and
`kernel/.build/zImage-mrg5.release`, plus `devicetree/dtb-mrg5-release.bin`, to
`/root/emmc-release/` on the build system alongside the files from `build-release/`.
The image builders verify the certificate's kernel hash and rescue-key check. Keep the
certificate with the exact image that generated it; do not create a sidecar by hand.

```sh
# on the system the releases are built from, as root, with build-release/ in /root/emmc-release
# and the kernel and device tree next to it
systemd-run --wait --setenv=KERNEL=zImage-mrg5 --setenv=EDITION=usb      --setenv=VERSION=<v> /root/emmc-release/make-release.sh
systemd-run --wait --setenv=KERNEL=zImage-mrg5 --setenv=EDITION=emmc     --setenv=VERSION=<v> /root/emmc-release/make-release.sh
systemd-run --wait --setenv=KERNEL=zImage-mrg5 --setenv=EDITION=emmc-hdd --setenv=VERSION=<v> /root/emmc-release/make-release.sh
/root/emmc-release/make-image.sh /srv/mrg5-release     <name>.img MRG5-INST   # EMMC Only
/root/emmc-release/make-image.sh /srv/mrg5-release-hdd <name>.img MRG5-INST   # EMMC + internal HDD
KERNEL=zImage-mrg5 /root/emmc-release/make-uninstall.sh && /root/emmc-release/make-image.sh /srv/mrg5-uninstall <name>.img MRG5-UNINST
```

`make-release.sh` copies the running system, removes everything personal (home folders by allow
list, accounts, keys, histories, pairings) and the Quake game data (downloaded on first use by
`quake-shareware-setup.py` instead) and checks that none of it is left, sets the edition's
storage, services and first-start steps, and writes the result: a SquashFS installer stick (EMMC
Only, EMMC + internal HDD) or a two-partition USB drive image (USB Boot). The installer always
installs, whatever the eMMC holds.
