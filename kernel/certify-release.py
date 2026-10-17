#!/usr/bin/env python3
"""Check a completed kernel build's initramfs and write its image-builder sidecar.

Usage: python3 certify-release.py <kernel output directory> <copied zImage>
This is a local build check, not a signature or third-party attestation.
"""
import hashlib
import gzip
from pathlib import Path
import re
import stat
import sys


def check_archive(data):
    """Validate newc without extracting paths or following archive symlinks."""
    offset = 0
    authorized = []
    names = set()
    key = re.compile(rb"(?:ssh-(?:rsa|ed25519|dss)|ecdsa-sha2-nistp\d+|"
                     rb"sk-(?:ssh-ed25519|ecdsa-sha2-nistp256)@openssh\.com)\s+AAAA")
    while True:
        header = data[offset:offset + 110]
        if len(header) != 110 or header[:6] != b"070701":
            raise ValueError("invalid or truncated newc archive")
        fields = [int(header[i:i + 8], 16) for i in range(6, 110, 8)]
        mode, size, name_size = fields[1], fields[6], fields[11]
        start = offset + 110
        name_bytes = data[start:start + name_size]
        if not name_size or len(name_bytes) != name_size or name_bytes[-1:] != b"\0":
            raise ValueError("invalid archive name")
        name = name_bytes[:-1].decode("utf-8")
        start = (start + name_size + 3) & ~3
        content = data[start:start + size]
        if len(content) != size:
            raise ValueError("truncated archive content")
        offset = (start + size + 3) & ~3
        if name == "TRAILER!!!":
            if size or any(data[offset:]):
                raise ValueError("unexpected data after archive trailer")
            break
        if name.startswith("./"):
            name = name[2:]
        if name in names or name.startswith("/") or ".." in name.split("/"):
            raise ValueError("duplicate or unsafe archive path")
        names.add(name)
        if name.rsplit("/", 1)[-1] == "authorized_keys":
            if name != "root/.ssh/authorized_keys" or not stat.S_ISREG(mode) or content:
                raise ValueError("unexpected or nonempty authorized_keys")
            authorized.append(name)
        if key.search(content) or re.search(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----", content):
            raise ValueError("SSH public key or private key text in initramfs")
    if authorized != ["root/.ssh/authorized_keys"]:
        raise ValueError("missing empty rescue authorized_keys")


def certify(output, image):
    sidecar = Path(str(image) + ".release")
    sidecar.unlink(missing_ok=True)
    blob = image.read_bytes()
    if blob != (output / "arch/arm/boot/zImage").read_bytes():
        raise ValueError("image differs from the completed build")
    archive = (output / "usr/initramfs_data.cpio").read_bytes()
    check_archive(archive)
    embedded = (output / "usr/initramfs_inc_data").read_bytes()
    unpacked = gzip.decompress(embedded) if embedded.startswith(b"\x1f\x8b") else embedded
    if unpacked != archive:
        raise ValueError("embedded archive differs from checked initramfs")
    if embedded not in (output / "vmlinux").read_bytes():
        raise ValueError("checked initramfs is not embedded in vmlinux")
    sidecar.write_text(
        f"sha256={hashlib.sha256(blob).hexdigest()}\n"
        f"initramfs_sha256={hashlib.sha256(archive).hexdigest()}\n"
        "rescue_ssh_keys=none\n", encoding="ascii")
    print(f"Release initramfs verified: {sidecar}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    try:
        certify(Path(sys.argv[1]), Path(sys.argv[2]))
    except (OSError, ValueError) as error:
        sys.exit(f"Release verification failed: {error}")
