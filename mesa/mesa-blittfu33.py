#!/usr/bin/env python3
"""Mesa v3d_blit.c: make the render blit's tiled copy of a linear source with
the TFU (defect 36, checks/53 §5).

The texture unit cannot sample linear memory, so v3d_render_blit first copies
a linear source into a tiled temporary with ctx->resource_copy_region, which
is util_resource_copy_region: a CPU map and memcpy of the whole level out of
uncached GPU memory. On this box every window buffer is linear (the mrg5
display scans out linear only), so every glCopyTexSubImage2D or glBlitFramebuffer
from the window converts the whole 1920x1080 frame in software. Quake
(quakespasm, r_oldwater 0) does one per visible warp texture per frame: the
start map ran at ~5 fps with the engine's thread in __memcpy_neon under
v3d_blit in every sample. Upstream (main) has the same code; a Pi 4's
display takes tiled buffers, so it rarely gets there.

The same whole-level linear-to-tiled conversion is what the TFU already does
for glamor's shadow copies (§9 item 12, ~4 ms for 1920x1080). v3d_tfu() is
an exact copy at one size and format, which is what the temporary is; it
returns false where it cannot (TFU not usable on this kernel, format), and
the CPU copy stays as the fallback.

usage: mesa-blittfu33.py <mesa src/gallium/drivers/v3d>
"""
import io
import os
import sys

p = os.path.join(sys.argv[1], "v3d_blit.c")
s = io.open(p, encoding="utf-8").read()
if "defect 36" in s:
    print("v3d_blit.c: already there")
    sys.exit(0)

EDITS = [
("""static void
v3d_render_blit(struct pipe_context *ctx, struct pipe_blit_info *info)
{
""", """static bool
v3d_tfu(struct pipe_context *pctx,
        struct pipe_resource *pdst,
        struct pipe_resource *psrc,
        unsigned int src_level,
        unsigned int base_level,
        unsigned int last_level,
        unsigned int src_layer,
        unsigned int dst_layer,
        bool for_mipmap);

static void
v3d_render_blit(struct pipe_context *ctx, struct pipe_blit_info *info)
{
"""),
("""                ctx->resource_copy_region(ctx,
                                          tiled, 0,
                                          0, 0, 0,
                                          info->src.resource, info->src.level,
                                          &box);
                info->src.level = 0;
""", """                /* checks/53 defect 36: convert with the TFU; the CPU copy
                 * reads the whole level out of uncached memory.
                 */
                if ((tmpl.target != PIPE_TEXTURE_2D &&
                     tmpl.target != PIPE_TEXTURE_RECT) ||
                    !v3d_tfu(ctx, tiled, info->src.resource,
                             info->src.level, 0, 0, 0, 0, false)) {
                        ctx->resource_copy_region(ctx,
                                                  tiled, 0,
                                                  0, 0, 0,
                                                  info->src.resource,
                                                  info->src.level,
                                                  &box);
                }
                info->src.level = 0;
"""),
]
for old, new in EDITS:
    assert s.count(old) == 1, "anchor not found: " + old[:60]
    s = s.replace(old, new)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("v3d_blit.c: applied")
