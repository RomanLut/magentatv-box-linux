#!/usr/bin/env python3
"""Mesa v3dx_emit.c: let the LOD go 1/256 above the base level when there is
no mipmapping, on V3D 3.x too (defect 21, checks/53 §5).

On V3D 3.x the TMU clamps the computed LOD into the texture state's
Min/Max Level-of-Detail and picks the min or mag filter from the clamped
value. emit_one_texture() clamps the LOD range to the view's levels, so a
texture without mipmaps (every NPOT texture in GLES 2) gets exactly [0, 0]:
the TMU always "magnifies", and a NEAREST min filter with a LINEAR mag filter
comes out linear when the texture is shrunk. dEQP-GLES2 texture.filtering
{2d,cube}.{nearest_linear,linear_nearest}_clamp_*_npot: 16 failures, errors
up to 124/255 (thin stripes blurred grey); the POT variants have mip levels
and pass.

The V3D 4.x sampler state already handles this, in
v3d_upload_sampler_state_variant(): "If we're not doing inter-miplevel
filtering, we need to clamp the LOD so that we only sample from baselevel.
However, we need to still allow the calculated LOD to be fractionally over
the baselevel, so that the HW can decide between the min and mag filters" -
min and max LOD at most 1/256. The same for 3.x: with PIPE_TEX_MIPFILTER_NONE
the range is [base, base + 1/256] at most (the fields are s8.8, 1/256 is one
step). With a mip filter the clamp to the last level stays: above it a
LINEAR mip filter would blend in a level that does not exist.

usage: mesa-lodclamp33.py <mesa src/src>
"""
import io
import os
import sys

p = os.path.join(sys.argv[1], "gallium/drivers/v3d/v3dx_emit.c")
s = io.open(p, encoding="utf-8").read()
if "defect 21" in s:
    print("v3dx_emit.c: already there")
    sys.exit(0)
old = """        /* Set up the sampler swizzle if we're doing 16-bit sampling.  For
         * 32-bit, we leave swizzling up to the shader compiler.
"""
new = """        /* checks/53 defect 21: as the 4.x sampler state does, without
         * mipmapping let the LOD go fractionally over the base level, so the
         * TMU can still choose between the min and mag filters (it decides
         * on the clamped LOD).
         */
        if (psampler->min_mip_filter == PIPE_TEX_MIPFILTER_NONE) {
                float base = psview->u.tex.first_level;

                unpacked.min_level_of_detail =
                        base + MIN2(MAX2(psampler->min_lod, 0), 1.0 / 256.0);
                unpacked.max_level_of_detail =
                        base + MIN2(MAX2(psampler->max_lod, psampler->min_lod),
                                    1.0 / 256.0);
        }

""" + old
assert s.count(old) == 1, "anchor not found"
io.open(p, "w", encoding="utf-8", newline="\n").write(s.replace(old, new))
print("v3dx_emit.c: applied")
