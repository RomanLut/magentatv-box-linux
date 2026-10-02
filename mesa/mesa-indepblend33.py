#!/usr/bin/env python3
"""Mesa v3d_screen.c: no independent blend functions on V3D 3.x (defect 20,
checks/53 §5).

v3d_screen_get_param() reports PIPE_CAP_INDEP_BLEND_ENABLE for V3D 4.0+ only
- on 3.x the Blend Config packet has no render target mask
(v3d_packet_v33.xml; v3dx_emit.c: "assert(rt == 0)" below 4.0), so one blend
state applies to every render target - but PIPE_CAP_INDEP_BLEND_FUNC on every
version. From the latter the state tracker exposes GL_EXT_draw_buffers_indexed
(ARB_draw_buffers_blend), whose glEnablei/glDisablei(GL_BLEND) then fail
with GL_INVALID_ENUM because they need EXT_draw_buffers2, i.e. the former.
dEQP resets that state after every test case and aborted the run after the
first case ("Failed to reset indexed draw buffer state: glGetError()
returned GL_INVALID_ENUM", MESA_DEBUG: glDisablei(cap=GL_BLEND)).

PIPE_CAP_INDEP_BLEND_FUNC now follows PIPE_CAP_INDEP_BLEND_ENABLE: 4.0+.

usage: mesa-indepblend33.py <mesa src/src>
"""
import io
import os
import sys

p = os.path.join(sys.argv[1], "gallium/drivers/v3d/v3d_screen.c")
s = io.open(p, encoding="utf-8").read()
if "defect 20" in s:
    print("v3d_screen.c: already there")
    sys.exit(0)
EDITS = [
("""        case PIPE_CAP_INDEP_BLEND_FUNC:
                return 1;
""", """                return 1;
"""),
("""        case PIPE_CAP_INDEP_BLEND_ENABLE:
                return screen->devinfo.ver >= 40;
""", """        /* checks/53 defect 20: on 3.x one blend config serves all render
         * targets, so neither per-RT enables nor per-RT functions.
         */
        case PIPE_CAP_INDEP_BLEND_ENABLE:
        case PIPE_CAP_INDEP_BLEND_FUNC:
                return screen->devinfo.ver >= 40;
"""),
]
for old, new in EDITS:
    assert s.count(old) == 1, "anchor not found: " + old[:60]
    s = s.replace(old, new)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("v3d_screen.c: applied")
