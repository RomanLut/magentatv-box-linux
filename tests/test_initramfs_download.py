"""Exercise the builder's downloader without network access (Linux build host)."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest


class DownloadTests(unittest.TestCase):
    def test_verified_cache_fallback_and_partial_cleanup(self):
        source = (Path(__file__).resolve().parents[1] /
                  "initramfs/build-initramfs.sh").read_text()
        function = source[source.index("fetch() {"):source.index('\nmkdir -p "$W"')]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "cache"
            cache.mkdir()
            good = root / "good"
            good.write_bytes(b"verified release source")
            bad = root / "bad"
            bad.write_bytes(b"corrupt download")
            sha = hashlib.sha256(good.read_bytes()).hexdigest()

            def fetch(*urls):
                return subprocess.run(
                    ["bash", "-c", 'set -euo pipefail\nW=$1\nshift\n' +
                     function + '\nfetch "$@"', "test", str(cache), sha,
                     "source.tar.gz", *urls], capture_output=True)

            target = cache / "source.tar.gz"
            target.write_bytes(b"old incomplete download")
            result = fetch(bad.as_uri(), good.as_uri())
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(target.read_bytes(), good.read_bytes())
            self.assertFalse(Path(str(target) + ".part").exists())
            # A verified cached copy needs no reachable URL.
            self.assertEqual(fetch((root / "missing").as_uri()).returncode, 0)
            target.unlink()
            result = fetch(bad.as_uri(), (root / "missing").as_uri())
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(target.exists())
            self.assertFalse(Path(str(target) + ".part").exists())
