#!/usr/bin/env python3
"""Add the V3D GPU node to the DTB our kernel boots with.

The vendor's device tree names the block only by compatible
("gpu-mmu@f1201000": brcm,bcm7268-v3d / brcm,v3d-v3.3.1.0) and gives it no reg
and no interrupts, because nexus drives V3D from userspace.  The in-tree
drm/v3d driver matches "brcm,7268-v3d" and needs the four windows by name; the
addresses are the ones the upstream binding documents for this very chip
(Documentation/devicetree/bindings/gpu/brcm,bcm-v3d.yaml), and they agree with
the vendor node: hub f1200000 + 0x1000 is the MMU the vendor node is named for.

usage: add-v3d-node.py <in.dtb> <out.dtb> [out.dts]
"""
import subprocess
import sys

SRC, DST = sys.argv[1], sys.argv[2]
DTS_OUT = sys.argv[3] if len(sys.argv) > 3 else None

NODE = """
\t\tgpu@f1200000 {
\t\t\tcompatible = "brcm,7268-v3d";
\t\t\treg = <0xf1200000 0x4000 0xf1208000 0x4000 0xf1204100 0x100 0xf1204000 0x100>;
\t\t\treg-names = "hub\\0core0\\0gca\\0bridge";
\t\t\tinterrupts = <0x00 0x4e 0x04 0x00 0x4d 0x04>;
\t\t\tinterrupt-parent = <0x01>;
\t\t};
"""

dts = subprocess.run(["dtc", "-I", "dtb", "-O", "dts", SRC],
                     capture_output=True, text=True, check=True).stdout

anchor = "\t\tgpu-mmu@f1201000 {"
assert dts.count(anchor) == 1, "vendor gpu-mmu node not found exactly once"
assert "gpu@f1200000" not in dts, "the node is already there"
dts = dts.replace(anchor, NODE.lstrip("\n") + "\n" + anchor)

if DTS_OUT:
    open(DTS_OUT, "w", newline="\n").write(dts)

p = subprocess.run(["dtc", "-I", "dts", "-O", "dtb", "-o", DST],
                   input=dts, capture_output=True, text=True)
sys.stderr.write(p.stderr)
if p.returncode:
    sys.exit("dtc failed")

back = subprocess.run(["dtc", "-I", "dtb", "-O", "dts", DST],
                      capture_output=True, text=True, check=True).stdout
i = back.index("gpu@f1200000")
print("node as it comes back out of the new dtb:")
print(back[i - 2:i + 400].split("gpu-mmu")[0].rstrip())
