#!/usr/bin/env python3
"""Mesa v3d gallium driver: transform feedback on V3D 3.x as the vendor driver
programs it (defect 24, checks/53 §5).

With upstream Mesa every transform feedback job on V3D 3.3 stalled the binner
until the GPU reset. The stock system's driver (libv3ddriver.so, captured with
stocktf.c) records the same draw without any count packet:

    bin list:   Tile Binning Mode Cfg, Flush VCD, Start Tile Binning,
                Wait for transform feedback (block count 0),
                Occlusion query counter, Branch to sub-list, Flush
    sub-list:   state, Transform Feedback Enable + spec + address,
                Vertex Array Prims (POINTS_TF), Return

Tested one by one on the box: Primitive Counts Feedback (opcode 72) in the
bin list epilogue hangs the binner on 3.3, and so did Transform Feedback Flush
and Count after each TF draw; the vendor list has neither. So on 3.x:
- v3dx_draw.c: Wait for transform feedback (block count 0) right after Start
  Tile Binning, as the vendor list; no TF flush-and-count after the draw;
- v3dx_job.c: no Primitive Counts Feedback;
- v3dx_emit.c: job->tf_enabled is set on 3.x too, so later draws that read a
  TF-written buffer wait for TF (v3d_emit_wait_for_tf_if_needed);
- the TRANSFORM_FEEDBACK_PRIMITIVES_WRITTEN count comes from the CPU, as Mesa
  did before it used the GPU counters (v3d_tf_statistics_record): the draw's
  primitives times instances, clamped to the room left in each buffer. With
  only a vertex shader (3.x has no geometry shaders) that is exact. The TF
  write offsets and the stream output targets' recorded vertex counts
  (DrawTransformFeedback) advance by the vertices actually written;
- v3d_job.c / v3d_context.c: no GPU counter readback and no job flush for it.

usage: mesa-tf33.py <mesa src/gallium/drivers/v3d>
"""
import io
import os
import sys

FILES = {
"v3dx_draw.c": [
("""        cl_emit(&job->bcl, START_TILE_BINNING, bin);
""", """        cl_emit(&job->bcl, START_TILE_BINNING, bin);

#if V3D_VERSION < 40
        /* checks/53 defect 24: the vendor driver's bin list on 3.3 waits
         * for transform feedback here, and has no TF count packets.
         */
        cl_emit(&job->bcl, WAIT_FOR_TRANSFORM_FEEDBACK, wait) {
                wait.block_count = 0;
        }
#endif
"""),
("""static void
v3d_update_job_ez(struct v3d_context *v3d, struct v3d_job *job)
""", """#if V3D_VERSION < 40
/**
 * checks/53 defect 24: V3D 3.x has no usable primitive counters (Primitive
 * Counts Feedback hangs the binner), so count the primitives written to the
 * transform feedback buffers here, as Mesa did before it used the counters.
 * Only a vertex shader exists on 3.x, so the count is the draw's primitives,
 * limited to the room left in the buffers.
 */
static void
v3d33_record_tf_prims(struct v3d_context *v3d,
                      const struct pipe_draw_info *info,
                      const struct pipe_draw_indirect_info *indirect,
                      const struct pipe_draw_start_count_bias *draw)
{
        struct v3d_streamout_stateobj *so = &v3d->streamout;
        struct pipe_stream_output_info *soinfo =
                &v3d->prog.bind_vs->base.stream_output;
        uint32_t count = indirect && indirect->count_from_stream_output ?
                v3d_stream_output_target_get_vertex_count(indirect->count_from_stream_output) :
                draw->count;
        uint32_t verts_per_prim =
                u_vertices_for_prims(u_base_prim_type(info->mode), 1);
        uint32_t prims = u_prims_for_vertices(info->mode, count) *
                MAX2(info->instance_count, 1);

        for (int i = 0; i < so->num_targets; i++) {
                struct pipe_stream_output_target *target = so->targets[i];
                if (!target || !soinfo->stride[i])
                        continue;
                uint32_t stride = soinfo->stride[i] * 4;
                uint32_t used = so->offsets[i] * stride;
                uint32_t room = target->buffer_size > used ?
                        (target->buffer_size - used) / stride / verts_per_prim : 0;
                prims = MIN2(prims, room);
        }

        v3d->tf_prims_generated += prims;
        for (int i = 0; i < so->num_targets; i++) {
                so->offsets[i] += prims * verts_per_prim;
                if (so->targets[i]) {
                        v3d_stream_output_target(so->targets[i])->recorded_vertex_count +=
                                prims * verts_per_prim;
                }
        }
}
#endif

static void
v3d_update_job_ez(struct v3d_context *v3d, struct v3d_job *job)
"""),
("""        if (v3d->streamout.num_targets)
                cl_emit(&job->bcl, TRANSFORM_FEEDBACK_FLUSH_AND_COUNT, flush);
""", """#if V3D_VERSION >= 40
        if (v3d->streamout.num_targets)
                cl_emit(&job->bcl, TRANSFORM_FEEDBACK_FLUSH_AND_COUNT, flush);
#endif
"""),
("""        for (int i = 0; i < v3d->streamout.num_targets; i++)
                v3d->streamout.offsets[i] += draws[0].count;
""", """#if V3D_VERSION >= 40
        for (int i = 0; i < v3d->streamout.num_targets; i++)
                v3d->streamout.offsets[i] += draws[0].count;
#else
        if (v3d->streamout.num_targets)
                v3d33_record_tf_prims(v3d, info, indirect, &draws[0]);
#endif
"""),
],
"v3dx_emit.c": [
("""#else /* V3D_VERSION < 40 */
                        cl_emit(&job->bcl, TRANSFORM_FEEDBACK_ENABLE, tfe) {""",
"""#else /* V3D_VERSION < 40 */
                        /* checks/53 defect 24: lets later draws wait for
                         * TF before reading a buffer it wrote.
                         */
                        job->tf_enabled |= v3d_transform_feedback_enabled(v3d);
                        cl_emit(&job->bcl, TRANSFORM_FEEDBACK_ENABLE, tfe) {"""),
],
"v3dx_job.c": [
("""                if (job->tf_enabled || job->needs_primitives_generated) {
                        /* Write primitive counts to memory. */""",
"""                /* checks/53 defect 24: this packet hangs the binner on
                 * V3D 3.3; 3.x counts TF primitives on the CPU.
                 */
                if (V3D_VERSION >= 40 &&
                    (job->tf_enabled || job->needs_primitives_generated)) {
                        /* Write primitive counts to memory. */"""),
],
"v3d_job.c": [
("""                if (job->needs_primitives_generated ||
                    (v3d->streamout.num_targets &&
                     job->tf_draw_calls_queued > 0))
                        v3d_read_and_accumulate_primitive_counters(v3d);""",
"""                if (v3d->screen->devinfo.ver >= 40 && /* checks/53 defect 24 */
                    (job->needs_primitives_generated ||
                     (v3d->streamout.num_targets &&
                      job->tf_draw_calls_queued > 0)))
                        v3d_read_and_accumulate_primitive_counters(v3d);"""),
],
"v3d_context.c": [
("""        struct v3d_job *job = v3d_get_job_for_fbo(v3d);
        if (job->draw_calls_queued == 0)
                return;

        /* In order to get up-to-date primitive counts""",
"""        /* checks/53 defect 24: 3.x counts at draw time, on the CPU. */
        if (v3d->screen->devinfo.ver < 40)
                return;

        struct v3d_job *job = v3d_get_job_for_fbo(v3d);
        if (job->draw_calls_queued == 0)
                return;

        /* In order to get up-to-date primitive counts"""),
],
}

for name, edits in FILES.items():
    p = os.path.join(sys.argv[1], name)
    s = io.open(p, encoding="utf-8").read()
    if "defect 24" in s:
        print(name + ": already there")
        continue
    for old, new in edits:
        assert s.count(old) == 1, name + ": anchor not found: " + old[:60]
        s = s.replace(old, new)
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)
    print(name + ": applied")
