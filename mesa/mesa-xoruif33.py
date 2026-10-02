#!/usr/bin/env python3
"""Mesa v3dx_rcl.c: the XOR UIF bit of the 3.x general tile loads and stores
(defect 30, checks/53 §5).

On V3D 3.3 Load/Store Tile Buffer General move a tile buffer in raw mode to a
UIF image, with the image's padded height and an "XOR UIF" bit
(v3d_packet_v33.xml). v3d_resource_setup_slices() gives a level the XOR
layout when its padded height is a multiple of the page cache
(V3D_TILING_UIF_XOR, "the HW will use the XOR bit on odd columns"); the 4.x
branch passes the tiling as the memory format, but the 3.x branch never set
the bit, so every raw load or store of an XOR surface swapped alternate
column groups. The general loads and stores are what 3.3 uses for
multisampled render targets and separate depth/stencil, and a 4x surface is
twice the size - 256x256 at 4x is 512 rows, an XOR layout: dEQP-GLES3
rasterization.fbo.rbo_multisample_* drew triangles with every other band of
columns missing after the resolve.

The bit is now set from the surface's tiling for both.

usage: mesa-xoruif33.py <mesa src/gallium/drivers/v3d>
"""
import io
import os
import sys

p = os.path.join(sys.argv[1], "v3dx_rcl.c")
s = io.open(p, encoding="utf-8").read()
if "defect 30" in s:
    print("v3dx_rcl.c: already there")
    sys.exit(0)

EDITS = [
("""                assert(buffer != ZSTENCIL);
                load.raw_mode = true;
                load.padded_height_of_output_image_in_uif_blocks =
                        surf->padded_height_of_output_image_in_uif_blocks;
""", """                assert(buffer != ZSTENCIL);
                load.raw_mode = true;
                load.padded_height_of_output_image_in_uif_blocks =
                        surf->padded_height_of_output_image_in_uif_blocks;
                /* checks/53 defect 30 */
                load.xor_uif = surf->tiling == V3D_TILING_UIF_XOR;
"""),
("""                assert(buffer != ZSTENCIL);
                store.raw_mode = true;
""", """                assert(buffer != ZSTENCIL);
                store.raw_mode = true;
                /* checks/53 defect 30 */
                store.xor_uif = surf->tiling == V3D_TILING_UIF_XOR;
"""),
]
for old, new in EDITS:
    assert s.count(old) == 1, "anchor not found: " + old[:60]
    s = s.replace(old, new)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("v3dx_rcl.c: applied")
