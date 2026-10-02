#!/usr/bin/env python3
"""Mesa nir_to_vir.c: centroid varyings on V3D 3.x (defect 26, checks/53 §5).

The fragment shader interpolates a centroid varying with the centroid W
payload (rf1) instead of the centre W (rf0), and the driver tells the
hardware which varyings are centroid with the Centroid Flags packet. That
packet exists from V3D 4.1 on (v3d_packet_v33.xml min_ver="41"; the driver
emits it for V3D_VERSION >= 40 only), so on 3.3 the hardware interpolates
every varying at the pixel centre while the shader multiplies centroid ones
by rf1, which does not match: noise over lines and triangles.

dEQP-GLES3 transform_feedback interpolation.centroid lines/triangles (12) and
random / random_full_array_capture cases with a centroid varying (60) failed
their image comparison; both images were speckled where a smooth gradient
belongs. Points passed.

On 3.x a centroid varying is interpolated like a smooth one, at the pixel
centre with the centre W. For single-sample targets the centroid is the
centre, so that is exact; with 4x MSAA a partly covered edge pixel samples
at its centre instead of inside the primitive.

usage: mesa-centroid33.py <mesa src/broadcom/compiler>
"""
import io
import os
import sys

p = os.path.join(sys.argv[1], "nir_to_vir.c")
s = io.open(p, encoding="utf-8").read()
if "defect 26" in s:
    print("nir_to_vir.c: already there")
    sys.exit(0)

EDITS = [
("""                if (var->data.centroid) {
                        BITSET_SET(c->centroid_flags, i);""",
"""                /* checks/53 defect 26: 3.x has no Centroid Flags packet,
                 * the hardware interpolates at the centre.
                 */
                if (var->data.centroid && c->devinfo->ver >= 40) {
                        BITSET_SET(c->centroid_flags, i);"""),
]
for old, new in EDITS:
    assert s.count(old) == 1, "anchor not found: " + old[:60]
    s = s.replace(old, new)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("nir_to_vir.c: applied")
