#!/usr/bin/env python3
"""Mesa: the sample mask (glSampleCoverage, glSampleMaski) on V3D 3.x
(defect 31, checks/53 §5).

Gallium turns glSampleCoverage into a sample mask, which the V3D driver hands
to the hardware with the Sample State packet (v3dx_emit.c, V3D_VERSION >= 40).
That packet is 4.1+ (v3d_packet_v33.xml), so on 3.3 the mask was dropped: a
quad drawn with coverage 0.0 covered every sample (dEQP-GLES3
multisample.fbo_{4,max}_samples proportionality_sample_coverage[_inverted],
sample_coverage_invert: "Image should be completely black").

On 3.x the fragment shader applies it instead, as it already applies
gl_SampleMask and alpha-to-coverage: setmsf(msf & mask) at the end. The mask
travels in the fragment shader key (key->sample_coverage was already set,
and V3D_DIRTY_SAMPLE_STATE already recomputes the key); like the other two,
it keeps early fragment tests off.

usage: mesa-samplemask33.py <mesa src>
"""
import io
import os
import sys

FILES = {
"broadcom/compiler/v3d_compiler.h": [
("""        bool sample_coverage;
        bool sample_alpha_to_coverage;
        bool sample_alpha_to_one;
        /* Mask of which color render targets are present. */""",
"""        bool sample_coverage;
        bool sample_alpha_to_coverage;
        bool sample_alpha_to_one;
        /* checks/53 defect 31: V3D 3.x has no Sample State packet, the
         * shader applies the sample mask (with sample_coverage).
         */
        uint8_t sample_mask;
        /* Mask of which color render targets are present. */"""),
],
"broadcom/compiler/nir_to_vir.c": [
("""        if (c->fs_key->sample_alpha_to_coverage && c->output_color_var[0]) {
                struct nir_variable *var = c->output_color_var[0];""",
"""        /* checks/53 defect 31 */
        if (c->devinfo->ver < 40 && c->fs_key->sample_coverage) {
                vir_SETMSF_dest(c, vir_nop_reg(),
                                vir_AND(c,
                                        vir_MSF(c),
                                        vir_uniform_ui(c, c->fs_key->sample_mask)));
        }

        if (c->fs_key->sample_alpha_to_coverage && c->output_color_var[0]) {
                struct nir_variable *var = c->output_color_var[0];"""),
("""            !c->fs_key->sample_alpha_to_coverage &&
            c->output_sample_mask_index == -1 &&""",
"""            !c->fs_key->sample_alpha_to_coverage &&
            !(c->devinfo->ver < 40 && c->fs_key->sample_coverage) &&
            c->output_sample_mask_index == -1 &&"""),
],
"gallium/drivers/v3d/v3d_program.c": [
("""                key->sample_coverage = (v3d->rasterizer->base.multisample &&
                                        v3d->sample_mask != (1 << V3D_MAX_SAMPLES) - 1);
""", """                key->sample_coverage = (v3d->rasterizer->base.multisample &&
                                        v3d->sample_mask != (1 << V3D_MAX_SAMPLES) - 1);
                /* checks/53 defect 31 */
                if (v3d->screen->devinfo.ver < 40 && key->sample_coverage)
                        key->sample_mask = v3d->sample_mask;
"""),
],
}

for name, edits in FILES.items():
    p = os.path.join(sys.argv[1], name)
    s = io.open(p, encoding="utf-8").read()
    if "defect 31" in s:
        print(name + ": already there")
        continue
    for old, new in edits:
        assert s.count(old) == 1, name + ": anchor not found: " + old[:60]
        s = s.replace(old, new)
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)
    print(name + ": applied")
