#!/usr/bin/env python3
"""Resolve and download armhf Debian bookworm packages for the MRG5 X11 test.

The box (192.168.3.60) has no route off its own /24, so packages are fetched
here in WSL and installed on the box with dpkg/apt-get from a local directory.

Usage (from the repository root inside WSL):
    python3 work/desktop/fetch-x11-debs.py --out work/desktop/bundle \
        --pkgs work/desktop/x11-core.pkglist

Dependency closure is computed from the armhf Packages index; conflicts and
pre-depends are honoured, `|` alternatives take the first candidate that exists.
"""
import argparse
import hashlib
import lzma
import os
import re
import subprocess
import sys
import urllib.request

MIRROR = "http://deb.debian.org/debian"


def fetch(url, dest):
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return dest
    tmp = dest + ".part"
    print(f"  fetch {url}", flush=True)
    with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    os.replace(tmp, dest)
    return dest


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def apt_ver_gt(a, b):
    """Rough version compare that is good enough for a single-suite index."""
    if not b:
        return True
    if not a:
        return False

    def order(v):
        # split into numeric and non-numeric runs; '~' sorts before everything
        out = []
        for part in re.split(r"([0-9]+|[^0-9]+)", v):
            if not part:
                continue
            out.append((0, int(part), "") if part.isdigit() else (1, 0, part))
        return out

    return order(a) > order(b)


def parse_packages(path):
    """Return {package: stanza_dict} for the whole index."""
    pkgs = {}
    with lzma.open(path, "rt", encoding="utf-8", errors="replace") as f:
        stanza = {}
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                if "Package" in stanza:
                    old = pkgs.get(stanza["Package"])
                    # keep the highest version present in the index
                    if old is None or apt_ver_gt(stanza.get("Version", ""),
                                                 old.get("Version", "")):
                        pkgs[stanza["Package"]] = stanza
                stanza = {}
                continue
            if line[0] in " \t" and stanza:
                key = next(reversed(stanza))
                stanza[key] += " " + line.strip()
                continue
            if ":" in line:
                k, v = line.split(":", 1)
                stanza[k.strip()] = v.strip()
    if "Package" in stanza:
        pkgs.setdefault(stanza["Package"], stanza)
    return pkgs


DEP_SPLIT = re.compile(r"\s*,\s*")


def alternatives(field):
    """Yield lists of alternative dependency expressions."""
    if not field:
        return
    for part in DEP_SPLIT.split(field):
        part = part.strip()
        if not part:
            continue
        yield [a.strip() for a in part.split("|")]


def dep_name(expr):
    """'libc6 (>= 2.34) [armhf]' -> 'libc6'"""
    return re.split(r"[\s(\[:]", expr.strip(), 1)[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--pkgs", required=True)
    ap.add_argument("--mirror", default=MIRROR)
    args = ap.parse_args()

    out = args.out
    cache = os.path.join(out, "cache")
    os.makedirs(cache, exist_ok=True)

    wanted = []
    with open(args.pkgs, encoding="utf-8") as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if line:
                wanted.extend(line.split())
    print(f"requested packages ({len(wanted)}): {' '.join(wanted)}")

    index_xz = os.path.join(cache, "Packages.xz")
    fetch(f"{args.mirror}/dists/bookworm/main/binary-armhf/Packages.xz", index_xz)
    print(f"parsing {index_xz} ...", flush=True)
    pkgs = parse_packages(index_xz)
    print(f"index has {len(pkgs)} packages")

    # closure
    queue = list(wanted)
    selected = {}
    missing = []
    while queue:
        name = queue.pop()
        if name in selected:
            continue
        if name not in pkgs:
            missing.append(name)
            continue
        st = pkgs[name]
        selected[name] = st
        for field in ("Pre-Depends", "Depends"):
            for alts in alternatives(st.get(field, "")):
                for expr in alts:
                    cand = dep_name(expr)
                    if cand in pkgs:
                        if cand not in selected:
                            queue.append(cand)
                        break
    if missing:
        sys.exit(f"ERROR: not found in main/binary-armhf: {sorted(set(missing))}")

    files = []
    total = 0
    for name in sorted(selected):
        st = selected[name]
        fn = st["Filename"]
        size = int(st.get("Size", "0"))
        files.append((name, st["Version"], fn, size, st.get("SHA256", "")))
        total += size
    print(f"closure: {len(files)} packages, {total/1e6:.1f} MB")
    for name, ver, fn, size, _ in files:
        print(f"  {name} {ver} {size/1e3:.0f} kB")

    debs = os.path.join(out, "debs")
    os.makedirs(debs, exist_ok=True)
    with open(os.path.join(out, "manifest.txt"), "w", encoding="utf-8") as m:
        for name, ver, fn, size, dig in files:
            m.write(f"{name}\t{ver}\t{os.path.basename(fn)}\t{size}\t{dig}\n")

    got = 0
    for i, (name, ver, fn, size, dig) in enumerate(files, 1):
        dest = os.path.join(debs, os.path.basename(fn))
        print(f"[{i}/{len(files)}] {name} {ver}", flush=True)
        fetch(f"{args.mirror}/{fn}", dest)
        if dig:
            actual = sha256(dest)
            if actual != dig:
                sys.exit(f"ERROR: sha256 mismatch for {dest}: {actual} != {dig}")
        got += os.path.getsize(dest)
    print(f"downloaded {len(files)} debs, {got/1e6:.1f} MB in {debs}")


if __name__ == "__main__":
    main()
