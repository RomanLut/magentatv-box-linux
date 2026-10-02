#!/usr/bin/env python3
"""Mesa: multisampled depth/stencil on V3D 3.x as the vendor driver does it
(defect 32, checks/53 §5).

Mesa kept a 4x depth24/stencil8 buffer on 3.x as a raw image: the bytes per
pixel multiplied by the sample count on top of the doubled width and height
(v3d_resource.c), a raw Store Tile Buffer General of Z+stencil after the
colour store and raw general loads of Z or stencil. The raw Z/S general loads
and stores do not work on 3.3 (Mesa's own comment: "Can't do raw ZSTENCIL
loads/stores"): with a depth/stencil attachment a 4x framebuffer came out
wrong as soon as it had more than one tile - a half-screen quad covered the
whole target (msstencil.c) - and dEQP-GLES3 multisample.fbo_*.stencil and the
fbo.msaa depth/stencil cases failed.

The vendor driver's render lists for the same scenario (stockms.c on the
stock system, stockms-{one,two}.txt; its result is exact):
- the Z/S buffer has the colour buffer's layout, 2x2 samples of 32 bits per
  pixel (padded height 20 UIF blocks for 96x80), no extra bytes per pixel;
- Tile Rendering Mode Cfg (Z/Stencil) with Decimate mode 3 (all samples);
- per tile: the colour through a raw Store Tile Buffer General, then Tile
  Coordinates Implicit and the ordinary Store Multi-Sample Resolved Tile
  Color Buffer, which writes Z/S through that config;
- a job that reloads Z/S does it with Reload Tile Color Buffer (Z and stencil
  load enabled), the colour with a raw Load Tile Buffer General.
Mesa's non-MSAA 3.x path already stores and reloads Z/S that way, so here the
multisampled combined buffer simply takes it too, with the all-samples
decimate mode; the raw general path stays only for a separate stencil buffer.

usage: mesa-mszs33.py <mesa src/gallium/drivers/v3d>
"""
import io
import os
import sys

FILES = {
"v3d_resource.c": [
("""                rsc->cpp = util_format_get_blocksize(prsc->format);
                if (screen->devinfo.ver < 40 && prsc->nr_samples > 1)
                        rsc->cpp *= prsc->nr_samples;
""", """                /* checks/53 defect 32: a 3.x multisampled depth/stencil
                 * buffer holds 2x2 samples per pixel like a colour buffer
                 * (the slices are already twice the size), as the vendor
                 * driver lays it out.
                 */
                rsc->cpp = util_format_get_blocksize(prsc->format);
"""),
],
"v3dx_rcl.c": [
("""                assert(surf->tiling != V3D_TILING_RASTER);
                zs.memory_format = surf->tiling;
        }
""", """                assert(surf->tiling != V3D_TILING_RASTER);
                zs.memory_format = surf->tiling;

                /* checks/53 defect 32: all samples, as the vendor */
                if (rsc->base.nr_samples > 1)
                        zs.decimate_mode = V3D_DECIMATE_MODE_ALL_SAMPLES;
        }
"""),
("""        if ((loads_pending & PIPE_CLEAR_DEPTHSTENCIL) &&
            (V3D_VERSION >= 40 ||
             (job->zsbuf && job->zsbuf->texture->nr_samples > 1))) {""",
"""        /* checks/53 defect 32: on 3.x only a separate stencil buffer takes
         * the raw general load; a combined one is reloaded with Reload Tile
         * Color Buffer through the Z/S config, as the vendor does.
         */
        if ((loads_pending & PIPE_CLEAR_DEPTHSTENCIL) &&
            (V3D_VERSION >= 40 ||
             (job->zsbuf && job->zsbuf->texture->nr_samples > 1 &&
              v3d_resource(job->zsbuf->texture)->separate_stencil))) {"""),
("""        if (job->store & PIPE_CLEAR_DEPTHSTENCIL && job->zsbuf &&
            !(V3D_VERSION < 40 && job->zsbuf->texture->nr_samples <= 1)) {""",
"""        /* checks/53 defect 32: likewise the store - the final Store
         * Multi-Sample Resolved writes a combined 3.x Z/S buffer.
         */
        if (job->store & PIPE_CLEAR_DEPTHSTENCIL && job->zsbuf &&
            !(V3D_VERSION < 40 &&
              (job->zsbuf->texture->nr_samples <= 1 ||
               !v3d_resource(job->zsbuf->texture)->separate_stencil))) {"""),
],
}

for name, edits in FILES.items():
    p = os.path.join(sys.argv[1], name)
    s = io.open(p, encoding="utf-8").read()
    if "defect 32" in s:
        print(name + ": already there")
        continue
    for old, new in edits:
        assert s.count(old) == 1, name + ": anchor not found: " + old[:60]
        s = s.replace(old, new)
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)
    print(name + ": applied")
