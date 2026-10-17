"""Run with python3 -m unittest discover -s tests."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "certificate", Path(__file__).resolve().parents[1] / "kernel/certify-release.py")
certificate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(certificate)


def archive(entries):
    data = bytearray()
    for name, content, mode in entries + [("TRAILER!!!", b"", 0)]:
        name = name.encode() + b"\0"
        fields = [1, mode, 0, 0, 1, 0, len(content), 0, 0, 0, 0, len(name), 0]
        data.extend(b"070701" + ''.join(f'{n:08x}' for n in fields).encode() + name)
        data.extend(b"\0" * (-len(data) % 4))
        data.extend(content)
        data.extend(b"\0" * (-len(data) % 4))
    return bytes(data)


class CertificateTests(unittest.TestCase):
    clean = [("root/.ssh/authorized_keys", b"", 0o100600)]

    def test_empty_authorized_keys(self):
        certificate.check_archive(archive(self.clean))

    def test_rejects_key_material_and_invalid_archives(self):
        cases = [
            [],
            [("root/.ssh/authorized_keys", b"key", 0o100600)],
            [("root/.ssh/authorized_keys", b"", 0o120777)],
            self.clean * 2,
            self.clean + [("etc/key", b"ssh-ed25519 AAAAtest", 0o100600)],
            self.clean + [("etc/key", b"-----BEGIN OPENSSH PRIVATE KEY-----", 0o100600)],
            self.clean + [("../escape", b"", 0o100600)],
        ]
        for entries in cases:
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                certificate.check_archive(archive(entries))
        for data in (archive(self.clean)[:-8], archive(self.clean) + b"extra"):
            with self.assertRaises(ValueError):
                certificate.check_archive(data)

    def test_certificate_removed_when_image_or_embedded_archive_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "arch/arm/boot").mkdir(parents=True)
            (output / "usr").mkdir()
            image = output / "zImage"
            image.write_bytes(b"kernel")
            (output / "arch/arm/boot/zImage").write_bytes(b"kernel")
            data = archive(self.clean)
            (output / "usr/initramfs_data.cpio").write_bytes(data)
            (output / "usr/initramfs_inc_data").write_bytes(data)
            (output / "vmlinux").write_bytes(b"prefix" + data)
            sidecar = Path(str(image) + ".release")
            certificate.certify(output, image)
            self.assertIn("rescue_ssh_keys=none", sidecar.read_text())
            image.write_bytes(b"modified")
            with self.assertRaises(ValueError):
                certificate.certify(output, image)
            self.assertFalse(sidecar.exists())
            image.write_bytes(b"kernel")
            certificate.certify(output, image)
            (output / "vmlinux").write_bytes(b"different initramfs")
            with self.assertRaises(ValueError):
                certificate.certify(output, image)
            self.assertFalse(sidecar.exists())
