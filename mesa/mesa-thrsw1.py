#!/usr/bin/env python3
"""Mesa v3d compiler: no last-THRSW restore after demoting to one thread
(checks/53 §5).

c98ddc778a3 ("broadcom/compiler: force a last thrsw for spilling", 2021)
injects a last THRSW before register allocation and, if nothing spilled,
removes it again and restores the previous one (vir_restore_last_thrsw).  It
was written for V3D 4.x, where register allocation never goes below 2 threads.
On V3D 3.x the minimum is 1: when allocation fails at 2 threads the loop
halves to 1 and vir_remove_thrsw() deletes every THRSW and clears
c->last_thrsw, but restore_last_thrsw still points at the deleted previous one,
so the restore passes NULL to vir_remove_instruction():

  #0 vir_remove_instruction  #1 v3d_nir_to_vir  #2 v3d_compile
  (Firefox hardware WebRender, a large shader, V3D 3.3)

The same function already handles this case at the top: vir_emit_last_thrsw()
sets *restore_last_thrsw = NULL after its own vir_remove_thrsw() for 3.x
single-threaded shaders.  Do the same in the allocation loop; with both NULL
the restore is skipped, as before c98ddc778a3.

usage: mesa-thrsw1.py <mesa src/broadcom/compiler>
"""
import io
import os
import sys

p = os.path.join(sys.argv[1], "nir_to_vir.c")
s = io.open(p, encoding="utf-8").read()
old = """                c->threads /= 2;

                if (c->threads == 1)
                        vir_remove_thrsw(c);
        }
"""
new = """                c->threads /= 2;

                if (c->threads == 1) {
                        vir_remove_thrsw(c);
                        /* checks/53: nothing left to restore (V3D 3.x) */
                        restore_last_thrsw = NULL;
                }
        }
"""
if new in s:
    print("nir_to_vir.c: already there")
    sys.exit(0)
assert s.count(old) == 1, "anchor not found"
io.open(p, "w", encoding="utf-8", newline="\n").write(s.replace(old, new))
print("nir_to_vir.c: applied")
