#!/usr/bin/env python3
"""modesetting + msdri3: read GL clients' frames through a cached mapping
(checks/53 §9 item 13).

A GL client in a window (not flipped) hands X each frame as a DRI3 pixmap, and
Present copies it into the window with CopyArea on the CPU. msdri3 maps that
buffer through GBM, which on the MRG5 is write-combined: 227 ms per 1920x1080
frame. The display driver (mrg5_drm, zImage-smp5q) maps a *read-only* mmap of
its dma-bufs cached and keeps the cache right in begin/end_cpu_access, which
the DMA_BUF_IOCTL_SYNC ioctl calls: 1 ms sync + 6 ms copy.

Here X keeps, for every imported client pixmap, a dup of its dma-buf fd and a
read-only mapping of it. A wrapped CopyArea reads from such a pixmap through
that mapping, bracketed by DMA_BUF_SYNC_START|READ and END|READ (the dma-buf
rule for CPU access; START also waits for the GPU's fence). The pixmap's own
read-write mapping stays as it was for everything else, so X can still draw
into client pixmaps. With an exporter that has no cached mapping the extra
mapping is just another uncached one and the sync a no-op.

usage: mrg5-msdri3-cachedread.py <xorg-server source tree>
"""
import io
import os
import sys

MARK = "MRG5 (checks/53): cached read"
ms = os.path.join(sys.argv[1], "hw/xfree86/drivers/modesetting")


def patch(name, pairs):
    p = os.path.join(ms, name)
    s = io.open(p, encoding="utf-8").read()
    if MARK in s:
        print(name + ": already there")
        return
    for old, new in pairs:
        assert s.count(old) == 1, (name, old[:60])
        s = s.replace(old, new)
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)
    print(name + ": applied")


patch("drmmode_display.h", [(
"""    struct gbm_bo *bo;
    void *bo_map;
    Bool use_modifiers;
#endif
} msPixmapPrivRec, *msPixmapPrivPtr;
""",
"""    struct gbm_bo *bo;
    void *bo_map;
    Bool use_modifiers;
    /* MRG5 (checks/53): cached read - an imported client buffer's dma-buf
     * (dup) and its read-only mapping, used by ms_dri3_copy_area */
    void *ro_map;
    size_t ro_size;
    int ro_fd;
#endif
} msPixmapPrivRec, *msPixmapPrivPtr;
""")])

patch("driver.h", [(
"""Bool ms_dri3_screen_init(ScreenPtr screen);
""",
"""Bool ms_dri3_screen_init(ScreenPtr screen);
void ms_dri3_close_screen(ScreenPtr screen); /* MRG5 (checks/53): cached read */
void ms_dri3_wrap_gc(ScreenPtr screen);
""")])

patch("driver.c", [(
"""    if (!fbScreenInit(pScreen, NULL,
                      pScrn->virtualX, pScrn->virtualY,
                      pScrn->xDpi, pScrn->yDpi,
                      pScrn->displayWidth, pScrn->bitsPerPixel))
        return FALSE;
""",
"""    if (!fbScreenInit(pScreen, NULL,
                      pScrn->virtualX, pScrn->virtualY,
                      pScrn->xDpi, pScrn->yDpi,
                      pScrn->displayWidth, pScrn->bitsPerPixel))
        return FALSE;
#ifdef MS_DRI3
    /* MRG5 (checks/53): cached read - on fb's GCs, below the damage layer
     * (miDCInitialize), which puts its own ops back after every call */
    ms_dri3_wrap_gc(pScreen);
#endif
"""), (
"""#ifdef MS_DRI3
    if (ms->drmmode.dri3_enabled)
        pScreen->DestroyPixmap = ms->drmmode.destroy_pixmap;
#endif
""",
"""#ifdef MS_DRI3
    if (ms->drmmode.dri3_enabled)
        pScreen->DestroyPixmap = ms->drmmode.destroy_pixmap;
    ms_dri3_close_screen(pScreen); /* MRG5 (checks/53): cached read */
#endif
""")])

patch("dri3.c", [
(
"""#include <sys/mman.h>
#include <sys/ioctl.h>
""",
"""#include <sys/mman.h>
#include <sys/ioctl.h>
#include <linux/dma-buf.h>
#include "gcstruct.h"
"""),
(
"""static Bool
ms_dri3_pixmap_make_exportable(PixmapPtr pixmap, Bool mods)
""",
"""/* MRG5 (checks/53): cached read.
 * A read-only mapping of an imported client buffer's dma-buf, next to the
 * read-write GBM mapping the pixmap keeps. mrg5_drm maps it cached.
 */
static void
ms_dri3_map_readonly(msPixmapPrivPtr ppriv, int fd, size_t size)
{
    int dfd = fcntl(fd, F_DUPFD_CLOEXEC, 3);
    void *map;

    if (dfd < 0)
        return;
    map = mmap(NULL, size, PROT_READ, MAP_SHARED, dfd, 0);
    if (map == MAP_FAILED) {
        close(dfd);
        return;
    }
    ppriv->ro_map = map;
    ppriv->ro_size = size;
    ppriv->ro_fd = dfd;
}

static void
ms_dri3_unmap_readonly(msPixmapPrivPtr ppriv)
{
    if (!ppriv->ro_map)
        return;
    munmap(ppriv->ro_map, ppriv->ro_size);
    close(ppriv->ro_fd);
    ppriv->ro_map = NULL;
}

static CreateGCProcPtr ms_dri3_create_gc_orig;
static const GCOps *ms_dri3_fb_ops;
static GCOps ms_dri3_gc_ops;

/* CopyArea from an imported client pixmap reads through the cached mapping,
 * between DMA_BUF_SYNC_START|READ (waits for the GPU, invalidates the CPU
 * cache) and END|READ. Present copies a windowed client's frame this way.
 */
static RegionPtr
ms_dri3_copy_area(DrawablePtr src, DrawablePtr dst, GCPtr gc,
                  int sx, int sy, int w, int h, int dx, int dy)
{
    ScrnInfoPtr scrn = xf86ScreenToScrn(src->pScreen);
    modesettingPtr ms = modesettingPTR(scrn);
    struct dma_buf_sync sync = { DMA_BUF_SYNC_START | DMA_BUF_SYNC_READ };
    msPixmapPrivPtr ppriv;
    PixmapPtr pix;
    RegionPtr ret;
    void *rw;

    if (src->type != DRAWABLE_PIXMAP || src == dst)
        return ms_dri3_fb_ops->CopyArea(src, dst, gc, sx, sy, w, h, dx, dy);
    pix = (PixmapPtr) src;
    ppriv = msGetPixmapPriv(&ms->drmmode, pix);
    if (!ppriv || !ppriv->ro_map ||
        drmIoctl(ppriv->ro_fd, DMA_BUF_IOCTL_SYNC, &sync))
        return ms_dri3_fb_ops->CopyArea(src, dst, gc, sx, sy, w, h, dx, dy);

    rw = pix->devPrivate.ptr;
    pix->devPrivate.ptr = ppriv->ro_map;
    ret = ms_dri3_fb_ops->CopyArea(src, dst, gc, sx, sy, w, h, dx, dy);
    pix->devPrivate.ptr = rw;

    sync.flags = DMA_BUF_SYNC_END | DMA_BUF_SYNC_READ;
    drmIoctl(ppriv->ro_fd, DMA_BUF_IOCTL_SYNC, &sync);
    return ret;
}

/* Directly on fbCreateGC (ms_dri3_wrap_gc runs right after fbScreenInit):
 * fb sets gc->ops once, there; the damage layer above wraps each GC and puts
 * back the ops it found underneath, ours, after every call. */
static Bool
ms_dri3_create_gc(GCPtr gc)
{
    Bool ret = ms_dri3_create_gc_orig(gc);

    if (!ret)
        return ret;
    if (!ms_dri3_fb_ops) {
        ms_dri3_fb_ops = gc->ops;
        ms_dri3_gc_ops = *gc->ops;
        ms_dri3_gc_ops.CopyArea = ms_dri3_copy_area;
    }
    if (gc->ops == ms_dri3_fb_ops)
        gc->ops = &ms_dri3_gc_ops;
    return ret;
}

void
ms_dri3_wrap_gc(ScreenPtr screen)
{
    ms_dri3_create_gc_orig = screen->CreateGC;
    screen->CreateGC = ms_dri3_create_gc;
}

void
ms_dri3_close_screen(ScreenPtr screen)
{
    if (ms_dri3_create_gc_orig)
        screen->CreateGC = ms_dri3_create_gc_orig;
    ms_dri3_create_gc_orig = NULL;
    ms_dri3_fb_ops = NULL;
}

static Bool
ms_dri3_pixmap_make_exportable(PixmapPtr pixmap, Bool mods)
"""),
(
"""    if (!screen->SetSharedPixmapBacking(pixmap, (void *)(intptr_t)fds[0]))
       ret = FALSE;

map_fail:
""",
"""    /* MRG5 (checks/53): cached read - single-plane buffers only; before
     * SetSharedPixmapBacking, which closes fds[0] (drmmode_SetSlaveBO) */
    if (ret && num == 1 && (modifier == DRM_FORMAT_MOD_INVALID || offsets[0] == 0))
       ms_dri3_map_readonly(msGetPixmapPriv(&ms->drmmode, pixmap), fds[0],
                            (size_t) strides[0] * height);

    if (!screen->SetSharedPixmapBacking(pixmap, (void *)(intptr_t)fds[0]))
       ret = FALSE;

map_fail:
"""),
(
"""map_fail:
    if (ret == FALSE) {
       fbDestroyPixmap(pixmap);
""",
"""map_fail:
    if (ret == FALSE) {
       ms_dri3_unmap_readonly(msGetPixmapPriv(&ms->drmmode, pixmap));
       fbDestroyPixmap(pixmap);
"""),
(
"""      if (ppriv && ppriv->bo) {
         gbm_bo_unmap(ppriv->bo, ppriv->bo_map);
         gbm_bo_destroy(ppriv->bo);
      }
""",
"""      if (ppriv && ppriv->bo) {
         gbm_bo_unmap(ppriv->bo, ppriv->bo_map);
         gbm_bo_destroy(ppriv->bo);
      }
      if (ppriv)
         ms_dri3_unmap_readonly(ppriv); /* MRG5 (checks/53): cached read */
"""),
(
"""    tmp_bo = bpriv->bo;
    tmp_map = bpriv->bo_map;
    tmp_mod = bpriv->use_modifiers;
""",
"""    tmp_bo = bpriv->bo;
    tmp_map = bpriv->bo_map;
    tmp_mod = bpriv->use_modifiers;

    /* MRG5 (checks/53): cached read - the read-only mapping follows its bo */
    {
        void *m = bpriv->ro_map;
        size_t sz = bpriv->ro_size;
        int f = bpriv->ro_fd;

        bpriv->ro_map = fpriv->ro_map;
        bpriv->ro_size = fpriv->ro_size;
        bpriv->ro_fd = fpriv->ro_fd;
        fpriv->ro_map = m;
        fpriv->ro_size = sz;
        fpriv->ro_fd = f;
    }
"""),
(
"""    ms->drmmode.destroy_pixmap = screen->DestroyPixmap;
    screen->DestroyPixmap = ms_dri3_destroy_pixmap;
""",
"""    ms->drmmode.destroy_pixmap = screen->DestroyPixmap;
    screen->DestroyPixmap = ms_dri3_destroy_pixmap;
    /* MRG5 (checks/53): cached read - CopyArea is wrapped in ms_dri3_wrap_gc */
"""),
])
