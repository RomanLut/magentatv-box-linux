#!/usr/bin/env python3
"""Mesa v3d33_tex.c: pad 1D lookups at the end, not after s (defect 18,
checks/53 §5).

On V3D 3.3 the two TMU configuration words ride on the first two parameter
writes (v3d33_vir_emit_tex(): "if (i < 2) tmu->uniform = texture_u[i]"), so a
lookup needs at least two writes. For a 1D texture (lookup type "Texture 1D",
v3d_packet_v33.xml Lookup Type = 4) Mesa guarantees that with a dummy t = 0.5
inserted right after s - but in 1D mode the value after s is the next
parameter, so a shadow lookup took the dummy as its depth reference and the
real reference one parameter later. Every shadow1D test failed (piglit
glsl-1.10 samplers glsl-fs-shadow1D*, arb_fragment_program_shadow
tex/txp-shadow1d; results inverted). Tried and rejected: no dummy at all
breaks plain 1D lookups (texture1D.shader_test: only one write, so no p1);
looking 1D up as "Texture 2D" breaks both.

Now the dummy is added after all parameters, and only when fewer than two
values would be written: a plain 1D lookup still gets s + dummy, a shadow,
bias or lod 1D lookup writes s and its parameters only.

usage: mesa-tex1d33.py <mesa src/broadcom/compiler>
"""
import io
import os
import sys

p = os.path.join(sys.argv[1], "v3d33_tex.c")
s = io.open(p, encoding="utf-8").read()
if "defect 18" in s:
    print("v3d33_tex.c: already there")
    sys.exit(0)
EDITS = [
("""                        if (instr->coord_components < 2)
                                coords[next_coord++] = vir_uniform_f(c, 0.5);
                        break;
""", """                        break;
"""),
("""        /* Limit the number of channels returned to both how many the NIR
""", """        /* checks/53 defect 18: the configuration words ride on the first
         * two writes, so write at least two values - padding after all
         * parameters: in 1D mode a value right after s is the next parameter.
         */
        if (next_coord < 2)
                coords[next_coord++] = vir_uniform_f(c, 0.5);

        /* Limit the number of channels returned to both how many the NIR
"""),
]
for old, new in EDITS:
    assert s.count(old) == 1, "anchor not found: " + old[:60]
    s = s.replace(old, new)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("v3d33_tex.c: applied")
