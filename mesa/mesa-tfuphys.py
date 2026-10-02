#!/usr/bin/env python3
"""Mesa v3d: use the TFU on V3D 3.3 when the kernel gives buffers their
physical address as GPU address (defect 7 of mesa-22.3.6-v3d33.patch,
checks/53 §9 item 12).

The V3D 3.3 TFU bypasses the GPU MMU; its addresses are physical.  Defect 7
switched it off on 3.x because Mesa's buffer addresses were MMU addresses
then.  A kernel with the reserved GPU region (v3d33-contig.py) answers
DRM_V3D_PARAM 0x7033 with 1 and makes every GPU address physical, and it
refuses TFU jobs whose addresses are not in the job's own buffers
(v3d33-tfu-phys.py).  Kernels without it reject the parameter: the TFU stays
off there, as before.

usage: mesa-tfuphys.py <mesa src/gallium/drivers/v3d>
"""
import io
import os
import sys

D = sys.argv[1]

HELPER = """
/* checks/53: on V3D 3.3 the TFU uses physical addresses; a kernel that makes
 * every GPU address physical says so with parameter 0x7033 (older kernels
 * reject it)
 */
bool
v3d33_tfu_usable(struct v3d_screen *screen)
{
        static int usable = -1;

        if (usable < 0) {
                struct drm_v3d_get_param p = {
                        .param = (enum drm_v3d_param)0x7033,
                };

                usable = v3d_ioctl(screen->fd, DRM_IOCTL_V3D_GET_PARAM, &p) == 0 &&
                         p.value == 1;
        }
        return usable;
}
"""

EDITS = {
"v3d_screen.c": [
("""        case PIPE_CAP_GENERATE_MIPMAP:
                /* the TFU that implements this wedges V3D 3.3 (checks/53) */
                return v3d_has_feature(screen, DRM_V3D_PARAM_SUPPORTS_TFU) &&
                       screen->devinfo.ver >= 40;
""", """        case PIPE_CAP_GENERATE_MIPMAP:
                /* the TFU that implements this uses physical addresses on
                 * V3D 3.3 (checks/53): only with a kernel that provides them
                 */
                return v3d_has_feature(screen, DRM_V3D_PARAM_SUPPORTS_TFU) &&
                       (screen->devinfo.ver >= 40 || v3d33_tfu_usable(screen));
"""),
("""static bool
v3d_has_feature(struct v3d_screen *screen, enum drm_v3d_param feature)
""", HELPER + """
static bool
v3d_has_feature(struct v3d_screen *screen, enum drm_v3d_param feature)
"""),
],
"v3d_screen.h": [
("""void
v3d_fence_init(struct v3d_screen *screen);
""", """void
v3d_fence_init(struct v3d_screen *screen);

bool
v3d33_tfu_usable(struct v3d_screen *screen);
"""),
],
"v3d_blit.c": [
("""        if (screen->devinfo.ver < 40)
                return false;

        /* Can't write to raster. */
""", """        if (screen->devinfo.ver < 40 && !v3d33_tfu_usable(screen))
                return false;

        /* Can't write to raster. */
"""),
],
}

for name, edits in EDITS.items():
    p = os.path.join(D, name)
    s = io.open(p, encoding="utf-8").read()
    if "v3d33_tfu_usable" in s:
        print(name + ": already there")
        continue
    for old, new in edits:
        assert s.count(old) == 1, name + ": anchor not found:\n" + old
        s = s.replace(old, new)
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)
    print(name + ": applied")
