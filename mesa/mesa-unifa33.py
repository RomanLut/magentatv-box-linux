#!/usr/bin/env python3
"""Mesa defect 14 on V3D 3.3: no ldunifa before V3D 4.1 (checks/53 section 5).

ntq_emit_load_unifa() (broadcom/compiler/nir_to_vir.c) loads uniforms, UBOs
and read-only SSBOs whose offset is not a constant but dynamically uniform
through the unifa register: ldunifa/ldunifarf signals. Those exist only from
V3D 4.1 on - qpu_pack.c has them in v41_sig_map alone - and the function has
no version check (written for the Pi 4; upstream dropped V3D 3.x in 2023,
85f26828fea, so none was ever added). On 3.3 the packer then fails:

    Failed to pack instruction 91:
    nop t35; ldunifarf
    Failed to compile MESA_SHADER_FRAGMENT prog 1/1 with any strategy.

and the draw runs without a valid shader: MMU faults near address 0 and a
fragment shader that never ends. Chromium's GPU compositing hit it within
seconds - Skia's Gaussian blur reads uoffsetsAndKernel[i] in a loop with a
highp int index that is uniform across the draw (work/chromium/shaders/
16.shader_test, reproduced offscreen by work/v3d-20260921/skblur.c: 79 faults
and resets in 200 passes).

The fix declines unifa below 4.1, so these loads take the general TMU path
the function already falls back to for divergent offsets.

usage: mesa-unifa33.py <mesa source tree>
"""
import io
import os
import sys

p = os.path.join(sys.argv[1], "src/broadcom/compiler/nir_to_vir.c")
s = io.open(p, encoding="utf-8").read()
MARK = "checks/53 defect 14"
if MARK in s:
    print("nir_to_vir.c: already there")
    sys.exit(0)
old = """        bool is_ssbo = instr->intrinsic == nir_intrinsic_load_ssbo;

        /* Every ldunifa auto-increments the unifa address by 4 bytes, so our
"""
new = """        bool is_ssbo = instr->intrinsic == nir_intrinsic_load_ssbo;

        /* checks/53 defect 14: ldunifa/ldunifarf exist from V3D 4.1 on
         * (qpu_pack.c has them in v41_sig_map only); on 3.3 the instruction
         * cannot be packed and the whole shader fails to compile.  Use the
         * general TMU path instead.
         */
        if (c->devinfo->ver < 41)
                return false;

        /* Every ldunifa auto-increments the unifa address by 4 bytes, so our
"""
assert s.count(old) == 1, "nir_to_vir.c: anchor not found"
io.open(p, "w", encoding="utf-8", newline="\n").write(s.replace(old, new))
print("nir_to_vir.c: applied")
