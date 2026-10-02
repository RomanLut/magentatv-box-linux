#!/bin/sh
# desktop-accel.sh on|off|status - choose the X config start-desktop.sh uses:
#   on   99-mrg5-kms.conf: modesetting on card1, msdri3 (CPU desktop, V3D for GL
#        clients through DRI3), page flips and ShadowFB
#   off  99-mrg5-fbdev.conf: the unaccelerated fbdev path (checks/41)
# Takes effect at the next desktop start.  Both files live in /root; exactly
# one of them is copied into /etc/X11/xorg.conf.d (checks/53 §6).
#
# libshadow.so goes with the config: the fbdev path needs the patched
# /root/libshadow-opaque.so (it forces every pixel's alpha to 0xff, checks/41);
# the KMS path needs Debian's own /root/libshadow-orig.so - its display ignores
# per-pixel alpha, and ShadowFB copies every damaged area through libshadow, so
# the patched per-pixel loop made window drags lag (checks/53 §6).
D=/etc/X11/xorg.conf.d
L=/usr/lib/xorg/modules/libshadow.so
case "${1:-status}" in
on)  rm -f $D/99-mrg5-fbdev.conf; cp /root/99-mrg5-kms.conf $D/
     cp /root/libshadow-orig.so $L ;;
off) rm -f $D/99-mrg5-kms.conf; cp /root/99-mrg5-fbdev.conf $D/
     cp /root/libshadow-opaque.so $L ;;
status) ;;
*) echo "usage: $0 on|off|status"; exit 1 ;;
esac
ls $D
case "$(sha256sum $L | cut -c1-16)" in
c71919a0b1cf60db) echo "libshadow.so: Debian's (KMS path)" ;;
2d99782f24bb9a19) echo "libshadow.so: opaque-alpha patch (fbdev path)" ;;
*) echo "libshadow.so: unknown ($(sha256sum $L | cut -c1-16))" ;;
esac
