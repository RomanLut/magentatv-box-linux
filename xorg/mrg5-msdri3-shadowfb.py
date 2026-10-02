#!/usr/bin/env python3
"""modesetting + msdri3: honour Option "ShadowFB" (checks/53 §6).

Raspberry Pi's msdri3 patch (0003-modesetting-Add-DRI3-support-to-...)
evaluates ShadowFB only when neither glamor nor msdri3 is on, so with msdri3 X
always draws straight into the dumb scanout buffer. On the MRG5 that buffer is
write-combined (uncached) memory: writes are cheap, but every read of the
screen - window moves, scrolling, GetImage, restoring what a menu covered -
runs at uncached speed (x11perf -copywinwin500 29.6 ms, -getimage500 32.5 ms,
against -rect500 1.5 ms).

modesetting's own ShadowFB is the stock answer for such buffers: the screen
pixmap lives in cached RAM, and only damaged areas are copied into the scanout
buffer (msUpdatePacked -> msShadowWindow, pure writes). None of that code
depends on glamor/msdri3; only the option read did. This reads it in the
msdri3 case too, default off, so without the option nothing changes.

Page flips keep working, with one change in present.c: modesetting unflips
by flipping back to the screen pixmap, and for that msdri3 exports it
(ms_dri3_gbm_bo_from_pixmap -> make_exportable), which moves the pixmap - with
ShadowFB, the cached shadow itself - into a write-combined GBM buffer for
good. From then on every draw and every shadow update reads uncached memory
(X at 100 % of a core for a 1280x800 video window, checks/53). With ShadowFB
the unflip takes modesetting's own fallback instead: it sets the mode on the
front buffer, which the shadow updates kept current. Upstream never meets
this case: without glamor it has neither DRI3 nor flips.

usage: mrg5-msdri3-shadowfb.py <xorg-server source tree>
"""
import io
import os
import sys


MARK = "MRG5 (checks/53): ShadowFB with msdri3"
ms = os.path.join(sys.argv[1], "hw/xfree86/drivers/modesetting")


def patch(name, old, new):
    p = os.path.join(ms, name)
    s = io.open(p, encoding="utf-8").read()
    if MARK in s:
        print(name + ": already there")
        return
    assert s.count(old) == 1, name + ": anchor not found"
    io.open(p, "w", encoding="utf-8", newline="\n").write(s.replace(old, new))
    print(name + ": applied")


old = """    ms->drmmode.pageflip =
        xf86ReturnOptValBool(ms->drmmode.Options, OPTION_PAGEFLIP, TRUE);
"""
patch("driver.c", old, """#ifdef MS_DRI3
    /* MRG5 (checks/53): ShadowFB with msdri3 - the scanout buffer is
     * uncached, so let X draw into a cached shadow and copy only damage out.
     * Off unless Option "ShadowFB" is set.
     */
    if (!ms->drmmode.glamor && ms->drmmode.dri3_enabled) {
        ms->drmmode.shadow_enable =
            xf86ReturnOptValBool(ms->drmmode.Options, OPTION_SHADOW_FB, FALSE);
        xf86DrvMsg(pScrn->scrnIndex, X_INFO, "ShadowFB with msdri3: %s\\n",
                   ms->drmmode.shadow_enable ? "enabled" : "disabled");
        ms->drmmode.shadow_enable2 = msShouldDoubleShadow(pScrn, ms);
    }
#endif

""" + old)

old = """    if (!ms->drmmode.pageflip)
        return FALSE;

    if (ms->drmmode.dri2_flipping)
        return FALSE;
"""
patch("present.c", old, old + """
#ifdef MS_DRI3
    /* MRG5 (checks/53): ShadowFB with msdri3 - never flip to the screen
     * pixmap: it is the cached shadow, and exporting it for the flip would
     * move it into uncached GPU memory for good. ms_present_unflip then sets
     * the mode on the front buffer, which the shadow updates keep current.
     */
    if (ms->drmmode.shadow_enable && !ms->drmmode.glamor &&
        pixmap == screen->GetScreenPixmap(screen))
        return FALSE;
#endif
""")
