#!/usr/bin/env python3
"""Resize the V3D GPU's reserved region (v3d-pool@30000000, made by add-v3d-pool.py) in a DTB
(checks/53 §9 item 12). drm/v3d (v3d33-contig.py) takes the size from the region's reg, so the
DTB is the only change; the region must stay below 4 GiB and inside the memory node.

Why (2026-09-30): Luanti on a big modded server (Your Land) filled the 256 MiB pool: GPU memory
in use rose from 92 MB to 314 MB (bo_stats, 7294 buffers) within 46 s, the next
DRM_IOCTL_V3D_CREATE_BO failed, and Mesa's v3d_cl_ensure_space_with_branch() dereferenced the
NULL buffer (SIGSEGV in v3d_bo_map).

usage: resize-v3d-pool.py <in.dtb> <out.dtb> <size-MiB>        (in: dtb-kms-pool-bt.bin)
"""
import re
import subprocess
import sys

SRC, DST, MIB = sys.argv[1], sys.argv[2], int(sys.argv[3])
BASE = 0x30000000
SIZE = MIB << 20

dts = subprocess.run(["dtc", "-q", "-I", "dtb", "-O", "dts", SRC],
                     capture_output=True, text=True, check=True).stdout
old = re.search(r"(\tv3d-pool@30000000 \{\n\t+reg = <0x00 0x30000000 0x00 )(0x[0-9a-f]+)(>;)", dts)
assert old, "v3d-pool@30000000 with a 64-bit reg not found"
end = BASE + SIZE
assert end <= 1 << 32, "the region must end below 4 GiB"

# inside the first memory bank, and clear of every other reserved region
mem = re.search(r"device_type = \"memory\";\n\t+reg = <0x00 0x00 0x00 (0x[0-9a-f]+)", dts)
assert mem and end <= int(mem.group(1), 16), "the region must lie inside memory bank 0"
for name, hi, lo, shi, slo in re.findall(
        r"\t\t([\w@-]+) \{\n(?:\t\t\t[^\n]*\n)*?\t\t\treg = <(0x[0-9a-f]+) (0x[0-9a-f]+) (0x[0-9a-f]+) (0x[0-9a-f]+)>;",
        dts.split("reserved-memory {", 1)[1].split("\n\t};", 1)[0]):
    if name.startswith("v3d-pool@"):
        continue
    b = (int(hi, 16) << 32) | int(lo, 16)
    e = b + ((int(shi, 16) << 32) | int(slo, 16))
    assert e <= BASE or b >= end, "overlaps %s (0x%x-0x%x)" % (name, b, e)

print("v3d-pool@30000000: 0x%x -> 0x%x (%d MiB, ends 0x%x)" % (int(old.group(2), 16), SIZE, MIB, end))
dts = dts[:old.start()] + old.group(1) + "0x%x" % SIZE + old.group(3) + dts[old.end():]
p = subprocess.run(["dtc", "-q", "-I", "dts", "-O", "dtb", "-o", DST],
                   input=dts, capture_output=True, text=True)
sys.exit(p.returncode)
