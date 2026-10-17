#!/bin/bash
# Apply the later V3D 3.3 fixes in the release order. Argument: Mesa source root.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
S=$(realpath "${1:?usage: bash apply-fixes.sh <Mesa source root>}")
while read -r fix directory; do
    python3 "$HERE/mesa-$fix.py" "$S/$directory"
done <<'FIXES'
tfuphys src/gallium/drivers/v3d
ownscanout src/gallium/drivers/v3d
tbo33 src/gallium/drivers/v3d
thrsw1 src/broadcom/compiler
unifa33 .
nospill33 .
r3merge33 src/broadcom/compiler
noscratch33 src
tex1d33 src/broadcom/compiler
vpmthrsw33 src/broadcom/compiler
indepblend33 src
lodclamp33 src
d32f33 src
tlbvec33 src/broadcom/compiler
tf33 src/gallium/drivers/v3d
vpmread33 src/broadcom/compiler
centroid33 src/broadcom/compiler
emptybin33 src/gallium/drivers/v3d
tex4words33 src/broadcom/compiler
vecalign33 src/broadcom/compiler
xoruif33 src/gallium/drivers/v3d
samplemask33 src
mszs33 src/gallium/drivers/v3d
loadflush33 src/gallium/drivers/v3d
mstex33 src/gallium/drivers/v3d
vid33 src/broadcom/compiler
blittfu33 src/gallium/drivers/v3d
FIXES
