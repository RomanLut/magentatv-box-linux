#!/bin/bash
# The two files the kernel builds in for the onboard Bluetooth chip (RTL8761ATV on UART1,
# brought up by hci_h5 + btrtl at boot, before any root file system):
#
#   rtl8761a_tv_fw.bin      Realtek's own TV firmware, as Realtek publishes it:
#                           Realtek-OpenSource/android_hardware_realtek, commit e58b611f,
#                           bt/rtkbt/Firmware/TV/rtl8761au_fw (fw_version 0x0e7afcd2)
#   rtl8761a_tv_config.bin  made by make-rtl8761a-config.py from the free RTL8761B config of
#                           linux-firmware (the UART entry: 1.5 Mbaud, flow control) plus the
#                           chip's further settings as values
#
#   firmware/fetch-firmware.sh <directory>     (kernel/build-kernel.sh passes .../firmware/rtl_bt)
#
# Neither file is kept in this repository; both are downloaded and checked by SHA-256.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
[ $# = 1 ] || { echo "usage: $0 <directory>" >&2; exit 1; }
D=$1
TV_C=e58b611f34f2f5ff57bb0d8cdf1b2e4751e3ccbd
TV_URL=https://raw.githubusercontent.com/Realtek-OpenSource/android_hardware_realtek/$TV_C/bt/rtkbt/Firmware/TV/rtl8761au_fw
TV_SHA=2ab2e795c2c797c26798cb607aeec2d37b7b306182df59ac31bbc54554c39fec
B_URL=https://git.kernel.org/pub/scm/linux/kernel/git/firmware/linux-firmware.git/plain/rtl_bt/rtl8761b_config.bin
B_SHA=6ddeb15f23588053e00cb08d25588bd7cf98d60fa93d9478efcef4ae8064a7ac
CONFIG_SHA=b323d9628b875c4a547af68967bb9cc94bc9a4478dbb37b1e73e4e530ae1ec13

mkdir -p "$D"
curl -fsSL --retry 3 -o "$D/rtl8761a_tv_fw.bin" "$TV_URL"
echo "$TV_SHA  $D/rtl8761a_tv_fw.bin" | sha256sum -c --quiet
curl -fsSL --retry 3 -o "$D/rtl8761b_config.bin" "$B_URL"
echo "$B_SHA  $D/rtl8761b_config.bin" | sha256sum -c --quiet
python3 "$HERE/make-rtl8761a-config.py" "$D/rtl8761b_config.bin" "$D/rtl8761a_tv_config.bin"
rm "$D/rtl8761b_config.bin"
# the same config as in the released kernel
echo "$CONFIG_SHA  $D/rtl8761a_tv_config.bin" | sha256sum -c --quiet
ls -l "$D"
