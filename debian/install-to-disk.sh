#!/bin/bash
# Write the MRG5 Debian root filesystem to a disk attached to the box
# (normally the internal SATA HDD).
#
# Run from Git Bash on the PC while the box runs our kernel's rescue system
# (no MRG5ROOT partition yet, so it stays in the initramfs with Dropbear SSH).
#
#   work/nas/install-to-disk.sh <box-ip> <device> --wipe
#   e.g. work/nas/install-to-disk.sh 192.168.3.60 /dev/sdb --wipe   (HDD; the boot stick is sda)
#
# ERASES <device>: one partition over the whole disk, the 3 GiB image written
# into it; Debian grows the filesystem to the partition on its first boot.
# Refuses the disk that holds the boot stick (Testapp6) and anything that is
# not a whole /dev/sdX disk.
set -euo pipefail

BOX=${1:?box ip}
DEV=${2:?device, e.g. /dev/sdb}
[ "${3:-}" = "--wipe" ] || { echo "add --wipe to confirm erasing $DEV"; exit 1; }
case "$DEV" in /dev/sd[a-z]) ;; *) echo "refusing $DEV: expected a whole disk /dev/sdX"; exit 1 ;; esac

HERE=$(cd "$(dirname "$0")" && pwd)
KEY=$HERE/../mrg5-test_ssh_ed25519
SSH="ssh -i $KEY -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@$BOX"
IMG_GZ='~/mrg5-rootfs/out/mrg5root.img.gz'
N=${DEV#/dev/}

echo "== disks on the box"
$SSH "cat /proc/partitions; /bin/busybox blkid"

echo "== safety checks on $DEV"
$SSH "
set -e
bb=/bin/busybox
[ -b $DEV ] || { echo 'no such disk: $DEV'; exit 1; }
if \$bb grep -q '^$DEV' /proc/mounts; then echo '$DEV is mounted'; exit 1; fi
\$bb mkdir -p /tmp/probe
for p in /dev/${N}[0-9]*; do
    [ -b \"\$p\" ] || continue
    if \$bb mount -o ro \"\$p\" /tmp/probe 2>/dev/null; then
        if [ -d /tmp/probe/Testapp6 ]; then \$bb umount /tmp/probe; echo \"\$p holds Testapp6 (boot stick) - refusing\"; exit 1; fi
        \$bb umount /tmp/probe
    fi
done
echo ok
"

echo "== clearing old partition tables on $DEV (MBR/GPT at the start, backup GPT at the end)"
$SSH "
bb=/bin/busybox
sectors=\$(\$bb cat /sys/block/$N/size)
\$bb dd if=/dev/zero of=$DEV bs=512 count=2048 2>/dev/null
\$bb dd if=/dev/zero of=$DEV bs=512 seek=\$((sectors - 2048)) count=2048 2>/dev/null
\$bb sync
echo \"cleared (\$sectors sectors)\"
"

echo "== partitioning $DEV (one Linux partition from sector 2048 - 4K-aligned - to the end)"
$SSH "printf 'o\nn\np\n1\n2048\n\nw\n' | /bin/busybox fdisk $DEV; /bin/busybox sync; /bin/busybox sleep 2; /bin/busybox ls -l ${DEV}1"

echo "== writing image to ${DEV}1"
wsl.exe -e bash -lc "cat $IMG_GZ" | $SSH "/bin/busybox gzip -dc > ${DEV}1 && /bin/busybox sync && echo written"

echo "== result"
$SSH "/bin/busybox blkid ${DEV}1"
echo "Reboot the box (ssh ... reboot); the initramfs finds MRG5ROOT and runs the first-boot setup."
