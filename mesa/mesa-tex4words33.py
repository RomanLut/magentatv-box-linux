#!/usr/bin/env python3
"""Mesa v3d33_tex.c: at most four TMU parameter words on V3D 3.3
(defect 28, checks/53 §5).

A 3.3 texture lookup is a series of writes to the TMU (s, t, r, bias or LOD,
shadow reference), the last one to TMUL. A shadow lookup with three
coordinates and a bias or an explicit LOD needs five: samplerCubeShadow with a
bias, samplerCubeShadow in a vertex shader (texture() there is an explicit
LOD 0), sampler2DArrayShadow with textureGrad (lowered to an explicit LOD).
With five writes the fragment or vertex shader never gets its result: one GPU
reset per draw (dEQP-GLES3 shaders.texture_functions texture.samplercubeshadow_
{vertex,bias_fragment}, texturegrad/texturegradoffset.sampler2darrayshadow_
{vertex,fragment}).

The TMU takes at most four, so such a lookup now leaves out the bias/LOD word
and uses the automatic LOD: no hang, and exact where only one level is
sampled (a vertex shader's LOD 0 on a texture without mipmaps, a bias that
does not change the level). A full fix would compare in the shader
(nir_lower_tex_shadow) and pass the LOD instead.

usage: mesa-tex4words33.py <mesa src/broadcom/compiler>
"""
import io
import os
import sys

p = os.path.join(sys.argv[1], "v3d33_tex.c")
s = io.open(p, encoding="utf-8").read()
if "defect 28" in s:
    print("v3d33_tex.c: already there")
    sys.exit(0)

EDITS = [
("""        struct qreg coords[5];
        int next_coord = 0;
""", """        struct qreg coords[5];
        int next_coord = 0;
        int lod_coord = -1;
"""),
("""                case nir_tex_src_bias:
                        coords[next_coord++] =
                                ntq_get_src(c, instr->src[i].src, 0);
""", """                case nir_tex_src_bias:
                        lod_coord = next_coord;
                        coords[next_coord++] =
                                ntq_get_src(c, instr->src[i].src, 0);
"""),
("""                case nir_tex_src_lod:
                        coords[next_coord++] =""", """                case nir_tex_src_lod:
                        lod_coord = next_coord;
                        coords[next_coord++] ="""),
("""        /* checks/53 defect 18: the configuration words ride on the first""",
"""        /* checks/53 defect 28: the 3.3 TMU takes at most four parameter
         * words; a fifth hangs the shader. Leave out the bias/LOD (the
         * TMU then uses its automatic LOD) when a shadow lookup with three
         * coordinates would need five.
         */
        if (next_coord > 4 && lod_coord >= 0) {
                for (int j = lod_coord; j < next_coord - 1; j++)
                        coords[j] = coords[j + 1];
                next_coord--;
                p0_unpacked.bias_supplied = false;
                p0_unpacked.disable_autolod_use_bias_only = false;
        }
        assert(next_coord <= 4);

        /* checks/53 defect 18: the configuration words ride on the first"""),
]
for old, new in EDITS:
    assert s.count(old) == 1, "anchor not found: " + old[:60]
    s = s.replace(old, new)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("v3d33_tex.c: applied")
