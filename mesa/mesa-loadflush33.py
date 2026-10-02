#!/usr/bin/env python3
"""Mesa v3dx_rcl.c: the dummy store after a 3.x tile load must not clear
(defect 33, checks/53 §5).

On V3D 3.x a general tile load completes at the next Tile Coordinates
Implicit, and a job that loads more than one buffer ends each earlier load
with Tile Coordinates Implicit + Store Tile Buffer General (buffer None)
- flush_last_load(). Mesa emitted that store with all of its "Disable ...
clear on write" bits at 0, so it cleared the tile buffers it had just loaded.
The vendor driver's list for the same job (stockms.c, stockms-two.txt) has
the store with all three set:

    Reload Tile Color Buffer (Z and stencil load)
    Tile Coordinates Implicit
    Store Tile Buffer General  buffer None, disable Z/stencil/colour clear
    Load Tile Buffer General   render target 0, raw
    Tile Coordinates Implicit ...

A 4x colour buffer reloaded together with depth/stencil came back with its
alpha 0 (msstencil.c; dEQP-GLES3 multisample.fbo_{4,max}_samples.stencil:
"max difference = (0, 0, 0, 255)"). The dummy store now clears nothing.

usage: mesa-loadflush33.py <mesa src/gallium/drivers/v3d>
"""
import io
import os
import sys

p = os.path.join(sys.argv[1], "v3dx_rcl.c")
s = io.open(p, encoding="utf-8").read()
if "defect 33" in s:
    print("v3dx_rcl.c: already there")
    sys.exit(0)

EDITS = [
("""        cl_emit(cl, TILE_COORDINATES_IMPLICIT, coords);
        cl_emit(cl, STORE_TILE_BUFFER_GENERAL, store) {
                store.buffer_to_store = NONE;
        }
}""", """        cl_emit(cl, TILE_COORDINATES_IMPLICIT, coords);
        cl_emit(cl, STORE_TILE_BUFFER_GENERAL, store) {
                store.buffer_to_store = NONE;
#if V3D_VERSION < 40
                /* checks/53 defect 33: only completes the load - the vendor
                 * driver's store here clears nothing.
                 */
                store.disable_color_buffers_clear_on_write = true;
                store.disable_z_buffer_clear_on_write = true;
                store.disable_stencil_buffer_clear_on_write = true;
#endif
        }
}"""),
]
for old, new in EDITS:
    assert s.count(old) == 1, "anchor not found: " + old[:60]
    s = s.replace(old, new)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("v3dx_rcl.c: applied")
