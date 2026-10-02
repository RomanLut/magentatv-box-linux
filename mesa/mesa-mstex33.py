#!/usr/bin/env python3
"""Mesa v3dx_state.c: texture types for multisampled textures on V3D 3.x
(defect 34, checks/53 §5).

A 3.x 4x colour buffer is stored raw, in its tile-buffer internal type and
bpp (defect 30's general stores), so v3d_create_texture_shader_state_bo()
picks the texture type for sampling it from the internal type - but only for
internal type 8 (RGBA8) and 16F (always RGBA16F); every other type hit
unreachable(), compiled out, and left texture type 0 (R8). Depth/stencil went
the same way: since defect 32 a 3.x multisampled Z/S buffer is stored through
the Z/S config in its output format, 32 bits per sample, but the blitter's
depth and stencil resolves read it through this branch too. With the Z/S
buffer at its real size (defect 32), those reads ran past its end: MMU faults
("pte invalid") in dEQP-GLES3 fbo.invalidate and fbo.msaa batches, e.g.
whole.unbind_blit_depth_stencil followed by whole.unbind_blit_msaa_color,
4 faults every time.

Now a depth/stencil resource takes the normal texture type of the view's
format, and a colour one the type that matches its internal type and bpp:
8 -> RGBA8, 8I/8UI -> RGBA8I/UI, 16F/16I/16UI -> RG16x (32 bpp) or RGBA16x,
32F/32I/32UI -> R32x, RG32x or RGBA32x.

usage: mesa-mstex33.py <mesa src/gallium/drivers/v3d>
"""
import io
import os
import sys

p = os.path.join(sys.argv[1], "v3dx_state.c")
s = io.open(p, encoding="utf-8").read()
if "defect 34" in s:
    print("v3dx_state.c: already there")
    sys.exit(0)

EDITS = [
("""                if (prsc->nr_samples > 1 && V3D_VERSION < 40) {""",
"""                /* checks/53 defect 34: a 3.x multisampled Z/S buffer is
                 * stored in its output format (defect 32), not raw.
                 */
                if (prsc->nr_samples > 1 && V3D_VERSION < 40 &&
                    !util_format_is_depth_or_stencil(prsc->format)) {"""),
("""                        switch (internal_type) {
                        case V3D_INTERNAL_TYPE_8:
                                tex.texture_type = TEXTURE_DATA_FORMAT_RGBA8;
                                break;
                        case V3D_INTERNAL_TYPE_16F:
                                tex.texture_type = TEXTURE_DATA_FORMAT_RGBA16F;
                                break;
                        default:
                                unreachable("Bad MSAA texture type");
                        }""",
"""                        /* checks/53 defect 34: the raw tile-buffer layout,
                         * by internal type and bpp.
                         */
                        bool bpp32 = internal_bpp == V3D_INTERNAL_BPP_32;
                        bool bpp64 = internal_bpp == V3D_INTERNAL_BPP_64;
                        switch (internal_type) {
                        case V3D_INTERNAL_TYPE_8:
                                tex.texture_type = TEXTURE_DATA_FORMAT_RGBA8;
                                break;
                        case V3D_INTERNAL_TYPE_8I:
                                tex.texture_type = TEXTURE_DATA_FORMAT_RGBA8I;
                                break;
                        case V3D_INTERNAL_TYPE_8UI:
                                tex.texture_type = TEXTURE_DATA_FORMAT_RGBA8UI;
                                break;
                        case V3D_INTERNAL_TYPE_16F:
                                tex.texture_type = bpp32 ? TEXTURE_DATA_FORMAT_RG16F :
                                                           TEXTURE_DATA_FORMAT_RGBA16F;
                                break;
                        case V3D_INTERNAL_TYPE_16I:
                                tex.texture_type = bpp32 ? TEXTURE_DATA_FORMAT_RG16I :
                                                           TEXTURE_DATA_FORMAT_RGBA16I;
                                break;
                        case V3D_INTERNAL_TYPE_16UI:
                                tex.texture_type = bpp32 ? TEXTURE_DATA_FORMAT_RG16UI :
                                                           TEXTURE_DATA_FORMAT_RGBA16UI;
                                break;
                        case V3D_INTERNAL_TYPE_32F:
                                tex.texture_type = bpp32 ? TEXTURE_DATA_FORMAT_R32F :
                                                   bpp64 ? TEXTURE_DATA_FORMAT_RG32F :
                                                           TEXTURE_DATA_FORMAT_RGBA32F;
                                break;
                        case V3D_INTERNAL_TYPE_32I:
                                tex.texture_type = bpp32 ? TEXTURE_DATA_FORMAT_R32I :
                                                   bpp64 ? TEXTURE_DATA_FORMAT_RG32I :
                                                           TEXTURE_DATA_FORMAT_RGBA32I;
                                break;
                        case V3D_INTERNAL_TYPE_32UI:
                                tex.texture_type = bpp32 ? TEXTURE_DATA_FORMAT_R32UI :
                                                   bpp64 ? TEXTURE_DATA_FORMAT_RG32UI :
                                                           TEXTURE_DATA_FORMAT_RGBA32UI;
                                break;
                        default:
                                tex.texture_type = v3d_get_tex_format(&screen->devinfo,
                                                                      cso->format);
                        }"""),
]
for old, new in EDITS:
    assert s.count(old) == 1, "anchor not found: " + old[:60]
    s = s.replace(old, new)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("v3dx_state.c: applied")
