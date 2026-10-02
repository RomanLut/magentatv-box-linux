#!/usr/bin/env python3
"""Mesa nir_to_vir.c: write all four colour components to the TLB on V3D 3.x
(defect 23, checks/53 §5).

vir_emit_tlb_color_write() writes as many components as the fragment output
has and says so in the TLB config word (vec size: TLB_VEC_SIZE_2_F16 or
_4_F16, TLB_VEC_SIZE_MINUS_1 for 32-bit writes). On V3D 3.3 that fails for
render targets with a 16-bit internal type - rgba16f/rg16f/r16f,
r11f_g11f_b10f, rgb10_a2, srgb8_alpha8, rgba16i/ui, rgb10_a2ui - whenever
fewer than four components are written (a float or vec2 into rgba16f, even a
float into r16f, a uvec3 into rgba16ui); 8-bit targets (rgba8) work with two.
dEQP-GLES3 fragment_out: 163 of 940 failed (basic, array, random).

The unwritten components are undefined in GL, so on 3.x the write is always
four components (missing ones 0, alpha 1) with the matching vec size: all 940
fragment_out cases pass.

usage: mesa-tlbvec33.py <mesa src/broadcom/compiler>
"""
import io
import os
import sys

p = os.path.join(sys.argv[1], "nir_to_vir.c")
s = io.open(p, encoding="utf-8").read()
if "defect 23" in s:
    print("nir_to_vir.c: already there")
    sys.exit(0)
EDITS = [
("""        if (c->fs_key->swap_color_rb & (1 << rt))
                num_components = MAX2(num_components, 3);
        assert(num_components != 0);
""", """        if (c->fs_key->swap_color_rb & (1 << rt))
                num_components = MAX2(num_components, 3);
        assert(num_components != 0);

        /* checks/53 defect 23: the V3D 3.x TLB takes short writes only for
         * 8-bit render targets; write all four components (the missing
         * ones are undefined in GL).
         */
        int var_components = num_components;
        if (c->devinfo->ver < 41)
                num_components = 4;
"""),
("""                struct qreg r = color[0];
                struct qreg g = color[1];
                struct qreg b = color[2];
                struct qreg a = color[3];
""", """                struct qreg r = color[0];
                struct qreg g = var_components > 1 ? color[1] :
                                                     vir_uniform_f(c, 0.0);
                struct qreg b = var_components > 2 ? color[2] :
                                                     vir_uniform_f(c, 0.0);
                struct qreg a = var_components > 3 ? color[3] :
                                                     vir_uniform_f(c, 1.0);
"""),
]
for old, new in EDITS:
    assert s.count(old) == 1, "anchor not found: " + old[:60]
    s = s.replace(old, new)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("nir_to_vir.c: applied")
