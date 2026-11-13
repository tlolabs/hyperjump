#!/usr/bin/env python3
"""Trusted weekly controller: wait for Mac releases, publish verified native assets."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import quote

import native_package as package
import weekly_release_smoke as ledger

PATTERN = r"v[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?"
TARGETS = ["linux-x64", "windows-x64"]


def outputs(values):
    text = "".join(f"{key}={value}\n" for key, value in values.items())
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            stream.write(text)
    else:
        print(text, end="")


def mac_snapshot(api, release):
    if release.get("draft") is not False or not release.get("published_at"):
        return None
    release_id = ledger.positive_int(release.get("id"), "release ID")
    assets = list(api.pages(f"{api.root}/releases/{release_id}/assets"))
    mac = []
    for asset in assets:
        name = asset.get("name", "")
        if (isinstance(name, str) and re.fullmatch(
                r"Hyper[ .-]Jump[-. ].*(?:macos|darwin|osx).*\.(?:dmg|pkg|zip)", name, re.I)
                and asset.get("state") == "uploaded" and type(asset.get("size")) is int and asset["size"] > 0):
            mac.append({"id": ledger.positive_int(asset.get("id"), "Mac asset ID"), "name": name,
                        "size": asset["size"], "updated_at": asset.get("updated_at"),
                        "digest": asset.get("digest")})
    if not mac:
        return None
    return {"release_id": release_id, "tag": ledger.validate_tag(release["tag_name"]),
            "mac_assets": sorted(mac, key=lambda asset: asset["id"])}


def select(api, baseline, claim=False):
    gate = ledger.Gate(api)
    ledger.validate_baseline(baseline, api.repo)
    known_tags = {entry["tag"]: entry["sha"] for entry in baseline["entries"]}
    for row in gate.tags(PATTERN):
        if row["tag"] in known_tags and known_tags[row["tag"]] != row["sha"]:
            raise ledger.GateError("Baselined release tag moved; cannot pair changed code with its existing Mac build")
    matrix, summary = gate.select(PATTERN, TARGETS, baseline=baseline)
    releases = {}
    for release in api.pages(f"{api.root}/releases"):
        tag = release.get("tag_name")
        if tag in releases:
            raise ledger.GateError("Ambiguous release tag: " + str(tag))
        releases[tag] = release
    eligible, plan, waiting, existing = [], {}, 0, 0
    snapshots = {}
    for item in matrix["include"]:
        package.identity(item)
        tag = item["tag"]
        if tag not in snapshots:
            release = releases.get(tag)
            snapshots[tag] = mac_snapshot(api, release) if release else None
        snapshot = snapshots[tag]
        if snapshot is None:
            waiting += 1
            continue
        assets = list(api.pages(f"{api.root}/releases/{snapshot['release_id']}/assets"))
        names = {package.archive_name(item), package.archive_name(item) + ".smoke.json"}
        if any(asset.get("name") in names for asset in assets):
            existing += 1
            continue
        eligible.append(item)
        plan[package.artifact_name(item)] = snapshot
    matrix = {"include": eligible}
    summary.update(new=len(eligible), waiting_for_published_mac_release=waiting, existing_native_assets=existing)
    if claim and eligible:
        _, attempt, url = ledger.current_run(api)
        if attempt != 1:
            raise ledger.GateError("Automatic retries are disabled")
        # Resolve again immediately before claiming, not by release target_commitish
        # (which is often an ambiguous branch name).
        actual = {row["tag"]: row["sha"] for row in gate.tags(PATTERN)}
        if any(actual.get(item["tag"]) != item["sha"] for item in eligible):
            raise ledger.GateError("Tag moved before claim")
        # Complete every last-moment readiness check before the first claim.
        for item in eligible:
            assets = verify_release(api, item, plan[package.artifact_name(item)])
            names = {package.archive_name(item), package.archive_name(item) + ".smoke.json"}
            if any(asset.get("name") in names for asset in assets):
                raise ledger.GateError("Native asset appeared before claim; nothing claimed")
        gate.claim(matrix, url)
    ledger.emit_outputs(matrix, summary)
    outputs({"release_plan": json.dumps(plan, separators=(",", ":"))})
    return matrix, plan


def verify_release(api, item, snapshot):
    actual = ledger.Gate(api).tags(re.escape(item["tag"]))
    if actual != [{"tag": item["tag"], "sha": item["sha"]}]:
        raise ledger.GateError("Release tag moved or disappeared; publication refused")
    identifier = ledger.positive_int(snapshot.get("release_id"), "release ID")
    release = api.request(f"{api.root}/releases/{identifier}")
    if release.get("tag_name") != item["tag"] or mac_snapshot(api, release) != snapshot:
        raise ledger.GateError("Published release or its Mac asset changed; publication refused")
    return list(api.pages(f"{api.root}/releases/{identifier}/assets"))


def smoke_passed(api, item):
    run, attempt, _ = ledger.current_run(api)
    if attempt != 1:
        raise ledger.GateError("Automatic retries are disabled")
    jobs = list(api.pages(f"{api.root}/actions/runs/{run}/attempts/{attempt}/jobs", key="jobs"))
    matches = [job for job in jobs if job.get("name") == f"Smoke {item['tag']} ({item['target']})"]
    if len(matches) > 1:
        raise ledger.GateError("Ambiguous smoke job identity")
    return len(matches) == 1 and matches[0].get("status") == "completed" and matches[0].get("conclusion") == "success"


def validate_artifact(directory, item):
    directory = Path(directory).resolve(strict=True)
    archive = directory / package.archive_name(item)
    receipt = directory / (archive.name + ".smoke.json")
    if set(path.name for path in directory.iterdir()) != {archive.name, receipt.name}:
        raise ledger.GateError("Expected exactly one archive and its smoke receipt")
    if any(path.is_symlink() or not path.is_file() for path in (archive, receipt)) or receipt.stat().st_size > 100000:
        raise ledger.GateError("Unsafe artifact files")
    result = json.loads(receipt.read_text(encoding="utf-8"))
    if set(result) != {"schema", "tag", "sha", "target", "archive", "sha256", "size", "smoke"}:
        raise ledger.GateError("Unexpected artifact receipt fields")
    if (result["schema"] != 1 or any(result[key] != value for key, value in item.items())
            or result["archive"] != archive.name or result["sha256"] != package.sha256(archive)
            or type(result["size"]) is not int or result["size"] != archive.stat().st_size or result["size"] <= 0):
        raise ledger.GateError("Archive identity, length or SHA-256 mismatch")
    package.validate_smoke(result["smoke"])
    return archive, receipt, result


def upload(api, release_id, path):
    endpoint = f"https://uploads.github.com/{api.root}/releases/{release_id}/assets?name={quote(path.name, safe='')}"
    result = subprocess.run(["gh", "api", "--hostname", "github.com", "--method", "POST",
                             "-H", "Content-Type: application/octet-stream", endpoint,
                             "--input", str(path)], capture_output=True, text=True, timeout=300, check=False)
    if result.returncode:
        raise ledger.GateError(f"Upload was not confirmed for {path.name}; inspect release before any manual retry: {result.stderr}")
    asset = json.loads(result.stdout)
    if asset.get("name") != path.name or asset.get("size") != path.stat().st_size or asset.get("state") != "uploaded":
        raise ledger.GateError("Uploaded asset response mismatch; outcome uncertain, inspect manually")
    asset_id = ledger.positive_int(asset.get("id"), "uploaded asset ID")
    expected = "sha256:" + package.sha256(path)
    if asset.get("digest"):
        if asset["digest"] != expected:
            raise ledger.GateError("Uploaded asset digest differs from tested bytes")
    else:
        # Older GitHub responses may omit digest. Download and hash rather than
        # silently downgrading artifact integrity to a filename/size check.
        with tempfile.TemporaryDirectory(prefix="verify-release-upload-") as temp:
            downloaded = Path(temp) / "asset"
            with downloaded.open("wb") as stream:
                subprocess.run(["gh", "api", "--hostname", "github.com", "--method", "GET",
                                "-H", "Accept: application/octet-stream",
                                f"{api.root}/releases/assets/{asset_id}"], stdout=stream, check=True, timeout=300)
            if package.sha256(downloaded) != expected.removeprefix("sha256:"):
                raise ledger.GateError("Downloaded release asset differs from tested bytes")
    return asset_id


def publish(api, item, snapshot, directory):
    if not smoke_passed(api, item):
        raise ledger.GateError("The matching native build/package/smoke job did not pass")
    archive, receipt, evidence = validate_artifact(directory, item)
    assets = verify_release(api, item, snapshot)
    if any(asset.get("name") in {archive.name, receipt.name} for asset in assets):
        raise ledger.GateError("Release asset name already exists; never overwrite or automatically retry")
    run, attempt, url = ledger.current_run(api)
    evidence["provenance"] = {"repository": api.repo, "run_id": run, "run_attempt": attempt,
                              "run_url": url, "release": snapshot}
    receipt.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    # Receipt describes tested bytes, not a promise that both uploads completed.
    # A partial/uncertain upload fails this job and is never automatically retried.
    uploaded = []
    for path in (receipt, archive):
        assets = verify_release(api, item, snapshot)
        if any(asset.get("name") == path.name for asset in assets):
            raise ledger.GateError("Asset appeared during publication; refusing overwrite")
        uploaded.append(upload(api, snapshot["release_id"], path))
        print(f"Confirmed upload: {path.name}")
    verify_release(api, item, snapshot)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
            stream.write(f"Published tested {item['target']} package for {item['tag']} ({item['sha']}).\n\nSHA-256: `{evidence['sha256']}`\n")
    return uploaded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["select", "eligible", "publish"])
    parser.add_argument("--baseline-file")
    parser.add_argument("--claim", action="store_true")
    parser.add_argument("--directory", default="release-assets")
    args = parser.parse_args()
    try:
        api = ledger.GitHub(os.environ["GITHUB_REPOSITORY"])
        if args.command == "select":
            if not args.baseline_file:
                raise ledger.GateError("The immutable baseline is required")
            select(api, ledger.load_baseline(args.baseline_file, api.repo), args.claim)
        else:
            item = package.identity(json.loads(os.environ["NATIVE_ITEM"]))
            if args.command == "eligible":
                passed = smoke_passed(api, item)
                outputs({"passed": str(passed).lower(), "artifact_name": package.artifact_name(item)})
                if not passed:
                    print("No passing native smoke job: no assets will be published.")
            else:
                plan = json.loads(os.environ["RELEASE_PLAN"])
                publish(api, item, plan[package.artifact_name(item)], args.directory)
        return 0
    except (ledger.GateError, ValueError, KeyError, OSError, subprocess.SubprocessError) as exc:
        print(f"Native release failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
