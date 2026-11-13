import copy
import io
import json
import os
from pathlib import Path
import stat
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import native_package as package

ITEM = {"tag": "v1.2.3", "sha": "a" * 40, "target": "linux-x64"}
EVIDENCE = {"schema": 1, "status": "passed", "checks": package.CHECKS,
            "frames": 33, "width": 640, "height": 480, "sampled_colors": 20,
            "audio": "files-present; silent CI backend, playback not tested"}


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "dist" / "Hyper Jump"
        (self.source / "_internal").mkdir(parents=True)
        (self.source / "_internal" / "asset.mp3").write_bytes(b"sound")
        self.executable = self.source / "Hyper Jump"
        self.executable.write_bytes(b"fixture executable")
        self.executable.chmod(0o755)
        self.output = self.root / "release-assets"

    def tearDown(self):
        self.temp.cleanup()

    def test_linux_archive_round_trip_preserves_runtime_and_executable(self):
        archive = package.package(self.source, self.output, ITEM)
        dest = self.root / "extracted"
        package.extract(archive, dest)
        app = dest / "Hyper Jump"
        self.assertEqual((app / "_internal" / "asset.mp3").read_bytes(), b"sound")
        self.assertEqual((app / "Hyper Jump").read_bytes(), b"fixture executable")
        self.assertTrue((app / "Hyper Jump").stat().st_mode & stat.S_IXUSR)

    def test_windows_archive_round_trip(self):
        self.executable.rename(self.source / "Hyper Jump.exe")
        item = {**ITEM, "target": "windows-x64"}
        archive = package.package(self.source, self.output, item)
        package.extract(archive, self.root / "extracted")
        self.assertTrue((self.root / "extracted/Hyper Jump/Hyper Jump.exe").is_file())
        self.assertTrue((self.root / "extracted/Hyper Jump/_internal/asset.mp3").is_file())

    @unittest.skipIf(os.name == "nt", "symlink fixture")
    def test_in_tree_link_is_dereferenced(self):
        (self.source / "alias").symlink_to("_internal/asset.mp3")
        archive = package.package(self.source, self.output, ITEM)
        with tarfile.open(archive) as bundle:
            self.assertTrue(bundle.getmember("Hyper Jump/alias").isfile())

    @unittest.skipIf(os.name == "nt", "symlink fixture")
    def test_outside_link_is_rejected(self):
        (self.source / "alias").symlink_to(sys.executable)
        with self.assertRaises(ValueError):
            package.package(self.source, self.output, ITEM)

    def test_missing_runtime_is_rejected(self):
        self.executable.unlink()
        with self.assertRaises(ValueError):
            package.package(self.source, self.output, ITEM)

    def test_package_is_not_overwritten(self):
        package.package(self.source, self.output, ITEM)
        with self.assertRaises(ValueError):
            package.package(self.source, self.output, ITEM)

    def test_path_traversal_rejected(self):
        for name in ("../escape", "/absolute", "Hyper Jump/../../escape", "C:/escape", "Hyper Jump\\escape", "other/path"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                package.safe_member(name)

    def test_archive_link_rejected(self):
        archive = self.root / "bad.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            info = tarfile.TarInfo("Hyper Jump/link")
            info.type, info.linkname = tarfile.SYMTYPE, "../../outside"
            bundle.addfile(info)
        with self.assertRaises(ValueError):
            package.extract(archive, self.root / "extracted")

    def test_zip_duplicate_and_links_rejected(self):
        archive = self.root / "bad.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            info = zipfile.ZipInfo("Hyper Jump/link")
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            bundle.writestr(info, "../../outside")
        with self.assertRaises(ValueError):
            package.extract(archive, self.root / "extracted")

    def test_archive_extract_requires_new_directory(self):
        archive = package.package(self.source, self.output, ITEM)
        with self.assertRaises(FileExistsError):
            package.extract(archive, self.source)

    def test_identity_rejects_unsupported_or_unsafe_inputs(self):
        for item in ({**ITEM, "tag": "v1.2.3/../../x"}, {**ITEM, "sha": "x"},
                     {**ITEM, "target": "macos-arm64"}, {**ITEM, "extra": "field"}):
            with self.subTest(item=item), self.assertRaises(ValueError):
                package.identity(item)

    def test_artifact_names_are_identity_specific(self):
        self.assertNotEqual(package.artifact_name(ITEM), package.artifact_name({**ITEM, "sha": "b" * 40}))
        self.assertNotEqual(package.artifact_name(ITEM), package.artifact_name({**ITEM, "target": "windows-x64"}))

    def test_smoke_evidence_rejects_weak_success(self):
        package.validate_smoke(EVIDENCE)
        for change in ({"status": "failed"}, {"frames": 1}, {"checks": []},
                       {"width": 0}, {"height": None}, {"sampled_colors": 1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                package.validate_smoke({**EVIDENCE, **change})

    def test_wrong_native_platform_rejected_before_launch(self):
        with patch("platform.system", return_value="Darwin"), self.assertRaises(ValueError):
            package.smoke("missing", ITEM, self.root / "report.json")

    @unittest.skipIf(os.name == "nt", "POSIX executable fixture, not an actual game run")
    def test_extracted_archive_orchestration_without_source_tree(self):
        code = ("#!" + sys.executable + "\nimport json, pathlib, sys, os\n"
                "assert pathlib.Path('../_internal/asset.mp3').exists() is False\n"
                "assert pathlib.Path(__file__).parent.joinpath('_internal/asset.mp3').read_bytes() == b'sound'\n"
                "assert 'PYTHONPATH' not in os.environ\n"
                "pathlib.Path(sys.argv[2]).write_text(" + repr(json.dumps(EVIDENCE)) + ")\n")
        self.executable.write_text(code)
        archive = package.package(self.source, self.output, ITEM)
        import shutil
        shutil.rmtree(self.source)
        with patch("platform.system", return_value="Linux"), patch("platform.machine", return_value="x86_64"):
            receipt = package.smoke(archive, ITEM, self.root / "receipt.json")
        self.assertEqual(receipt["sha256"], package.sha256(archive))
        self.assertEqual(receipt["smoke"]["status"], "passed")

    def test_nonzero_exit_timeout_and_missing_report_fail(self):
        archive = package.package(self.source, self.output, ITEM)
        import subprocess
        for behavior in (subprocess.CompletedProcess([], 7), subprocess.TimeoutExpired([], 90), subprocess.CompletedProcess([], 0)):
            kwargs = {"side_effect": behavior} if isinstance(behavior, Exception) else {"return_value": behavior}
            with patch("platform.system", return_value="Linux"), patch("platform.machine", return_value="x86_64"), patch.object(package.subprocess, "run", **kwargs):
                with self.assertRaises((ValueError, OSError, subprocess.TimeoutExpired)):
                    package.smoke(archive, ITEM, self.root / "receipt.json")
            self.assertFalse((self.root / "receipt.json").exists())


if __name__ == "__main__":
    unittest.main()
