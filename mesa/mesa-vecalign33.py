#!/usr/bin/env python3
"""Mesa nir_to_vir.c: vector memory loads only at natural alignment on V3D 3.x
(defect 29, checks/53 §5).

nir_opt_load_store_vectorize() merges neighbouring UBO/SSBO loads into one
vector load through the general TMU path; mem_vectorize_callback() allows it
whenever the vector stays inside a 16-byte block ("Vector accesses wrap at
16-byte boundaries", the V3D 4.x rule). The 3.3 TMU aligns a vector read
down to its own size instead: a vec2 load at offset 4 returned the words at
offsets 0 and 4. A std140 block whose first member is unused in a shader
gets exactly that load for the next two (dEQP-GLES3 ubo.random.scalar_types
2, 3, 5, 6, 14, 23 and KHR-GLES3 shaders.uniform_block.random.scalar_types
2, 9; ubotest.c: f read e's value, g read f's).

On 3.x a vector load is now formed only when it is aligned to its size
(rounded up to a power of two); unaligned neighbours stay separate loads.

usage: mesa-vecalign33.py <mesa src/broadcom/compiler>
"""
import io
import os
import sys

p = os.path.join(sys.argv[1], "nir_to_vir.c")
s = io.open(p, encoding="utf-8").read()
if "defect 29" in s:
    print("nir_to_vir.c: already there")
    sys.exit(0)

EDITS = [
("""        if (16 - align_mul + align_offset + num_components * 4 > 16)
                return false;

        return true;
}
""", """        if (16 - align_mul + align_offset + num_components * 4 > 16)
                return false;

        /* checks/53 defect 29: the 3.x TMU aligns a vector access down to
         * its size, so it must start at a multiple of it.
         */
        struct v3d_compile *c = data;
        if (c && c->devinfo->ver < 41) {
                unsigned size = util_next_power_of_two(num_components) * 4;
                if (align_mul < size || align_offset % size != 0)
                        return false;
        }

        return true;
}
"""),
("""                        .callback = mem_vectorize_callback,
                        .robust_modes = 0,
                };""", """                        .callback = mem_vectorize_callback,
                        .robust_modes = 0,
                        .cb_data = c,
                };"""),
]
for old, new in EDITS:
    assert s.count(old) == 1, "anchor not found: " + old[:60]
    s = s.replace(old, new)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("nir_to_vir.c: applied")
