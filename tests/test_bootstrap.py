import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from forge_visual_enhancer import bootstrap


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ve-bootstrap-test-")
        self.root = Path(self.temp.name)
        self.setup = self.root / ".setup"
        self.runtime = self.root / "runtime" / "Visual-Enhancer"
        self.paths = patch.multiple(bootstrap, ROOT=self.root, SETUP=self.setup,
                                    STATUS=self.setup / "status.json", CONFIG=self.root / "config.json",
                                    RUNTIME=self.runtime)
        self.paths.start()
        self.env = patch.dict(os.environ, {}, clear=False)
        self.env.start()
        os.environ.pop("VISUAL_ENHANCER_EXE", None)

    def tearDown(self):
        self.env.stop()
        self.paths.stop()
        self.temp.cleanup()

    def test_reuses_configured_program_without_downloading(self):
        app = self.root / "existing"
        app.mkdir()
        (app / "VE_CLI.exe").write_bytes(b"cli")
        (app / "Visual Enhancer.exe").write_bytes(b"gui")
        (self.root / "config.json").write_text(json.dumps({"visual_enhancer_exe": str(app / "VE_CLI.exe")}))
        with patch.object(bootstrap, "_download", side_effect=AssertionError("unexpected download")):
            bootstrap._worker()
        self.assertEqual(json.loads((self.setup / "status.json").read_text())["phase"], "ready")
        self.assertTrue((app / "VE_CLI.exe").is_file())

    def test_full_install_uses_verified_archive_and_is_idempotent(self):
        sample = self.root / "sample.zip"
        with zipfile.ZipFile(sample, "w") as z:
            z.writestr("VE_CLI.exe", b"test cli")
            z.writestr("Visual Enhancer.exe", b"test gui")
            z.writestr("bin/nested/file.txt", b"test resource")
        def fake_download(target):
            target.write_bytes(sample.read_bytes())
        with patch.object(bootstrap, "_find_existing_cli", return_value=None), \
             patch.object(bootstrap, "_download", side_effect=fake_download) as download, \
             patch.object(bootstrap, "CLI_SHA256", hashlib.sha256(b"test cli").hexdigest()):
            bootstrap._worker()
            bootstrap._worker()
        self.assertEqual(download.call_count, 1)
        self.assertEqual((self.runtime / "bin/nested/file.txt").read_bytes(), b"test resource")
        self.assertEqual(json.loads((self.setup / "status.json").read_text())["phase"], "ready")

    def test_bad_paths_and_links_are_rejected(self):
        for index, name in enumerate(("../escape.txt", "/absolute.txt", "C:/outside.txt", "..\\escape2.txt")):
            archive = self.root / f"bad-{index}.zip"
            with zipfile.ZipFile(archive, "w") as z:
                item = zipfile.ZipInfo(name)
                item.filename = name  # Avoid Windows' separator normalization in the fixture.
                z.writestr(item, b"no")
            with self.subTest(name=name):
                with self.assertRaises(RuntimeError):
                    bootstrap._extract(archive, self.root / f"out-{index}")
        archive = self.root / "link.zip"
        link = zipfile.ZipInfo("link")
        link.create_system = 3
        link.external_attr = 0o120777 << 16
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr(link, "../outside")
        with self.assertRaises(RuntimeError):
            bootstrap._extract(archive, self.root / "links")
        self.assertFalse((self.root.parent / "escape.txt").exists())

    def test_wrong_checksum_never_installs(self):
        class FakeResponse(io.BytesIO):
            pass
        with patch.object(bootstrap.urllib.request, "urlopen", return_value=FakeResponse(b"bad archive")):
            with self.assertRaisesRegex(RuntimeError, "SHA-256"):
                bootstrap._download(self.root / "download.zip", expected="0" * 64)
        self.assertFalse(self.runtime.exists())

    def test_existing_incomplete_runtime_and_config_are_not_overwritten(self):
        self.runtime.mkdir(parents=True)
        marker = self.runtime / "user-file.txt"
        marker.write_text("keep")
        with patch.object(bootstrap, "_find_existing_cli", return_value=None), \
             patch.object(bootstrap, "_download", side_effect=AssertionError("unexpected download")):
            bootstrap._worker()
        self.assertEqual(marker.read_text(), "keep")
        self.assertEqual(json.loads((self.setup / "status.json").read_text())["phase"], "error")

    def test_lock_excludes_a_second_worker(self):
        with bootstrap._setup_lock() as first:
            with bootstrap._setup_lock() as second:
                self.assertTrue(first)
                self.assertFalse(second)

    def test_start_setup_spawns_background_worker(self):
        with patch.object(bootstrap, "_configured_cli", return_value=None), \
             patch.object(bootstrap.subprocess, "Popen", return_value=types.SimpleNamespace()) as spawn:
            message = bootstrap.start_setup()
        self.assertEqual(spawn.call_count, 1)
        self.assertIn("Preparing", message)
        self.assertEqual(spawn.call_args.args[0][-1], "--worker")


if __name__ == "__main__":
    unittest.main(verbosity=2)
