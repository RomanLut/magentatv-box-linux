#!/usr/bin/env python3
"""Mesa qpu_schedule.c: never merge two writers of r3 (or r4) into one
instruction on V3D 3.x (defect 16, checks/53 §5).

On V3D 3.x ldvary writes the varying into r3 implicitly (4.x: an explicit
register). Register allocation already keeps other values out of r3 across an
r3 writer (update_graph_and_reg_classes_for_inst(): "nothing else can be
stored in r3/r4 across it", with vir_writes_r3() counting ldvary on 3.x), but
the QPU scheduler merges instructions afterwards and qpu_merge_inst() has no
such rule. It paired the fmul of one varying, allocated to r3, with the ldvary
of the next:

    fmul r3, r3, rf0   ; ldvary
    fadd rf6, r3, r5   ; fmul r4, r3, rf0 ; ldvary

and the next instruction reads r3 once as the product and once as the new
varying - one varying in every few came out wrong. piglit
glsl-1.20/execution/literal-varyings (8 varyings, red instead of green);
Chromium's YUV video quad in a window (one texture coordinate wrong: grey in
one triangle, colour stripes in the other).

Two changes:
- qpu_merge_inst() refuses to merge when both instructions write r3, or both
  write r4 (v3d_qpu_writes_r3()/_r4(), which include the implicit writes).
- fixup_pipelined_ldvary() (the 2021 ldvary pipelining, written for 4.x)
  runs on 4.1+ only: its checks look at the ldvary's explicit destination
  (sig_magic/sig_addr), which a 3.x ldvary does not have.

usage: mesa-r3merge33.py <mesa src/broadcom/compiler>
"""
import io
import os
import sys

p = os.path.join(sys.argv[1], "qpu_schedule.c")
s = io.open(p, encoding="utf-8").read()
MARK = "defect 16"
if MARK in s:
    print("qpu_schedule.c: already there")
    sys.exit(0)

EDITS = [
("""        if (a->sig.ldvary && b->sig.ldvary)
                return false;
""", """        if (a->sig.ldvary && b->sig.ldvary)
                return false;

        /* checks/53 defect 16: at most one writer of r3 and one of r4 per
         * instruction, implicit writes included (on V3D 3.x ldvary writes
         * r3). Register allocation keeps other values out of r3/r4 across
         * such a writer, but only for the instructions as they were then.
         */
        if (v3d_qpu_writes_r3(devinfo, a) && v3d_qpu_writes_r3(devinfo, b))
                return false;
        if (v3d_qpu_writes_r4(devinfo, a) && v3d_qpu_writes_r4(devinfo, b))
                return false;
"""),
("""        assert(inst->type == V3D_QPU_INSTR_TYPE_ALU);
        assert(inst->sig.ldvary);
        uint32_t ldvary_magic = inst->sig_magic;
""", """        assert(inst->type == V3D_QPU_INSTR_TYPE_ALU);
        assert(inst->sig.ldvary);

        /* checks/53 defect 16: the checks below look at the ldvary's
         * explicit destination (sig_magic/sig_addr), which only V3D 4.1+
         * has; on 3.x ldvary writes r3/r5 implicitly.
         */
        if (c->devinfo->ver < 41)
                return false;

        uint32_t ldvary_magic = inst->sig_magic;
"""),
]
for old, new in EDITS:
    assert s.count(old) == 1, "anchor not found: " + old[:60]
    s = s.replace(old, new)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("qpu_schedule.c: applied")
