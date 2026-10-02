#!/usr/bin/env python3
"""Mesa nir_to_vir.c: gl_VertexID on V3D 3.x is 24 bits (defect 35,
checks/53 §5).

A 3.x vertex or coordinate shader reads the vertex ID from the VPM, ahead of
the attributes (ntq_setup_vs_inputs). dEQP-GLES3
shaders.builtin_variable.vertex_id indexes a uniform array with it
(u_colors[gl_VertexID], an indexed uniform read through the TMU at base +
16 * index), and on every run the GPU read exactly 0x10000000 below the
array: three MMU faults ("pte invalid" at 0x203bd100, 0x20150000 - the
buffer's address with bit 28 clear, an index 2^24 too small), no reset, the
rendered colours right. Where the high bits come from is not established:
the IDs of the drawn vertices are clean in both shaders (vidprobe.c, through
a flat varying and, for the coordinate shader, transform feedback), and a
glDrawArrays with an indexed uniform read does not fault at any vertex count;
the test also draws indexed. V3D 3.3 vertex indices are 24-bit (the driver
reports GL_MAX_ELEMENT_INDEX 0xffffff), so masking the ID to 24 bits changes
no valid value - and the faults are gone, the case still passes.

usage: mesa-vid33.py <mesa src/broadcom/compiler>
"""
import io
import os
import sys

p = os.path.join(sys.argv[1], "nir_to_vir.c")
s = io.open(p, encoding="utf-8").read()
if "defect 35" in s:
    print("nir_to_vir.c: already there")
    sys.exit(0)

EDITS = [
("""                c->vid = ntq_emit_vpm_read(c, &vpm_components_queued,
                                           &num_components, ~0);
        }
""", """                c->vid = ntq_emit_vpm_read(c, &vpm_components_queued,
                                           &num_components, ~0);
                /* checks/53 defect 35: the 3.x VPM vertex ID has set bits
                 * above its 24-bit index.
                 */
                if (c->devinfo->ver < 40)
                        c->vid = vir_AND(c, c->vid, vir_uniform_ui(c, 0xffffff));
        }
"""),
]
for old, new in EDITS:
    assert s.count(old) == 1, "anchor not found: " + old[:60]
    s = s.replace(old, new)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("nir_to_vir.c: applied")
