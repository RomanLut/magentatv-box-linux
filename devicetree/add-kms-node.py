#!/usr/bin/env python3
"""Add the node that binds the MRG5 KMS driver (drivers/gpu/drm/mrg5).

It carries no registers: the driver talks to the display path through
mrg5-p50.c, which owns the per-frame list.  Its only job is to make the
driver's presence a property of the device tree, so the same kernel boots
without KMS on a DTB that lacks it.

usage: add-kms-node.py <in.dtb> <out.dtb> [out.dts]      (in: dtb-v3d.bin)
"""
import subprocess
import sys

SRC, DST = sys.argv[1], sys.argv[2]
DTS_OUT = sys.argv[3] if len(sys.argv) > 3 else None

NODE = "\tmrg5-kms {\n\t\tcompatible = \"mrg5,kms\";\n\t};\n\n"

dts = subprocess.run(["dtc", "-I", "dtb", "-O", "dts", SRC],
                     capture_output=True, text=True, check=True).stdout
anchor = "\trdb {"
assert dts.count(anchor) == 1, "root-level rdb node not found exactly once"
assert "mrg5,kms" not in dts, "the node is already there"
assert "brcm,7268-v3d" in dts, "expected the V3D dtb as input"
dts = dts.replace(anchor, NODE + anchor)

if DTS_OUT:
    open(DTS_OUT, "w", newline="\n").write(dts)
p = subprocess.run(["dtc", "-q", "-I", "dts", "-O", "dtb", "-o", DST],
                   input=dts, capture_output=True, text=True)
if p.returncode:
    sys.exit("dtc failed:\n" + p.stderr)

back = subprocess.run(["dtc", "-I", "dtb", "-O", "dts", DST],
                      capture_output=True, text=True, check=True).stdout
i = back.index("mrg5-kms {")
print(back[i - 1:i + 60].rstrip())
print("gpu node present:", "brcm,7268-v3d" in back)
