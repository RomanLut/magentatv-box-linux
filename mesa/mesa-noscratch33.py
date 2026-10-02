#!/usr/bin/env python3
"""Mesa v3d: small indexed arrays as if-ladders on V3D 3.x, not scratch
(defect 17, checks/53 §5).

A temporary array (or matrix, or an input/output array turned into one by
lower_all_io_to_temps) indexed with a non-constant index goes to scratch:
nir_lower_vars_to_scratch() in v3d_lower_nir(), then per-component
store_scratch/load_scratch through the TMU. On V3D 3.3 that goes wrong as soon
as a shader writes more than a few values: piglit's
glsl-fs-vec4-indexing-temp-src reads black for every index, and the
variable-indexing tests hang the GPU (19 timeouts) - the TMU write path of
3.x is the one defect 15 found unusable for spilling. A shader with a large
array and few writes (glsl-{fs,vs}-giant-temp-array, int[512]) does work.

The usual Mesa trade-off, as in other NIR drivers: nir_lower_indirect_derefs()
turns indexing into an if-ladder for arrays up to a length limit, larger
arrays keep scratch. On 3.x arrays of up to 16 elements are laddered before
the scratch pass (enough for every piglit variable-indexing case; a ladder
over hundreds of elements would need more registers than 3.3 has, and it
cannot spill either). V3D 4.x is unchanged.

(An earlier version reported INDIRECT_INPUT/OUTPUT/TEMP_ADDR = 0 on 3.x, as
vc4 does, so the GLSL front end laddered every array: giant arrays then did
not compile. The caps stay as upstream.)

usage: mesa-noscratch33.py <mesa src/src>
"""
import io
import os
import sys

MARK = "defect 17"


def patch(rel, edits):
    p = os.path.join(sys.argv[1], rel)
    s = io.open(p, encoding="utf-8").read()
    if MARK in s:
        print(rel + ": already there")
        return
    for old, new in edits:
        assert s.count(old) == 1, rel + ": anchor not found: " + old[:60]
        s = s.replace(old, new)
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)
    print(rel + ": applied")


patch("broadcom/compiler/vir.c", [(
"""        NIR_PASS(_, c->s, nir_lower_vars_to_scratch,
                 nir_var_function_temp,
                 0,
                 glsl_get_natural_size_align_bytes);""",
"""        /* checks/53 defect 17: scratch through the TMU is unreliable on
         * V3D 3.x; index small arrays with if-ladders instead.
         */
        if (c->devinfo->ver < 41) {
                NIR_PASS(_, c->s, nir_lower_indirect_derefs,
                         nir_var_function_temp, 16);
        }

        NIR_PASS(_, c->s, nir_lower_vars_to_scratch,
                 nir_var_function_temp,
                 0,
                 glsl_get_natural_size_align_bytes);"""),
])
