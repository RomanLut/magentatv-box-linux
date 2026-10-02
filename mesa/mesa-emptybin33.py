#!/usr/bin/env python3
"""Mesa v3dx_draw.c: no bin list without a draw (defect 27, checks/53 §5).

v3d_draw_vbo() starts the job's bin list (v3d_start_draw: Tile Binning Mode
Cfg, Start Tile Binning) and only then compiles the shaders and skips the draw
if one failed to compile ("fragment shader failed to compile. Expect
corruption."). A job whose only draw was skipped is submitted with a bin list
that bins nothing, and the render list branches into its empty tile lists. On
V3D 3.3 that job never completes: the render list runs to its end, the frame
is never counted, and the GPU is reset. A job with no bin list at all (a clear
alone) is fine.

A shader fails to compile on 3.3 when register allocation cannot fit it even at
one thread, since 3.3 cannot spill (defect 15): dEQP-GLES3
texture.units.all_units.only_cube.{1,2,7}, 24 cube samplers in one fragment
shader, one GPU reset each; cubeunits.c reproduces it.

The shaders are now compiled and checked before the bin list is started, so a
draw that cannot run leaves the job as it was.

usage: mesa-emptybin33.py <mesa src/gallium/drivers/v3d>
"""
import io
import os
import sys

p = os.path.join(sys.argv[1], "v3dx_draw.c")
s = io.open(p, encoding="utf-8").read()
if "defect 27" in s:
    print("v3dx_draw.c: already there")
    sys.exit(0)

EDITS = [
("""        v3d_start_draw(v3d);
        v3d_update_compiled_shaders(v3d, info->mode);
        if (!v3d_check_compiled_shaders(v3d))
                return;
""", """        /* checks/53 defect 27: compile and check before starting the bin
         * list - a job binning nothing never completes on V3D 3.3.
         */
        v3d_update_compiled_shaders(v3d, info->mode);
        if (!v3d_check_compiled_shaders(v3d))
                return;
        v3d_start_draw(v3d);
"""),
]
for old, new in EDITS:
    assert s.count(old) == 1, "anchor not found: " + old[:60]
    s = s.replace(old, new)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("v3dx_draw.c: applied")
