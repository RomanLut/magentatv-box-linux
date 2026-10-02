#!/usr/bin/env python3
"""Mesa v3d: keep the tiled shadow of this process's own scanout buffer while
it is unchanged (checks/53 §9 item 12).

The V3D texture unit cannot read linear (raster) memory, so Mesa samples a
linear resource through a tiled shadow copy, which v3d_update_shadow_texture()
refreshes before a draw - but skips only when

        shadow->writes == orig->writes && orig->bo->private

The X server's screen is a scanout buffer that Mesa allocates on the display
device through renderonly and imports, so it is never "private", and every
draw that reads the screen (window copies, moves, scrolling) re-converted the
whole 1920x1080 screen, changed or not: 9 211 conversions in 2 s of
x11perf -move, ~4 ms each.  Unchanged upstream up to at least 25.0 (vc4 has
the same line).

A scanout buffer this process allocated itself is written only by this
process and read by the display engine, so for it the writes counter is
trusted too.  Two things make that correct:
  - own_scanout is set only where v3d_resource_create() allocates the buffer
    through renderonly for PIPE_BIND_SCANOUT - not for imports, which get
    rsc->scanout as well and keep the conservative behaviour;
  - a write is counted only when its job is submitted, so the jobs writing the
    original are flushed before the comparison - the same flush the
    conversion itself (v3d_tfu) does before converting.  Without it the
    screen showed stale content wherever a pending job had drawn.

usage: mesa-ownscanout.py <mesa src/gallium/drivers/v3d>
"""
import io
import os
import sys

D = sys.argv[1]

EDITS = {
"v3d_resource.h": [
("""        struct renderonly_scanout *scanout;
""", """        struct renderonly_scanout *scanout;
        /* checks/53: a scanout buffer this process allocated itself (not an
         * import); only we write it, so its writes counter can be trusted
         */
        bool own_scanout;
"""),
],
"v3d_resource.c": [
("""                if (!rsc->scanout) {
                        fprintf(stderr, "Failed to create scanout resource\\n");
                        goto fail;
                }
""", """                if (!rsc->scanout) {
                        fprintf(stderr, "Failed to create scanout resource\\n");
                        goto fail;
                }
                rsc->own_scanout = true;
"""),
("""        if (shadow->writes == orig->writes && orig->bo->private)
                return;
""", """        /* checks/53: pending writes to the original are counted only when
         * their job is submitted - flush them before trusting the counter,
         * as the conversion (v3d_tfu) does before converting
         */
        v3d_flush_jobs_writing_resource(v3d, &orig->base, V3D_FLUSH_DEFAULT,
                                        false);
        if (shadow->writes == orig->writes &&
            (orig->bo->private || orig->own_scanout))
                return;
"""),
],
}

for name, edits in EDITS.items():
    p = os.path.join(D, name)
    s = io.open(p, encoding="utf-8").read()
    if "own_scanout" in s:
        print(name + ": already there")
        continue
    for old, new in edits:
        assert s.count(old) == 1, name + ": anchor not found:\n" + old
        s = s.replace(old, new)
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)
    print(name + ": applied")
