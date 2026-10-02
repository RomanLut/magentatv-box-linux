#!/usr/bin/env python3
"""Mesa qpu_schedule.c: never put two ldvary signals into one instruction
(defect 11 of mesa-22.3.6-v3d33.patch, checks/53 §5).

Each ldvary reads the next varying component in order, so an instruction may
carry one.  The scheduler combines instructions in two places and relies on
v3d_qpu_sig_writes_address() to refuse a second ldvary: on V3D 4.x ldvary
writes an explicit register (sig_addr), so that check catches it; on V3D 3.x
ldvary writes r3/r5 implicitly, has no address, and the check passes.
fixup_pipelined_ldvary() (the 2021 ldvary pipelining, 1784dd22 and follow-ups)
then sets ldvary on a previous instruction that already has one, and one
varying read vanishes: every later read gets the component before it.

Seen in Mesa's fixed-function fragment shader, which reads TEX0 as s, t, r, q
(r unused) for a projective lookup: 4 ldvary in the VIR, 3 in the QPU code,
q read as r = 0, so 1/q is infinite and every texel came from the texture's
corner - xfwm4's GLX compositor (vblank_mode auto) drew one solid colour
instead of the desktop.  GLSL texture2DProj() failed the same way.

usage: mesa-ldvary.py <mesa src/broadcom/compiler>
"""
import io
import os
import sys

p = os.path.join(sys.argv[1], "qpu_schedule.c")
s = io.open(p, encoding="utf-8").read()
if "one ldvary per instruction" in s:
    print("qpu_schedule.c: ldvary guards already there")
    sys.exit(0)

EDITS = [
("""        if (!qpu_compatible_peripheral_access(devinfo, a, b))
                return false;

        struct v3d_qpu_instr merge = *a;
""", """        if (!qpu_compatible_peripheral_access(devinfo, a, b))
                return false;

        /* one ldvary per instruction: each reads the next varying.  On V3D
         * 3.x ldvary has no address for the sig_writes_address() check below
         * to catch.
         */
        if (a->sig.ldvary && b->sig.ldvary)
                return false;

        struct v3d_qpu_instr merge = *a;
"""),
("""        /* The previous instruction cannot have a conflicting signal */
        if (v3d_qpu_sig_writes_address(c->devinfo, &prev->qpu.sig))
                return false;
""", """        /* The previous instruction cannot have a conflicting signal */
        if (v3d_qpu_sig_writes_address(c->devinfo, &prev->qpu.sig))
                return false;

        /* ... nor an ldvary of its own (one ldvary per instruction; on V3D
         * 3.x ldvary writes no address, so the check above misses it).
         */
        if (prev->qpu.sig.ldvary)
                return false;
"""),
]
for old, new in EDITS:
    assert s.count(old) == 1, "qpu_schedule.c: anchor not found:\n" + old
    s = s.replace(old, new)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("qpu_schedule.c: ldvary guards applied")
