#!/usr/bin/env python3
"""Package, freshly extract, and verify Hyper Jump without third-party helpers."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import zipfile

CHECKS = ["window", "bundled-model", "bundled-audio-files", "rendered-frame",
          "primary-fire", "enemy-spawn", "shield-toggle", "restart"]


def identity(item):
    if set(item) != {"tag", "sha", "target"}:
        raise ValueError("Unexpected package identity fields")
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?", item["tag"]) or len(item["tag"]) > 80:
        raise ValueError("Unsupported version tag")
    if not re.fullmatch(r"[0-9a-f]{40}", item["sha"]) or item["target"] not in {"linux-x64", "windows-x64"}:
        raise ValueError("Unsupported SHA or native target")
    return item


def artifact_name(item):
    identity(item)
    return "hyperjump-" + hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest()


def archive_name(item):
    identity(item)
    extension = ".zip" if item["target"] == "windows-x64" else ".tar.gz"
    return f"Hyper-Jump-{item['tag']}-{item['target']}{extension}"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package(source, output, item):
    source, output = Path(source).resolve(strict=True), Path(output)
    if source.name != "Hyper Jump" or not source.is_dir():
        raise ValueError("Expected the complete PyInstaller Hyper Jump directory")
    executable = source / ("Hyper Jump.exe" if item["target"] == "windows-x64" else "Hyper Jump")
    if not executable.is_file() or not (source / "_internal").is_dir():
        raise ValueError("Incomplete PyInstaller distribution")
    for path in source.rglob("*"):
        if not path.is_file() and not path.is_dir() and not path.is_symlink():
            raise ValueError("Special file in package")
        if path.is_symlink() and not path.resolve(strict=True).is_relative_to(source):
            raise ValueError("Package symlink escapes distribution")
    output.mkdir(parents=True, exist_ok=True)
    target = output / archive_name(item)
    if target.exists():
        raise ValueError("Refusing to replace an existing package")
    # Copy/dereference in-tree PyInstaller library symlinks to make archives
    # portable, then archive every runtime dependency and data file.
    with tempfile.TemporaryDirectory(prefix="hyperjump-package-") as temp:
        staged = Path(temp) / "Hyper Jump"
        shutil.copytree(source, staged, symlinks=False)
        if item["target"] == "windows-x64":
            with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(staged.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(staged.parent).as_posix())
        else:
            with tarfile.open(target, "x:gz") as archive:
                archive.add(staged, arcname="Hyper Jump")
    return target


def safe_member(name):
    path = PurePosixPath(name)
    if ("\\" in name or ":" in name or path.is_absolute() or ".." in path.parts
            or not path.parts or path.parts[0] != "Hyper Jump"):
        raise ValueError("Unsafe archive member: " + name)


def extract(archive, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    names = set()
    if str(archive).endswith(".zip"):
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                safe_member(member.filename)
                if member.filename in names or stat.S_ISLNK(member.external_attr >> 16):
                    raise ValueError("Duplicate or linked archive member")
                names.add(member.filename)
            bundle.extractall(destination)
    else:
        with tarfile.open(archive, "r:gz") as bundle:
            for member in bundle.getmembers():
                safe_member(member.name)
                if member.name in names or not (member.isfile() or member.isdir()):
                    raise ValueError("Duplicate, linked, or special archive member")
                names.add(member.name)
            bundle.extractall(destination, filter="data")


def validate_smoke(result):
    if (not isinstance(result, dict) or result.get("schema") != 1 or result.get("status") != "passed"
            or result.get("checks") != CHECKS or result.get("frames") != 33
            or type(result.get("width")) is not int or result["width"] < 320
            or type(result.get("height")) is not int or result["height"] < 240
            or type(result.get("sampled_colors")) is not int or result["sampled_colors"] <= 4):
        raise ValueError("Incomplete native render/gameplay smoke evidence")
    return result


def smoke(archive, item, output):
    expected = "Windows" if item["target"] == "windows-x64" else "Linux"
    import platform
    if platform.system() != expected or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise ValueError("Smoke must run natively on the matching x64 operating system")
    archive = Path(archive).resolve(strict=True)
    if archive.name != archive_name(item):
        raise ValueError("Unexpected archive name")
    before = sha256(archive)
    with tempfile.TemporaryDirectory(prefix="hyperjump-extracted-smoke-") as temp:
        root = Path(temp)
        extract(archive, root / "unpacked")
        executable = root / "unpacked" / "Hyper Jump" / ("Hyper Jump.exe" if expected == "Windows" else "Hyper Jump")
        report = root / "result.json"
        home = root / "home"
        home.mkdir()
        env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), XDG_CONFIG_HOME=str(home),
                   XDG_DATA_HOME=str(home), APPDATA=str(home), LOCALAPPDATA=str(home))
        # No source-tree CWD, PYTHONPATH, virtualenv fallback, or inherited
        # dynamic-library paths: test the distributable, not the build tree.
        for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
            env.pop(key, None)
        result = subprocess.run([str(executable), "--smoke-report", str(report)],
                                cwd=home, env=env, timeout=90, check=False)
        if result.returncode:
            raise ValueError(f"Packaged application exited {result.returncode}")
        evidence = validate_smoke(json.loads(report.read_text(encoding="utf-8")))
    if before != sha256(archive):
        raise ValueError("Archive changed during smoke test")
    receipt = {"schema": 1, **identity(item), "archive": archive.name,
               "sha256": before, "size": archive.stat().st_size, "smoke": evidence}
    Path(output).write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["package", "smoke"])
    parser.add_argument("--source", default="dist/Hyper Jump")
    parser.add_argument("--output", default="release-assets")
    args = parser.parse_args()
    item = identity(json.loads(os.environ["NATIVE_ITEM"]))
    output = Path(args.output)
    if args.command == "package":
        package(args.source, output, item)
    else:
        smoke(output / archive_name(item), item, output / (archive_name(item) + ".smoke.json"))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            stream.write("artifact_name=" + artifact_name(item) + "\n")


if __name__ == "__main__":
    main()
