#!/usr/bin/env python3
"""Mesa nir_to_vir.c: vertex attribute reads past 32 words on V3D 3.x
(defect 25, checks/53 §5).

On V3D 3.x a vertex or coordinate shader reads its attributes from the VPM
with generic block reads of at most 32 words each (num field, 0 = 32). The
setup's addr is the first VPM row to read; v3d33_vir_vpm_read_setup() takes it
from c->num_inputs, but ntq_emit_vpm_read() never advanced that counter (only
the fragment and geometry shader input paths use it now), so the second read
setup of a shader with more than 32 attribute words started at row 0 again:
those attributes got the values of the first ones.

dEQP-GLES3 transform_feedback basic_types/array/array_element interleaved
mat4, mat3x4, mat4x3, mat2x3, mat2x4 (36 or 34 attribute words): the last
attribute's captured values wrong, e.g. basic_types.interleaved.points.highp_mat4
"Mismatch in v_varB (a_varB_c3)". Rendering reads the same wrong attributes.

Count every word read in c->num_inputs on 3.x, as the read setups expect.

usage: mesa-vpmread33.py <mesa src/broadcom/compiler>
"""
import io
import os
import sys

p = os.path.join(sys.argv[1], "nir_to_vir.c")
s = io.open(p, encoding="utf-8").read()
if "defect 25" in s:
    print("nir_to_vir.c: already there")
    sys.exit(0)

EDITS = [
("""        if (*num_components_queued != 0) {
                (*num_components_queued)--;
                return vir_MOV(c, vpm);
        }

        uint32_t num_components = MIN2(*remaining, 32);

        v3d33_vir_vpm_read_setup(c, num_components);

        *num_components_queued = num_components - 1;
        *remaining -= num_components;

        return vir_MOV(c, vpm);
""", """        /* checks/53 defect 25: c->num_inputs is the VPM row the next read
         * setup starts at (v3d33_vir_vpm_read_setup), so count each word.
         */
        if (*num_components_queued != 0) {
                (*num_components_queued)--;
                c->num_inputs++;
                return vir_MOV(c, vpm);
        }

        uint32_t num_components = MIN2(*remaining, 32);

        v3d33_vir_vpm_read_setup(c, num_components);

        *num_components_queued = num_components - 1;
        *remaining -= num_components;
        c->num_inputs++;

        return vir_MOV(c, vpm);
"""),
]
for old, new in EDITS:
    assert s.count(old) == 1, "anchor not found: " + old[:60]
    s = s.replace(old, new)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("nir_to_vir.c: applied")
