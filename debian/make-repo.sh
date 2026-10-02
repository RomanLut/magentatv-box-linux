#!/bin/bash
# Build the apt repository index for the local (offline) X11 repo.
# Run from the repository root; needs dpkg-scanpackages (dpkg-dev).
#   bash work/desktop/make-repo.sh
set -euo pipefail
cd "$(dirname "$0")/bundle"
rm -f Packages Packages.gz
dpkg-scanpackages --multiversion debs /dev/null > Packages
gzip -9 -k Packages
echo "packages in index: $(grep -c '^Package:' Packages)"
ls -l Packages Packages.gz
