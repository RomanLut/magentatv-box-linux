#!/usr/bin/env python3
"""Mesa v3d: advertise texture buffer objects only on V3D 4.x (checks/53 §5).

Upstream enabled PIPE_CAP_TEXTURE_BUFFER_OBJECTS unconditionally
(7f1525f086f, MR 13409, 2019/2021, tested on the RPi4 only), but the support
behind it (60a1968fa19) went into the V3D 4.x texture state path
(v3dX(create_texture_shader_state_bo), v3d_create_sampler_view) only.  The
V3D 3.3 path, emit_one_texture() in v3dx_emit.c, never learned PIPE_BUFFER
views: it dereferences the bound sampler, and a buffer texture sampled with
txf has none.  The state tracker's PBO upload (st_pbo_draw, used by
glTexSubImage2D from a pixel buffer) samples through a buffer texture, so
Firefox's hardware WebRender segfaulted there on the first upload:

  #0 emit_one_texture  #1 v3d33_emit_state  #2 v3d_draw_vbo
  #3 cso_draw_arrays   #4 st_pbo_draw       #5 try_pbo_upload_common

With the cap off on 3.3 the state tracker uploads through a CPU mapping, as
on vc4, which does not advertise TBOs either.  GLES 3.0 does not need them.

usage: mesa-tbo33.py <mesa src/gallium/drivers/v3d>
"""
import io
import os
import sys

p = os.path.join(sys.argv[1], "v3d_screen.c")
s = io.open(p, encoding="utf-8").read()
old = """        case PIPE_CAP_TEXTURE_BUFFER_OBJECTS:
                return true;
"""
new = """        case PIPE_CAP_TEXTURE_BUFFER_OBJECTS:
                /* checks/53: only the V3D 4.x texture state knows buffers */
                return screen->devinfo.ver >= 40;
"""
if new in s:
    print("v3d_screen.c: already there")
    sys.exit(0)
assert s.count(old) == 1, "anchor not found"
io.open(p, "w", encoding="utf-8", newline="\n").write(s.replace(old, new))
print("v3d_screen.c: applied")
