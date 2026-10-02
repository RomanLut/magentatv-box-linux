#!/bin/bash
# make-release.sh (checks/54, "eMMC release", "USB Boot"): build a release from the running
# MRG5 system (the HDD system).
#
#   systemd-run --unit=mrg5-make-release --setenv=EDITION=emmc /root/emmc-release/make-release.sh
#
# EDITION=emmc ("EMMC Only boot"), output in $OUT (default /srv/mrg5-release), packed into a disk
# image by make-image.sh:
#   Testapp6/BOOT/boot.ini            installer: sets BOLT's STARTUP if missing, boots live
#   Testapp6/BOOT/<kernel>, <dtb>     the kernel and device tree
#   Testapp6/live/rootfs.sqfs         the reduced system (SquashFS, zstd)
#   Testapp6/emmc/boot.ini, startup.ini   written to the eMMC's boot partition by the installer
#   SHA256SUMS (no documentation: the README is on GitHub, owner 2026-10-02)
# The stick boots the system live from rootfs.sqfs (initramfs live mode, stage1-root.sh);
# mrg5-emmc-install.service then partitions the eMMC and installs it (mrg5-emmc-install).
#
# EDITION=usb ("USB Boot"), output the disk image $IMGDIR/magentatv-box-linux-usb-boot-<version>.img.xz
# (staging in $OUT, default /srv/mrg5-release-usb):
#   1  FAT32 "MRG5-USB" 512 MiB: Testapp6/BOOT/ (boot.ini with the root label, kernel, DTB),
#      SHA256SUMS; BOLT starts it through its USB path, nothing is written to NOR
#   2  ext4 "MRG5USBROOT": the system with CasaOS and Docker, mounted as on the USB system stick
#      (noatime, commit=600, logs and caches in RAM); mrg5-growroot grows it to the end of the
#      USB drive at the first start, mrg5-casaos-preset makes the CasaOS account and the share
#
# EDITION=emmc-hdd ("EMMC + internal HDD"): the installer stick of EMMC Only (same output, packed
# by make-image.sh), with CasaOS and Docker. The installer also erases the internal HDD
# (partition "MRG5HDD"); /sbin/init is mrg5-overlay-init, which runs the eMMC system read-only
# with every write going to the HDD (overlay), and fstab binds /DATA and Docker's folders to it.
#
# Every release leaves out personal data (/DATA contents, browser, Kodi and Luanti profiles,
# histories, Bluetooth pairings, Samba users, SSH keys and host keys, machine-id) and the
# development leftovers in /root and /usr/local/src (release-exclude.txt plus the keep list for
# /root below). EMMC Only also leaves out CasaOS and Docker (release-exclude-nocasaos.txt,
# purged); USB Boot keeps them with CasaOS's state reset. The account "admin" gets
# $RELEASE_PASSWORD (default "admin", as the public README documents: admin / admin).
#
# Environment: EDITION (emmc), OUT, IMGDIR (/srv/mrg5-images), KERNEL (default zImage-smp6c),
# DTB (dtb-mrg5-release.bin), BOOTDIR (the directory holding them; default this script's
# directory), RELEASE_PASSWORD (admin), KEEP_SSH_KEY=1 keeps root's authorized_keys (test builds
# only), VERSION (date), SKIP_COPY=1 reuses the staging copy of an interrupted run.
set -euo pipefail
HERE=$(dirname "$(readlink -f "$0")")
# the release (checks/54): emmc = "EMMC Only boot" (/DATA fixed on the eMMC, an HDD is never
# touched); emmc-hdd = "EMMC + internal HDD" (eMMC read-only, every write on the HDD); usb =
# "USB Boot" (/DATA fixed on the USB drive, the internal HDD is not used)
EDITION=${EDITION:-emmc}
case "$EDITION" in
    emmc)     OUT=${OUT:-/srv/mrg5-release} ;;
    emmc-hdd) OUT=${OUT:-/srv/mrg5-release-hdd} ;;
    usb)      OUT=${OUT:-/srv/mrg5-release-usb} ;;
    *) echo "ERROR: EDITION must be emmc, emmc-hdd or usb" >&2; exit 1 ;;
esac
# INSTALLER: an eMMC installer stick (live SquashFS); CASAOS: CasaOS and Docker stay
case "$EDITION" in emmc|emmc-hdd) INSTALLER=1 ;; *) INSTALLER=0 ;; esac
case "$EDITION" in usb|emmc-hdd) CASAOS=1 ;; *) CASAOS=0 ;; esac
STAGE=$OUT/root
IMGDIR=${IMGDIR:-/srv/mrg5-images}
# the copy of / must not take in its own output (it did once: the staging copy copied itself
# until it held 40 GB); release-exclude.txt leaves out exactly these places
case "$OUT" in /srv/mrg5-release*) ;; *) echo "ERROR: OUT must be /srv/mrg5-release*" >&2; exit 1 ;; esac
[ "$IMGDIR" = /srv/mrg5-images ] || { echo "ERROR: IMGDIR must be /srv/mrg5-images" >&2; exit 1; }
KERNEL=${KERNEL:-zImage-smp6c}
DTB=${DTB:-dtb-mrg5-release.bin}
RELEASE_PASSWORD=${RELEASE_PASSWORD:-admin}
KEEP_SSH_KEY=${KEEP_SSH_KEY:-0}
VERSION=${VERSION:-$(date +%Y%m%d)}
EMMC_LABEL=MRG5EMMC
USB_BOOT_LABEL=MRG5-USB
USB_ROOT_LABEL=MRG5USBROOT
USB_FAT_MB=512
LOG=/root/make-release-$EDITION-$(date +%Y%m%d-%H%M).log
exec > >(tee "$LOG") 2>&1
step() { echo; echo "== $(date +%T) $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "run as root"
mountpoint -q /live/medium && die "this is the live system; build from an installed one"
for t in mksquashfs unsquashfs sfdisk mkfs.vfat mkfs.ext4 setfont xz losetup; do
    command -v "$t" >/dev/null || die "$t missing (apt-get install squashfs-tools fdisk dosfstools e2fsprogs kbd console-setup-linux xz-utils)"
done
[ "$EDITION" = usb ] && { command -v growpart >/dev/null || die "growpart missing (apt-get install cloud-guest-utils): the USB system needs it"; }
if [ "$CASAOS" = 1 ]; then
    [ -x /usr/bin/casaos ] && [ -d /var/lib/casaos/www ] || die "CasaOS is not installed on this system"
    [ -x /usr/bin/dockerd ] || die "Docker is not installed on this system"
fi
BOOTDIR=${BOOTDIR:-$HERE}
[ -f "$BOOTDIR/$KERNEL" ] && [ -f "$BOOTDIR/$DTB" ] || die "no $KERNEL and $DTB in BOOTDIR=$BOOTDIR"
# only a release kernel: built by work/kms-20260921/build-release-kernel.sh, whose .release file
# records its sha256 and that its rescue initramfs holds no SSH keys (owner, 2026-10-03)
[ -f "$BOOTDIR/$KERNEL.release" ] || die "$KERNEL has no .release file (build it with build-release-kernel.sh)"
grep -qx "sha256=$(sha256sum "$BOOTDIR/$KERNEL" | cut -d' ' -f1)" "$BOOTDIR/$KERNEL.release" ||
    die "$KERNEL does not match its .release file"
grep -qx "rescue_ssh_keys=none.*" "$BOOTDIR/$KERNEL.release" || die "$KERNEL's rescue initramfs may hold SSH keys"
# the stick boot.ini of the running system (USB paths, root label line), as in boot-smp6a-pool512.ini
TEMPLATE=$HERE/boot-template.ini
[ -f "$TEMPLATE" ] || die "no boot.ini template $TEMPLATE"
echo "release $VERSION ($EDITION) from $(hostname), kernel $KERNEL, dtb $DTB (from $BOOTDIR)"

# ------------------------------------------------------------------ staging copy
excl=(--exclude-from="$HERE/release-exclude.txt")
[ "$CASAOS" = 0 ] && excl+=(--exclude-from="$HERE/release-exclude-nocasaos.txt")
if [ "${SKIP_COPY:-0}" = 1 ] && [ -x "$STAGE/lib/systemd/systemd" ]; then
    # reuse the copy of an interrupted run (the steps below can run again on it)
    step "reusing the copy in $STAGE (SKIP_COPY=1)"
    rm -rf "$OUT/Testapp6" "$OUT/SHA256SUMS"
else
step "copying the system to $STAGE"
rm -rf "$OUT"
mkdir -p "$STAGE"
set +e
tar -C / --create --one-file-system --numeric-owner --xattrs --xattrs-include='*' --acls \
    --sparse --anchored --wildcards "${excl[@]}" \
    --warning=no-file-ignored --file=- . |
    tar -C "$STAGE" --extract --numeric-owner --xattrs --xattrs-include='*' --acls \
        --same-permissions --file=-
st=("${PIPESTATUS[@]}")
set -e
# GNU tar exits 1 for files that changed while being read (a running system), as in
# make-usb-stick.sh
[ "${st[0]}" -le 1 ] || die "reading the system failed (tar ${st[0]})"
[ "${st[1]}" -eq 0 ] || die "writing the copy failed (tar ${st[1]})"
fi
[ -x "$STAGE/lib/systemd/systemd" ] && [ -e "$STAGE/mrg5/installed" ] || die "copy incomplete"
du -sh "$STAGE" | cut -f1

# ------------------------------------------------------------- remove packages
step "removing packages ($EDITION)"
R=$STAGE
cleanup_chroot() {
    # a process just started in the chroot can still hold one for a moment (proc stayed mounted
    # once, 2026-10-01): retry, then detach it lazily
    for m in dev/pts dev sys proc; do
        mountpoint -q "$R/$m" || continue
        umount "$R/$m" 2>/dev/null || { sleep 2; umount "$R/$m" 2>/dev/null; } ||
            umount -l "$R/$m" 2>/dev/null || true
    done
    rm -f "$R/usr/sbin/policy-rc.d"
}
trap cleanup_chroot EXIT
mount -t proc proc "$R/proc"
mount -t sysfs sys "$R/sys"
mount --bind /dev "$R/dev"
mount --bind /dev/pts "$R/dev/pts"
printf '#!/bin/sh\nexit 101\n' > "$R/usr/sbin/policy-rc.d"   # no service starts in the chroot
chmod 755 "$R/usr/sbin/policy-rc.d"
# development-only packages from the bring-up (GPU test suite, debugger, build headers);
# no autoremove: it strips libraries the /opt Chromium needs (memory: no-apt-autoremove)
dev=$(chroot "$R" dpkg-query -W -f='${Package}\n' 2>/dev/null |
    grep -E '^(piglit|gdb|gdbserver|cmake|cmake-data|build-essential|g\+\+|g\+\+-12|meson|ninja-build)$' || true)
# the -dev headers (~100 MB) stay: the held, patched Mesa's -dev packages depend on them
if [ -n "$dev" ]; then
    # shellcheck disable=SC2086
    chroot "$R" env DEBIAN_FRONTEND=noninteractive apt-get purge -y $dev
fi
rm -rf "$R/usr/lib/arm-linux-gnueabihf/piglit"
# Quake: the engine (quakespasm) and Debian's quake package stay, the game data does not
# (id Software's shareware licence). quake-shareware-setup downloads it on first use
# (checks/41, "Quake"); the quake package still depends on game-data-packager instead.
if chroot "$R" dpkg-query -W -f='${Status}' quake-shareware 2>/dev/null | grep -q 'install ok installed'; then
    chroot "$R" env DEBIAN_FRONTEND=noninteractive apt-get purge -y quake-shareware
fi
rm -rf "$R/usr/local/share/games/quake"
for f in usr/games/quakespasm usr/bin/lha usr/local/bin/quake usr/local/lib/mrg5-games/quake-shareware-setup.py \
         usr/share/games/quake/quakespasm.pak; do
    [ -e "$R/$f" ] || die "Quake's first-start setup needs /$f in the copy"
done
chroot "$R" python3 -c 'import PyQt5.QtQuick' 2>/dev/null || die "Quake's first-start setup needs PyQt5's QtQuick"
# the cores for RetroArch's downloadable games (games-20260924/build-cores.sh): PrBoom,
# vitaQuake 2 and ScummVM (GPL) and ECWolf (GPL + id's Wolf3D licence) ship; XRick has no
# formal licence, so it stays off the release (owner, 2026-10-03)
rm -f "$R/usr/local/lib/libretro/xrick_libretro.so" "$R/usr/local/bin/rick"
for f in prboom ecwolf vitaquake2 scummvm; do
    [ -f "$R/usr/local/lib/libretro/${f}_libretro.so" ] || die "the $f core is not in the copy"
done
[ -d "$R/usr/local/share/scummvm/theme" ] || die "ScummVM's data (/usr/local/share/scummvm) is not in the copy"
if [ "$CASAOS" = 0 ]; then
    pkgs=$(chroot "$R" dpkg-query -W -f='${Package}\n' 2>/dev/null |
        grep -E '^(docker-ce|docker-ce-cli|docker-ce-rootless-extras|docker-buildx-plugin|docker-compose-plugin|docker-model-plugin|containerd\.io)$' || true)
    if [ -n "$pkgs" ]; then
        # shellcheck disable=SC2086
        chroot "$R" env DEBIAN_FRONTEND=noninteractive apt-get purge -y $pkgs
    fi
    rm -f "$R/etc/apt/sources.list.d/docker.list" "$R/etc/apt/keyrings/docker.asc"
    # CasaOS is not a package: its installer put binaries and units in place (and rclone with it)
    for u in casaos casaos-gateway casaos-message-bus casaos-local-storage casaos-user-service \
             casaos-app-management rclone; do
        rm -f "$R/etc/systemd/system/$u.service" "$R/etc/systemd/system/$u.service.buildroot" \
              "$R/usr/lib/systemd/system/$u.service" "$R/usr/lib/systemd/system/$u.service.buildroot"
        find "$R/etc/systemd/system" -name "$u.service" -type l -delete
    done
    rm -f "$R"/usr/bin/casaos* "$R/usr/bin/rclone" "$R"/etc/bash_completion.d/casaos*
    rm -rf "$R/opt/containerd" "$R/etc/docker"
    rm -f "$R/root/Desktop/casaos.desktop" "$R/usr/local/share/icons/casaos.png"
    # Samba: CasaOS's shares go with it; smbd stays, without shares
    sed -i '/include *= *\/etc\/samba\/smb.casa.conf/d' "$R/etc/samba/smb.conf"
    rm -f "$R/etc/samba/smb.casa.conf"
    # the launcher's CasaOS tile
    sed -i '/<tile title="CasaOS"/,/\/>/d' "$R/etc/mrg5-launcher/tiles.xml"
    grep -q CasaOS "$R/etc/mrg5-launcher/tiles.xml" && die "CasaOS tile still in tiles.xml"
else
    # CasaOS stays, as a fresh installation: no account, shares, disks, settings or install id
    # (they are made at the first start, mrg5-casaos-preset); Docker starts with no images
    rm -rf "$R"/var/lib/casaos/db/* "$R/var/lib/casaos/1" "$R/var/lib/casaos/baseinfo.conf"
    rm -f "$R/etc/samba/smb.casa.conf"
    grep -q '<tile title="CasaOS"' "$R/etc/mrg5-launcher/tiles.xml" || die "no CasaOS tile in tiles.xml"
    [ -f "$R/usr/local/share/icons/casaos.png" ] || die "no CasaOS icon"
fi

# -------------------------------------------------------------- personal data
step "removing personal data and identities"
# Home folders by allow list, never by deny list: whatever is not named here goes (a deny list
# once let browser profiles under other names, Kodi's profile, the desktop's trash and game
# saves into the images, 2026-10-01). keep_only <dir> <names...>: remove every other entry.
keep_only() {
    local d=$1 f
    shift
    [ -d "$d" ] || return 0
    for f in "$d"/* "$d"/.[!.]* "$d"/..?*; do
        [ -e "$f" ] || [ -L "$f" ] || continue
        case " $* " in *" $(basename "$f") "*) ;; *) rm -rf "$f" ;; esac
    done
}
# /root: the desktop scripts and the configuration the desktop and the games start with
keep_only "$R/root" .bashrc .profile .config .drirc .quakespasm .local Desktop \
    start-desktop.sh stop-desktop.sh desktop-accel.sh set-dpi.sh
# (not pulse/: its cookie is the sound server's access key, made anew at the first start)
keep_only "$R/root/.config" xfce4 Thunar Mousepad ristretto mpv retroarch \
    mimeapps.list user-dirs.dirs user-dirs.locale
keep_only "$R/root/.config/retroarch" retroarch.cfg autoconfig assets config filters overlay \
    shaders layouts database cheats
# Core option defaults of the release (owner, 2026-10-03): automatic frame skipping for the
# systems whose games can fall behind on this CPU, so they slow down less and crackle less.
# RetroArch keeps one option file per core; the player can still change them in the Quick Menu.
# PPSSPP skips only when the frame-skip count is above 0 and takes it as the upper limit
# (Core/HLE/sceDisplay.cpp); PCSX ReARMed's "auto" skips when RetroArch reports its audio
# buffer running low; Mupen64Plus-Next has no frame skip, its equivalent is frame duping.
set_core_opt() { # <core name> <key> <value>
    f="$R/root/.config/retroarch/config/$1/$1.opt"
    install -d "${f%/*}" && touch "$f" && sed -i "/^$2 = /d" "$f" && echo "$2 = \"$3\"" >> "$f"
}
set_core_opt PPSSPP ppsspp_auto_frameskip enabled
set_core_opt PPSSPP ppsspp_frameskip 2
# PSP games drawn at 2x (960x544) instead of the PSP's own 480x272 (owner, 2026-10-03)
set_core_opt PPSSPP ppsspp_internal_resolution 960x544
set_core_opt PCSX-ReARMed pcsx_rearmed_frameskip_type auto
# PS1 games drawn at 2x by the NEON renderer's enhancement (owner); measured on the box, Silent
# Hill keeps full speed with it (1800 frames in 29.9 s, the same as native)
set_core_opt PCSX-ReARMed pcsx_rearmed_neon_enhancement_enable enabled
set_core_opt Mupen64Plus-Next mupen64plus-FrameDuping True
# Quake II: vitaQuakeII's GLES build has only the software renderer (upstream's Makefile turns
# HAVE_OPENGL off for GLES=1). At its 960x544 default it drew 34 fps against RetroArch's 60 Hz
# target, so the sound broke up. Measured on the box (attract demo, audio-paced): at a 50 fps
# target - the panel's own rate - 480x272 keeps up exactly, 640x368 falls 4 % short.
set_core_opt vitaQuakeII vitaquakeii_resolution 480x272
set_core_opt vitaQuakeII vitaquakeii_framerate 50
# Blueman's settings (owner, 2026-10-02): Bluetooth switched on at every start (powermanager
# auto-power-on) and the plugin list, in which the ConnectionNotifier plugin is off (no pop-up at
# every reconnection of the remote or a pad). Exactly these two keys are read from root's dconf
# database and compiled into a database of their own; nothing else of it ships (Blueman's recent
# connections hold the addresses of the build system's devices, Mousepad and GNOME Software
# their window state).
rm -rf "$R/root/.config/dconf"
command -v dconf >/dev/null && command -v dbus-run-session >/dev/null ||
    die "dconf missing (apt-get install dconf-cli): the release takes Blueman's settings from it"
kd=$(mktemp -d)
dread() { HOME=/root dbus-run-session -- dconf read "$1"; }
plugins=$(dread /org/blueman/general/plugin-list)
power=$(dread /org/blueman/plugins/powermanager/auto-power-on)
[ -n "$plugins" ] && [ -n "$power" ] || die "Blueman's settings are not in root's dconf database"
printf '[org/blueman/general]\nplugin-list=%s\n\n[org/blueman/plugins/powermanager]\nauto-power-on=%s\n' \
    "$plugins" "$power" > "$kd/blueman"
install -d -m 700 "$R/root/.config/dconf"
dconf compile "$R/root/.config/dconf/user" "$kd"
echo "Blueman settings:"; sed 's/^/  /' "$kd/blueman"
rm -rf "$kd"
keep_only "$R/root/.local" share
keep_only "$R/root/.local/share" applications
keep_only "$R/root/.quakespasm" id1
keep_only "$R/root/.quakespasm/id1" config.cfg
# the other accounts: their shell defaults only
for h in "$R"/home/*; do
    keep_only "$h" .bashrc .profile .bash_logout
done
if [ "$KEEP_SSH_KEY" = 1 ] && [ -f /root/.ssh/authorized_keys ]; then
    install -d -m 700 "$R/root/.ssh"
    install -m 600 /root/.ssh/authorized_keys "$R/root/.ssh/authorized_keys"
    echo "TEST BUILD: root's authorized_keys kept"
fi
rm -f "$R"/etc/ssh/ssh_host_*          # mrg5-firstboot.service makes new ones
: > "$R/etc/machine-id"                  # systemd makes a new one at the first boot
rm -f "$R/var/lib/dbus/machine-id"
echo mrg5 > "$R/etc/hostname"
sed -i 's/\bmrg5-nas\b/mrg5/g; s/\bmrg5-usb\b/mrg5/g' "$R/etc/hosts"
rm -f "$R/var/lib/mrg5-launcher/remote-setup-done" "$R/etc/mrg5-storage.conf" \
      "$R/etc/mrg5-usb-image" "$R/etc/mrg5-restored-from-release"
rm -rf "$R/var/lib/mrg5-storage" "$R/var/lib/mrg5"
# smartd's state and attribute logs: named after the build system's disks (model and serial) and
# holding their SMART history (owner, 2026-10-03); its drive database (drivedb/) stays
rm -f "$R"/var/lib/smartmontools/attrlog.* "$R"/var/lib/smartmontools/smartd.*.state*
# time zone: Europe/Berlin (owner, 2026-10-01)
ln -sf /usr/share/zoneinfo/Europe/Berlin "$R/etc/localtime"
echo Europe/Berlin > "$R/etc/timezone"
# accounts: root and browser stay locked; admin gets the release password
echo "admin:$RELEASE_PASSWORD" | chroot "$R" chpasswd
chroot "$R" passwd -l root >/dev/null
# an empty /DATA tree for the programs that use it
for d in Media Gallery Games Games/bios Games/nes Games/snes Games/gb Games/gba Games/megadrive \
         Games/pce Games/psx Games/n64 Games/psp Games/doom Games/wolf3d Games/quake2 Games/scummvm \
         Games/downloads Documents Downloads; do
    install -d -m 777 "$R/DATA/$d"
done
# ScummVM finds its themes and engine data in the system directory (retroarch-menu-setup.py)
ln -s /usr/local/share/scummvm "$R/DATA/Games/bios/scummvm"
[ -f /DATA/Games/bios/README.txt ] && install -m 666 /DATA/Games/bios/README.txt "$R/DATA/Games/bios/"
# the PSP core needs PPSSPP's own assets (fonts, flash0, language files) in the system
# directory; build-ppsspp.sh puts upstream's assets/ at the core's tag there (checks/41, PSP)
# (with flash0/font/*.pgf, the PSP's system fonts; they ship, owner's decision 2026-10-04)
for f in ppge_atlas.zim flash0/font/ltn0.pgf flash0/font/jpn0.pgf; do
    [ -f "/DATA/Games/bios/PPSSPP/$f" ] || die "PPSSPP's assets are not in /DATA/Games/bios/PPSSPP (no $f; run build-ppsspp.sh)"
done
cp -a /DATA/Games/bios/PPSSPP "$R/DATA/Games/bios/" && chmod -R a+rwX "$R/DATA/Games/bios/PPSSPP"
# and must be the -marm build: PPSSPP's ARM JIT calls into the core with a plain ARM BL, which
# crashes in Thumb code (an odd symbol value) as soon as a game starts from RetroArch's menu
a=$(readelf -sW "$R/usr/local/lib/libretro/ppsspp_libretro.so" | awk '$8 == "_ZN10CoreTiming7AdvanceEv" { print $2; exit }')
case "$a" in
    "") die "cannot read the PSP core's symbols (readelf, /usr/local/lib/libretro/ppsspp_libretro.so)" ;;
    *[13579bdf]) die "the PSP core is a Thumb build; rebuild it with build-ppsspp.sh (-marm)" ;;
esac

# ------------------------------------------------------------ system settings
step "configuring the copy ($EDITION)"
if [ "$EDITION" = emmc ]; then
    ROOT_LINE="LABEL=$EMMC_LABEL	/	ext4	defaults,noatime,commit=600,errors=remount-ro	0	1"
    FSTAB_HEAD="# MRG5 on the internal eMMC (work/emmc-release/make-release.sh)"
elif [ "$EDITION" = emmc-hdd ]; then
    # the root is the overlay mrg5-overlay-init makes (eMMC read-only + MRG5HDD:/upper)
    ROOT_LINE="# / is an overlay: the eMMC (LABEL=$EMMC_LABEL, read-only, /mrg5/lower) under MRG5HDD:/upper (/mrg5/hdd)"
    FSTAB_HEAD="# MRG5 EMMC + internal HDD (work/emmc-release/make-release.sh)"
else
    ROOT_LINE="LABEL=$USB_ROOT_LABEL	/	ext4	defaults,noatime,commit=600,errors=remount-ro	0	1"
    FSTAB_HEAD="# MRG5 USB Boot: the system on the USB drive (work/emmc-release/make-release.sh)"
fi
{
    echo "$FSTAB_HEAD"
    echo "$ROOT_LINE"
    cat <<EOF
# in RAM to spare the flash
tmpfs	/tmp	tmpfs	mode=1777,nosuid,nodev	0	0
tmpfs	/var/log	tmpfs	mode=0755,nosuid,nodev,size=128M	0	0
tmpfs	/root/.cache	tmpfs	mode=0700,uid=0,gid=0,nosuid,nodev,size=512M	0	0
tmpfs	/home/admin/.cache	tmpfs	mode=0700,uid=1000,gid=1001,nosuid,nodev,size=512M	0	0
tmpfs	/home/browser/.cache	tmpfs	mode=0700,uid=1001,gid=1002,nosuid,nodev,size=512M	0	0
# Samba's caches (browse list every few minutes, rebuilt at each start); users and shares stay
tmpfs	/var/cache/samba	tmpfs	mode=0755,nosuid,nodev,size=16M	0	0
EOF
    if [ "$CASAOS" = 1 ]; then
        # CasaOS's downloaded app stores: casaos-app-management rebuilds them after every boot
        # (~1100 files, ~12 MB); "default" (from the installation) stays on the drive
        for d in casaos.app github.com; do
            install -d -m 755 "$R/var/lib/casaos/appstore/$d"
            find "$R/var/lib/casaos/appstore/$d" -mindepth 1 -delete
            echo "tmpfs	/var/lib/casaos/appstore/$d	tmpfs	mode=0755,nosuid,nodev,size=64M	0	0"
        done
    fi
    if [ "$EDITION" = emmc-hdd ]; then
        # straight on the HDD, not through the overlay: the data folder, and Docker's storage
        # (overlay2 cannot run on an overlay root)
        echo "/mrg5/hdd/DATA	/DATA	none	bind	0	0"
        echo "/mrg5/hdd/docker	/var/lib/docker	none	bind	0	0"
        echo "/mrg5/hdd/containerd	/var/lib/containerd	none	bind	0	0"
    fi
} > "$R/etc/fstab"
install -d -m 700 "$R/root/.cache"
install -d -o 1000 -g 1001 -m 700 "$R/home/admin/.cache"
install -d -o 1001 -g 1002 -m 700 "$R/home/browser/.cache"
find /var/log -xdev -type d -printf 'd %p %m %U %G -\n' | awk 'NF == 6' \
    > "$R/etc/tmpfiles.d/mrg5-var-log.conf"
# DHCP client id from the MAC, not from the machine-id: the live installer, the installed system
# and every reinstall then look like one device to the router and keep one address. With the
# machine-id-based default, the first boot of the installed system waited 2 min 19 s for its
# lease (DHCPv4 at 139 s; 8.6 s at the next boot) after the live system had leased with another id.
N=$R/etc/systemd/network/10-eth0.network
if [ -f "$N" ] && ! grep -q '^ClientIdentifier=' "$N"; then
    if grep -q '^\[DHCPv4\]' "$N"; then
        sed -i '/^\[DHCPv4\]/a ClientIdentifier=mac' "$N"
    else
        printf '\n[DHCPv4]\nClientIdentifier=mac\n' >> "$N"
    fi
fi
rm -f "$R/etc/systemd/network/10-eth0.network.pre-ics-dns"
# EMMC Only and USB Boot do not use the internal HDD: no SMART monitoring of one (smartd's
# attribute log would otherwise be written to the flash every 30 minutes). smartctl stays for
# manual use; EMMC + internal HDD keeps the monitoring (owner, 2026-10-01)
if [ "$EDITION" != emmc-hdd ]; then
    chroot "$R" systemctl disable smartmontools.service >/dev/null 2>&1 || true
    rm -f "$R/etc/systemd/system/multi-user.target.wants/smartmontools.service" \
          "$R/etc/systemd/system/smartd.service"
fi
# DLNA receiver, Spotify Connect and the DLNA media server (owner, 2026-10-04; checks/41, "DLNA and
# Spotify"): the receiver and Spotify in every edition; the media server only where the data folder
# is shared (USB Boot, EMMC + internal HDD), as EMMC Only has no shared folders
for f in usr/local/bin/mrg5-dlna-receiver etc/systemd/system/mrg5-dlna-receiver.service \
         opt/macast/bin/python3 usr/bin/librespot usr/sbin/minidlnad usr/bin/shairport-sync; do
    [ -e "$R/$f" ] || die "DLNA/Spotify: /$f is not in the copy"
done
grep -q 'MagentaTV Box Linux: minidlna on the same box' "$R"/opt/macast/lib/python3*/site-packages/macast/ssdp.py ||
    die "Macast is not patched to share UDP 1900 with minidlna (work/dlna/macast-0.65.post1-reuseaddr.patch)"
grep -q '^	output_backend = "pa";' "$R/etc/shairport-sync.conf" || die "AirPlay: shairport-sync is not set to PulseAudio"
systemctl --root="$R" enable mrg5-dlna-receiver.service raspotify.service shairport-sync.service >/dev/null 2>&1
# the phone remote (checks/41, "Phone remote"): remote-touchpad on port 8090, its QR code in the
# launcher's settings; every edition
for f in usr/local/bin/remote-touchpad usr/local/bin/mrg5-phone-remote \
         etc/systemd/system/mrg5-phone-remote.service; do
    [ -e "$R/$f" ] || die "phone remote: /$f is not in the copy"
done
grep -q phoneRemoteQr "$R/usr/local/lib/mrg5-launcher/Main.qml" || die "phone remote: the launcher has no QR code"
chroot "$R" python3 -c 'import qrcode' 2>/dev/null || die "phone remote: python3-qrcode is not in the copy"
systemctl --root="$R" enable mrg5-phone-remote.service >/dev/null 2>&1
if [ "$EDITION" = emmc ]; then
    systemctl --root="$R" disable minidlna.service >/dev/null 2>&1 || true
else
    systemctl --root="$R" enable minidlna.service >/dev/null 2>&1
fi
# no automatic apt runs (owner, 2026-10-01): apt-daily and apt-daily-upgrade rebuilt the package
# caches (4.5 MB) and download the lists on the flash; updates are run by hand or from Software
systemctl --root="$R" disable apt-daily.timer apt-daily-upgrade.timer
mkdir -p "$R/etc/systemd/journald.conf.d"
printf '[Journal]\nStorage=volatile\nRuntimeMaxUse=64M\n' > "$R/etc/systemd/journald.conf.d/mrg5-volatile.conf"
install -m 644 "$HERE/mrg5-firstboot.service" "$R/etc/systemd/system/"
install -d "$R/etc/systemd/system/multi-user.target.wants"
ln -sf /etc/systemd/system/mrg5-firstboot.service "$R/etc/systemd/system/multi-user.target.wants/"
# eth0's MAC address from the box's own boot flash (BOLT puts it into the device tree too;
# this keeps it when that does not happen)
install -m 755 "$HERE/mrg5-macaddr" "$R/usr/local/sbin/mrg5-macaddr"
install -m 644 "$HERE/mrg5-macaddr.service" "$R/etc/systemd/system/"
install -d "$R/etc/systemd/system/sysinit.target.wants"
ln -sf /etc/systemd/system/mrg5-macaddr.service "$R/etc/systemd/system/sysinit.target.wants/"
if [ "$INSTALLER" = 1 ]; then
    # the installer
    install -m 755 "$HERE/mrg5-emmc-install" "$R/usr/local/sbin/mrg5-emmc-install"
    install -m 644 "$HERE/mrg5-emmc-install.service" "$R/etc/systemd/system/"
    ln -sf /etc/systemd/system/mrg5-emmc-install.service "$R/etc/systemd/system/multi-user.target.wants/"
    # in the live system the installer owns the screen: no launcher, no console login on tty1,
    # no /DATA move
    live_off="mrg5-launcher.service getty@tty1.service mrg5-storage.service"
    # with CasaOS also Docker, CasaOS and devmon: they would start in the installer's RAM, and
    # devmon would mount the HDD the installer is about to erase
    [ "$CASAOS" = 1 ] && live_off="$live_off docker.service docker.socket containerd.service \
        casaos.service casaos-gateway.service casaos-message-bus.service casaos-local-storage.service \
        casaos-user-service.service casaos-app-management.service devmon@.service \
        mrg5-casaos-preset.service smartmontools.service"
    for u in $live_off; do
        install -d "$R/etc/systemd/system/$u.d"
        printf '[Unit]\n# not in the live installer (work/emmc-release)\nConditionPathIsMountPoint=!/live/medium\n' \
            > "$R/etc/systemd/system/$u.d/mrg5-not-live.conf"
    done
fi
if [ "$EDITION" = emmc-hdd ]; then
    # the overlay start (mrg5-overlay-init) as /sbin/init; Debian's link to systemd is diverted,
    # so a systemd-sysv update cannot put it back
    chroot "$R" dpkg-divert --local --rename --divert /sbin/init.systemd --add /sbin/init
    install -m 755 "$HERE/mrg5-overlay-init" "$R/sbin/init"
    install -m 755 "$HERE/mrg5-casaos-preset" "$R/usr/local/sbin/"
    install -m 644 "$HERE/mrg5-casaos-preset.service" "$R/etc/systemd/system/"
    ln -sf /etc/systemd/system/mrg5-casaos-preset.service "$R/etc/systemd/system/multi-user.target.wants/"
fi
if [ "$EDITION" = usb ]; then
    # first start: grow the root to the USB drive, CasaOS account and share
    install -m 755 "$HERE/mrg5-growroot" "$HERE/mrg5-casaos-preset" "$R/usr/local/sbin/"
    install -m 644 "$HERE/mrg5-growroot.service" "$HERE/mrg5-casaos-preset.service" "$R/etc/systemd/system/"
    for u in mrg5-growroot mrg5-casaos-preset; do
        ln -sf "/etc/systemd/system/$u.service" "$R/etc/systemd/system/multi-user.target.wants/"
    done
fi
if [ "$CASAOS" = 1 ]; then
    # container logs go to the journal (in RAM) instead of json-file logs on the drive
    mkdir -p "$R/etc/docker"
    python3 - "$R/etc/docker/daemon.json" <<'EOF'
import json, os, sys
p = sys.argv[1]
d = json.load(open(p)) if os.path.exists(p) and os.path.getsize(p) else {}
d["log-driver"] = "journald"
json.dump(d, open(p, "w"), indent=2)
EOF
fi
cat > "$R/etc/mrg5-release" <<EOF
version=$VERSION
edition=$EDITION
made=$(date -Is)
kernel=$KERNEL
dtb=$DTB
EOF
cleanup_chroot
trap - EXIT
# nothing personal may be left (the allow lists above should leave none; this is the check)
# no Quake game data in any release: it is downloaded on first use under id's licence
q=$(find "$R/usr/share/games/quake" "$R/usr/local/share/games" "$R/root" "$R/home" "$R/DATA" -xdev \
        -iname 'pak[0-9].pak' 2>/dev/null || true)
[ -z "$q" ] || die "Quake game data left in the copy: $(echo "$q" | xargs)"
step "checking the copy for personal data"
leaks=$(cd "$R" && {
    find root home DATA -xdev \( -iname cookies -o -iname 'login data*' -o -iname history \
        -o -iname 'web data' -o -iname '*.trashinfo' -o -name '.*_history' -o -name .kodi \
        -o -iname 'autosave-*' -o -iname 'content_*history.lpl' -o -iname '*.jpg' -o -iname '*.jpeg' \
        -o -iname '*.heic' -o -iname '*.mp4' -o -iname '*.mkv' -o -iname '*.srm' \) -print
    find var/lib/bluetooth var/lib/casaos/db -mindepth 1 -print
    ls etc/ssh/ssh_host_*
    [ "$KEEP_SSH_KEY" = 1 ] || find root/.ssh home/*/.ssh -print
} 2>/dev/null || true)     # find and ls fail on folders that are absent, which is the clean case
[ -z "$leaks" ] || die "personal data left in the copy: $(echo "$leaks" | head -20 | xargs)"
# and nothing that identifies the build system: its disks' serial numbers, its Ethernet and
# Bluetooth addresses, the addresses of the devices paired with it (headphones, pads, the remote;
# PulseAudio's state named them as bluez_sink.B8_B2_…) and its host name, in the usual spellings,
# in any file outside the packages
ids=$(mktemp)
{
    lsblk -dno SERIAL 2>/dev/null | grep -v '^ *$'
    # the Bluetooth adapter's address: BlueZ's folder name in /var/lib/bluetooth (no sysfs file);
    # the paired devices: the folders inside it
    mac='^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$'
    for a in $(cat /sys/class/net/eth0/address 2>/dev/null
               for d in $(ls /var/lib/bluetooth 2>/dev/null | grep -E "$mac"); do
                   echo "$d"; ls "/var/lib/bluetooth/$d" | grep -E "$mac"; done); do
        for c in "$(echo "$a" | tr A-F a-f)" "$(echo "$a" | tr a-f A-F)"; do
            echo "$c"; echo "$c" | tr -d :; echo "$c" | tr : _; done
    done
    hostname
} | sort -u > "$ids"
found=$(cd "$R" && grep -rlF -f "$ids" etc var root home DATA usr/local srv 2>/dev/null || true)
rm -f "$ids"
[ -z "$found" ] || die "the build system's identifiers left in the copy: $(echo "$found" | head -20 | xargs)"
echo "none found"
findmnt -rn -o TARGET | grep -q "^$R/" && die "mounts are left in $R: $(findmnt -rn -o TARGET | grep "^$R/" | xargs)"
du -sh "$STAGE" 2>/dev/null | cut -f1

# ---------------------------------------------------------------- boot files
step "boot files"
B=$OUT/Testapp6/BOOT
mkdir -p "$B"
cp "$BOOTDIR/$KERNEL" "$BOOTDIR/$DTB" "$B/"
if [ "$INSTALLER" = 1 ]; then
    mkdir -p "$OUT/Testapp6/live" "$OUT/Testapp6/emmc"
    # the installer: STARTUP once (BOLT writes flash0.nvram only when it is missing), then live
    {
        echo 'testenv STARTUP || setenv -p STARTUP "batch -fatfs emmcflash0.splash:Testapp6/BOOT/startup.ini";'
        sed -e "s|zImage-[A-Za-z0-9]*|$KERNEL|; s|dtb-[A-Za-z0-9-]*\.bin|$DTB|" \
            -e 's|^dt add prop /chosen mrg5,root s [A-Za-z0-9_-]*;|dt add prop /chosen mrg5,live s /Testapp6/live/rootfs.sqfs;|' \
            "$TEMPLATE"
    } > "$B/boot.ini"
    grep -q 'mrg5,live' "$B/boot.ini" || die "installer boot.ini has no live line"
    # the eMMC's own boot.ini and startup.ini (checks/42 §3a)
    sed -e "s|zImage-[A-Za-z0-9]*|$KERNEL|; s|dtb-[A-Za-z0-9-]*\.bin|$DTB|; s|usbdisk0:|emmcflash0.splash:|g" \
        -e "s|^dt add prop /chosen mrg5,root s [A-Za-z0-9_-]*;|dt add prop /chosen mrg5,root s $EMMC_LABEL;|" \
        "$TEMPLATE" > "$OUT/Testapp6/emmc/boot.ini"
    install -m 644 "$HERE/startup.ini" "$OUT/Testapp6/emmc/startup.ini"
    inis="$B/boot.ini $OUT/Testapp6/emmc/boot.ini"
else
    # USB Boot: BOLT's USB path, the root by label, nothing written to NOR
    sed -e "s|zImage-[A-Za-z0-9]*|$KERNEL|; s|dtb-[A-Za-z0-9-]*\.bin|$DTB|" \
        -e "s|^dt add prop /chosen mrg5,root s [A-Za-z0-9_-]*;|dt add prop /chosen mrg5,root s $USB_ROOT_LABEL;|" \
        "$TEMPLATE" > "$B/boot.ini"
    grep -q "mrg5,root s $USB_ROOT_LABEL;" "$B/boot.ini" || die "boot.ini has no root label line"
    # (setenv DT_ADDRESS sets a RAM variable; -p and unsetenv write flash0.nvram)
    grep -Eq 'setenv -p|unsetenv' "$B/boot.ini" && die "USB Boot's boot.ini must not write NOR"
    inis="$B/boot.ini"
fi
for f in $inis; do
    [ "$(wc -c < "$f")" -le 2048 ] || die "$f exceeds BOLT's 2048-byte buffer"
done

if [ "$INSTALLER" = 1 ]; then
    step "SquashFS image"
    mksquashfs "$STAGE" "$OUT/Testapp6/live/rootfs.sqfs" -comp zstd -Xcompression-level 15 \
        -b 256K -noappend -xattrs -no-progress
    ls -l "$OUT/Testapp6/live/rootfs.sqfs"
    sz=$(stat -c %s "$OUT/Testapp6/live/rootfs.sqfs")
    [ "$sz" -lt 4294967295 ] || die "rootfs.sqfs exceeds FAT32's 4 GiB file limit"
    rm -rf "$STAGE"
    (cd "$OUT" && find Testapp6 -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
    cat "$OUT/SHA256SUMS"
    du -sh "$OUT" | cut -f1
    step "done: pack $OUT with make-image.sh"
    exit 0
fi

# ------------------------------------------------------- USB Boot disk image
(cd "$OUT" && find Testapp6 -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
cat "$OUT/SHA256SUMS"
step "USB Boot disk image"
used=$(du -s -B1M "$STAGE" | cut -f1)
root_mb=$(( used + used / 10 + 512 ))  # MiB: the system, 10 % and 512 MiB; grown at the first start
mkdir -p "$IMGDIR"
IMG=$IMGDIR/magentatv-box-linux-usb-boot-$VERSION.img
rm -f "$IMG" "$IMG.xz" "$IMG.xz.sha256"
truncate -s $(( (1 + USB_FAT_MB + root_mb) * 1048576 )) "$IMG"
sfdisk -q "$IMG" <<EOF
label: dos
start=2048, size=${USB_FAT_MB}MiB, type=c, bootable
type=83
EOF
loop=$(losetup -f --show -P "$IMG")
M=$(mktemp -d)
cleanup_img() {
    umount "$M/boot" 2>/dev/null || true
    umount "$M/root" 2>/dev/null || true
    losetup -d "$loop" 2>/dev/null || true
}
trap cleanup_img EXIT
[ -b "${loop}p2" ] || die "image partitions did not appear"
mkfs.vfat -F 32 -s 8 -n "$USB_BOOT_LABEL" "${loop}p1" >/dev/null
mkfs.ext4 -F -q -L "$USB_ROOT_LABEL" -m 1 -E lazy_itable_init=0,lazy_journal_init=0 "${loop}p2"
mkdir -p "$M/boot" "$M/root"
mount -o noatime "${loop}p2" "$M/root"
tar -C "$STAGE" --create --numeric-owner --xattrs --xattrs-include='*' --acls --sparse --file=- . |
    tar -C "$M/root" --extract --numeric-owner --xattrs --xattrs-include='*' --acls \
        --same-permissions --file=-
[ -x "$M/root/lib/systemd/systemd" ] && [ -e "$M/root/mrg5/installed" ] || die "image root incomplete"
df -h "$M/root" | tail -1
umount "$M/root"
e2fsck -fn "${loop}p2"
mount "${loop}p1" "$M/boot"
cp -r "$OUT/Testapp6" "$OUT/SHA256SUMS" "$M/boot/"
sync
(cd "$M/boot" && sha256sum -c --quiet SHA256SUMS) || die "boot partition differs from SHA256SUMS"
umount "$M/boot"
fsck.vfat -n "${loop}p1" >/dev/null || die "fsck.vfat found errors"
losetup -d "$loop"
trap - EXIT
rmdir "$M/boot" "$M/root" "$M"
rm -rf "$STAGE"
sfdisk -d "$IMG"
xz -T4 -6 "$IMG"
(cd "$IMGDIR" && sha256sum "$(basename "$IMG").xz" > "$(basename "$IMG").xz.sha256")
ls -l "$IMG.xz"
cat "$IMG.xz.sha256"
step "done: $IMG.xz"
