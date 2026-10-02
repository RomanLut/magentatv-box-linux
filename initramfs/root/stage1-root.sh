#!/bin/sh
# Hand over from the rescue initramfs to the Debian system on the partition
# labelled MRG5ROOT (built by work/nas/build-rootfs.sh).
#
# boot.ini can name another label with a device-tree property, which BOLT adds
# before it starts the kernel:
#     dt add prop /chosen mrg5,root s MRG5USBROOT;
# That is how a stick made by work/usb-image/make-usb-stick.sh boots the root on
# itself even when the box also has an HDD with MRG5ROOT. Without the property
# the label is MRG5ROOT.
#
# Installed into the initramfs as /stage1-root.sh and sourced by /init-script
# (PID 1) once /dev, /proc and /sys are mounted and the console is attached.
#
# Stays in the rescue system (returns) when:
#   - no MRG5ROOT partition appears within 60 s,
#   - it cannot be mounted,
#   - it contains /mrg5/rescue,
#   - first-boot configuration fails (log: /debootstrap/debootstrap.log on it).
#
# First boot: runs debootstrap --second-stage and /mrg5/firstboot.sh natively
# inside the new root, then boots it.

bb=/bin/busybox

mrg5_root_label() {
    label=$($bb tr -d '\000' < /sys/firmware/devicetree/base/chosen/mrg5,root 2>/dev/null)
    case "$label" in
        ""|*[!A-Za-z0-9_-]*) label=MRG5ROOT ;;
    esac
    echo "$label"
}

mrg5_find_root() {
    $bb findfs LABEL="$root_label" 2>/dev/null
}

mrg5_undo_chroot_mounts() {
    $bb umount -l /newroot/dev 2>/dev/null
    $bb umount /newroot/sys 2>/dev/null
    $bb umount /newroot/proc 2>/dev/null
}

mrg5_root_handover() {
    # The root is normally on the internal SATA disk. It needs spin-up time,
    # and sata-retry enumerates it if the link comes up after the driver's
    # first probe (it never rebinds while a disk is attached).
    root_label=$(mrg5_root_label)
    echo "MRG5ROOT: looking for the root labelled $root_label"
    retry_pid=""
    if [ -d /sys/class/ata_port/ata1 ]; then
        sata-retry supervise &
        retry_pid=$!
    fi
    dev=""
    i=0
    while [ $i -lt 60 ]; do
        dev=$(mrg5_find_root)
        [ -n "$dev" ] && break
        $bb sleep 1
        i=$((i + 1))
    done
    [ -n "$retry_pid" ] && $bb kill "$retry_pid" 2>/dev/null
    if [ -z "$dev" ]; then
        echo "MRG5ROOT: no partition labelled $root_label, staying in the rescue system"
        return 0
    fi
    echo "MRG5ROOT: found $dev"

    $bb mkdir -p /newroot
    if ! $bb mount -t ext4 "$dev" /newroot; then
        echo "MRG5ROOT: mount of $dev failed, staying in the rescue system"
        return 0
    fi
    if [ -e /newroot/mrg5/rescue ]; then
        echo "MRG5ROOT: /mrg5/rescue present, staying in the rescue system"
        $bb umount /newroot
        return 0
    fi

    if [ -e /newroot/debootstrap/debootstrap ]; then
        echo "MRG5ROOT: first boot - configuring Debian, this takes several minutes"
        # PID 1 runs with PATH=/bin; debootstrap and dpkg inside the chroot need the sbin dirs.
        export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
        $bb mount -t proc proc /newroot/proc
        $bb mount -t sysfs sysfs /newroot/sys
        $bb mount -o rbind /dev /newroot/dev
        if ! $bb chroot /newroot /debootstrap/debootstrap --second-stage; then
            echo "MRG5ROOT: debootstrap second stage failed (see /debootstrap/debootstrap.log)"
            mrg5_undo_chroot_mounts
            $bb umount /newroot
            return 0
        fi
        if ! $bb chroot /newroot /bin/sh /mrg5/firstboot.sh; then
            echo "MRG5ROOT: /mrg5/firstboot.sh failed"
            mrg5_undo_chroot_mounts
            $bb umount /newroot
            return 0
        fi
        mrg5_undo_chroot_mounts
        $bb sync
    fi

    if [ ! -e /newroot/mrg5/installed ] || [ ! -e /newroot/lib/systemd/systemd ]; then
        echo "MRG5ROOT: $dev is not a configured MRG5 root, staying in the rescue system"
        $bb umount /newroot
        return 0
    fi

    echo "MRG5ROOT: switching to Debian on $dev"
    $bb umount /dev/pts 2>/dev/null
    $bb mount -o move /dev /newroot/dev
    $bb mount -o move /sys /newroot/sys
    $bb mount -o move /proc /newroot/proc
    exec $bb switch_root /newroot /sbin/init
}

# Live mode (work/emmc-release, the eMMC installer): boot.ini names a SquashFS image on a FAT
# partition instead of a root label,
#     dt add prop /chosen mrg5,live s /Testapp6/live/rootfs.sqfs;
# The image is mounted read-only through a loop device, with a tmpfs overlay for writes; the
# FAT stays mounted at /live/medium in the new root (the installer copies from it). The
# system's fstab root line names the installed root, so it is dropped from the live copy.
mrg5_live_image() {
    img=$($bb tr -d '\000' < /sys/firmware/devicetree/base/chosen/mrg5,live 2>/dev/null)
    case "$img" in
        /*) ;;
        *) img="" ;;
    esac
    case "$img" in
        *[!A-Za-z0-9_./-]*|*..*) img="" ;;
    esac
    echo "$img"
}

mrg5_live_handover() {
    img=$1
    echo "MRG5LIVE: looking for $img on a FAT partition"
    $bb mkdir -p /live/medium /live/rootfs /live/rw /newroot
    found=""
    i=0
    while [ $i -lt 60 ] && [ -z "$found" ]; do
        for dev in $($bb blkid | $bb grep 'TYPE="vfat"' | $bb cut -d: -f1); do
            $bb mount -t vfat -o ro "$dev" /live/medium 2>/dev/null || continue
            if [ -f "/live/medium$img" ]; then
                found=$dev
                break
            fi
            $bb umount /live/medium
        done
        [ -n "$found" ] && break
        $bb sleep 1
        i=$((i + 1))
    done
    if [ -z "$found" ]; then
        echo "MRG5LIVE: $img not found, staying in the rescue system"
        return 0
    fi
    echo "MRG5LIVE: found $img on $found"
    if ! $bb mount -t squashfs -o ro,loop "/live/medium$img" /live/rootfs; then
        echo "MRG5LIVE: cannot mount the image, staying in the rescue system"
        $bb umount /live/medium
        return 0
    fi
    $bb mount -t tmpfs -o mode=0755 tmpfs /live/rw
    $bb mkdir -p /live/rw/upper /live/rw/work
    if ! $bb mount -t overlay overlay \
            -o lowerdir=/live/rootfs,upperdir=/live/rw/upper,workdir=/live/rw/work /newroot ||
            [ ! -e /newroot/lib/systemd/systemd ]; then
        echo "MRG5LIVE: overlay failed, staying in the rescue system"
        return 0
    fi
    $bb grep -Ev '^[^#][^[:space:]]*[[:space:]]+/[[:space:]]' /newroot/etc/fstab > /newroot/etc/fstab.live
    $bb mv /newroot/etc/fstab.live /newroot/etc/fstab
    $bb mkdir -p /newroot/live/medium /newroot/live/rootfs /newroot/live/rw
    $bb mount -o move /live/medium /newroot/live/medium
    $bb mount -o move /live/rootfs /newroot/live/rootfs
    $bb mount -o move /live/rw /newroot/live/rw
    echo "MRG5LIVE: switching to the live system"
    $bb umount /dev/pts 2>/dev/null
    $bb mount -o move /dev /newroot/dev
    $bb mount -o move /sys /newroot/sys
    $bb mount -o move /proc /newroot/proc
    exec $bb switch_root /newroot /sbin/init
}

live_img=$(mrg5_live_image)
if [ -n "$live_img" ]; then
    mrg5_live_handover "$live_img"
else
    mrg5_root_handover
fi
