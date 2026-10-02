#!/usr/bin/env python3
"""Mesa v3dx_format_table.c: sample float depth as DEPTH_COMP32F on V3D 3.x
too (defect 22, checks/53 §5).

The V3D 3.x format table textures PIPE_FORMAT_Z32_FLOAT (and
Z32_FLOAT_S8X24_UINT) as R32F; the 4.x table uses DEPTH_COMP32F. With depth
comparison enabled, v3d_get_tex_return_size() asks for 16-bit results, which
a 32-bit float colour format cannot deliver, and the TMU compares depth
formats only: every shadow lookup of a float depth texture failed -
dEQP-GLES3 texture.shadow.{2d,2d_array,cube}.*.*_depth_component32f, all
eight compare functions including always/never, 144 cases.

The texture data format enum Mesa uses for 3.3 (v3d_packet_v33.xml) has
DEPTH COMP32F (23) without a version limit. With it, 188 of the 191 dEQP-GLES3
float-depth cases pass (before: 44), non-shadow sampling included; the other
three are MSAA float depth, failing or unsupported before as well.

usage: mesa-d32f33.py <mesa src/src>
"""
import io
import os
import sys

p = os.path.join(sys.argv[1], "gallium/drivers/v3d/v3dx_format_table.c")
s = io.open(p, encoding="utf-8").read()
if "defect 22" in s:
    print("v3dx_format_table.c: already there")
    sys.exit(0)
EDITS = [
("""        FORMAT(Z32_FLOAT,         ZS_DEPTH_COMPONENT32F, R32F, SWIZ_XXXX, 32, 1),
""", """        /* checks/53 defect 22: DEPTH_COMP32F, as on 4.x - the TMU compares
         * depth formats only
         */
        FORMAT(Z32_FLOAT,         ZS_DEPTH_COMPONENT32F, DEPTH_COMP32F, SWIZ_XXXX, 32, 1),
"""),
("""        FORMAT(Z32_FLOAT_S8X24_UINT, ZS_DEPTH_COMPONENT32F, R32F, SWIZ_XXXX, 32, 1),
""", """        FORMAT(Z32_FLOAT_S8X24_UINT, ZS_DEPTH_COMPONENT32F, DEPTH_COMP32F, SWIZ_XXXX, 32, 1),
"""),
]
for old, new in EDITS:
    assert s.count(old) == 1, "anchor not found: " + old[:60]
    s = s.replace(old, new)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("v3dx_format_table.c: applied")
