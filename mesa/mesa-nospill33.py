#!/usr/bin/env python3
"""Mesa defect 15 on V3D 3.3: no TMU register spilling (checks/53 section 5).

When register allocation fails, Mesa's V3D compiler spills temporaries to a
scratch buffer through the TMU: a store (tmuau + tmud, then tmuwt) and a load
(tmuau, then ldtmu), with a TMU configuration word 0xffffff7f ("per quad") in
the V3D 4.x layout. V3D 3.3 has no such thing: Mesa's own packet description
defines the TMU Config Parameter 0/1/2 structs and the TMU Op enum (the write
operations included) only from 4.1 on (min_ver="41" in v3d_packet_v33.xml).
On 3.3 every spilling shader waits forever for its TMU operation: the frame's
render list runs to its end, the fragment shaders never finish (PCS=0x5), and
the kernel resets the GPU - once per draw.

Chromium's GPU compositing hit it with Skia's larger programs (a destination
read plus a 14-tap Gaussian: 739 instructions, 47 spills and 47 fills at 2
threads; work/chromium/shaders3/43.shader_test). work/v3d-20260921/skrrect.c
with that fragment shader reproduces it offscreen: 5 draws, 5 GPU resets.

The fix allows no TMU spills below V3D 4.1. Spills that only re-materialize a
uniform or a value stay allowed; everything else makes that thread count fail
allocation, and the compile strategies drop to fewer threads - at 1 thread
V3D 3.3 has 64 registers per thread instead of 32 (the 1-thread path is the
one defect 13 fixed).

usage: mesa-nospill33.py <mesa source tree>
"""
import io
import os
import sys

p = os.path.join(sys.argv[1], "src/broadcom/compiler/vir_register_allocate.c")
s = io.open(p, encoding="utf-8").read()
MARK = "checks/53 defect 15"
if MARK in s:
    print("vir_register_allocate.c: already there")
    sys.exit(0)
old = """static inline bool
tmu_spilling_allowed(struct v3d_compile *c)
{
        return c->spills + c->fills < c->max_tmu_spills;
}
"""
new = """static inline bool
tmu_spilling_allowed(struct v3d_compile *c)
{
        /* checks/53 defect 15: TMU spills store through the TMU with a V3D
         * 4.x TMU configuration word; V3D 3.3 has neither TMU writes nor that
         * word (v3d_packet_v33.xml: TMU Config Parameter and TMU Op are 4.1+),
         * and a spilling shader never finishes.  Make register allocation
         * fail instead, so the compile strategies lower the thread count.
         */
        if (c->devinfo->ver < 41)
                return false;

        return c->spills + c->fills < c->max_tmu_spills;
}
"""
assert s.count(old) == 1, "vir_register_allocate.c: anchor not found"
io.open(p, "w", encoding="utf-8", newline="\n").write(s.replace(old, new))
print("vir_register_allocate.c: applied")
