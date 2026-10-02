#!/usr/bin/env python3
"""Mesa qpu_schedule.c: keep VPM setups and writes on one side of a thread
switch on V3D 3.x (defect 19, checks/53 §5).

On V3D 3.x a vertex shader writes each output as a pair: vpmsetup (select the
VPM slot) and a write to the vpm register. That setup is QPU state the other
thread of the QPU also uses. Vertex shaders on 3.x did not switch threads
until defect 14: since then an indexed uniform read (a GLSL array promoted to
uniforms, e.g. a constant array read with a variable index) goes through the
TMU, with a thrsw. The scheduler then put a vpmsetup into the thrsw's delay
slots - still this thread - and the matching vpm write after the switch, when
the other thread had moved the setup:

    mov vpm, rf5          ; thrsw
    add tmuau, r4, r0     ; ...
    vpmsetup -, r3                    <- delay slot, before the switch
    ...
    mov vpm, rf10                     <- after the switch: wrong slot

piglit glsl-1.20 array_bounds glsl-array-bounds-12: gl_FrontColor red or
yellow instead of green for every index, not only the out-of-bounds one.

Like the accumulators, flags, TLB and TMU state already handled there, the
VPM state is treated as not surviving a switch on 3.x:
- calculate_deps(): a thrsw is a write dependency of last_vpm, so no VPM
  access moves across it;
- qpu_inst_after_thrsw_valid_in_delay_slot(): no VPM access scheduled after a
  thrsw goes into its delay slots.

usage: mesa-vpmthrsw33.py <mesa src/broadcom/compiler>
"""
import io
import os
import sys

p = os.path.join(sys.argv[1], "qpu_schedule.c")
s = io.open(p, encoding="utf-8").read()
if "defect 19" in s:
    print("qpu_schedule.c: already there")
    sys.exit(0)

EDITS = [
("""                add_write_dep(state, &state->last_tmu_write, n);
                add_write_dep(state, &state->last_tmu_config, n);
        }
""", """                add_write_dep(state, &state->last_tmu_write, n);
                add_write_dep(state, &state->last_tmu_config, n);

                /* checks/53 defect 19: on V3D 3.x the VPM write setup
                 * (vpmsetup) is QPU state the other thread changes too.
                 */
                if (devinfo->ver < 41)
                        add_write_dep(state, &state->last_vpm, n);
        }
"""),
("""        /* Instruction sequence restrictions: Branch is not allowed in delay
         * slots of a thrsw.
         */
        if (qinst->qpu.type == V3D_QPU_INSTR_TYPE_BRANCH)
                return false;
""", """        /* Instruction sequence restrictions: Branch is not allowed in delay
         * slots of a thrsw.
         */
        if (qinst->qpu.type == V3D_QPU_INSTR_TYPE_BRANCH)
                return false;

        /* checks/53 defect 19: on V3D 3.x a vpmsetup placed here would be
         * used by a vpm write after the switch, when the other thread has
         * moved the setup.
         */
        if (c->devinfo->ver < 41 && v3d_qpu_uses_vpm(&qinst->qpu))
                return false;
"""),
]
for old, new in EDITS:
    assert s.count(old) == 1, "anchor not found: " + old[:60]
    s = s.replace(old, new)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("qpu_schedule.c: applied")
