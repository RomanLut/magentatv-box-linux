#!/usr/bin/env python3
"""Reserve 256 MiB of RAM for the V3D GPU alone, as the vendor's graphics heap
(checks/53 §9 item 12).

Adds to /reserved-memory a no-map region at 0x30000000 (inside the range the
vendor's Nexus graphics heap occupies on the stock system, 0x20000000..) and
points the gpu@f1200000 node at it with memory-region.  Linux then neither
allocates from nor maps that memory; drm/v3d manages it itself (no
"shared-dma-pool" compatible on purpose: a DMA pool would be mapped whole at
boot, and 256 MiB does not fit the 240 MiB vmalloc area of this kernel).
The kernel command line keeps CMA below it (cma=64M@0x10000000-0x28000000).

usage: add-v3d-pool.py <in.dtb> <out.dtb> [out.dts]      (in: dtb-kms.bin)
"""
import re
import subprocess
import sys

SRC, DST = sys.argv[1], sys.argv[2]
DTS_OUT = sys.argv[3] if len(sys.argv) > 3 else None
BASE, SIZE = 0x30000000, 0x10000000

dts = subprocess.run(["dtc", "-I", "dtb", "-O", "dts", SRC],
                     capture_output=True, text=True, check=True).stdout
assert "v3d-pool@" not in dts, "the region is already there"
assert dts.count("\tgpu@f1200000 {") == 1, "gpu@f1200000 not found exactly once"
phandle = max(int(h, 16) for h in re.findall(r"phandle = <(0x[0-9a-f]+)>", dts)) + 1

anchor = "\t\treserved-nodma@00000000 {"
assert dts.count(anchor) == 1, "reserved-memory anchor not found"
node = ("\t\tv3d-pool@%x {\n"
        "\t\t\treg = <0x00 0x%x 0x00 0x%x>;\n"
        "\t\t\tno-map;\n"
        "\t\t\tphandle = <0x%x>;\n"
        "\t\t};\n\n") % (BASE, BASE, SIZE, phandle)
dts = dts.replace(anchor, node + anchor)

gpu = "\t\tgpu@f1200000 {\n\t\t\tcompatible = \"brcm,7268-v3d\";\n"
assert dts.count(gpu) == 1, "gpu node text not as expected"
dts = dts.replace(gpu, gpu + "\t\t\tmemory-region = <0x%x>;\n" % phandle)

if DTS_OUT:
    open(DTS_OUT, "w", newline="\n").write(dts)
p = subprocess.run(["dtc", "-q", "-I", "dts", "-O", "dtb", "-o", DST],
                   input=dts, capture_output=True, text=True)
if p.returncode:
    sys.exit("dtc failed:\n" + p.stderr)

back = subprocess.run(["dtc", "-I", "dtb", "-O", "dts", DST],
                      capture_output=True, text=True, check=True).stdout
i = back.index("v3d-pool@")
print(back[i - 2:i + 110].rstrip())
j = back.index("gpu@f1200000 {")
print(back[j:j + 120].rstrip())
