import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import native_package as package
import native_release as release
import weekly_release_smoke as ledger
from test_native_package import ITEM, EVIDENCE
from test_weekly_release_smoke import FakeAPI, REPO, ROOT, status

MAC = {"id": 51, "name": "Hyper.Jump-macOS-arm64.dmg", "size": 123,
       "state": "uploaded", "updated_at": "2026-11-13T00:00:00Z", "digest": "sha256:" + "a" * 64}
RELEASE = {"id": 21, "tag_name": ITEM["tag"], "draft": False, "published_at": "2026-11-13T00:00:00Z"}
ENV = {"GITHUB_REPOSITORY": REPO, "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
       "GITHUB_SERVER_URL": "https://github.com"}


class ReleaseAPI(FakeAPI):
    def __init__(self):
        super().__init__(tags=[{"name": ITEM["tag"], "commit": {"sha": ITEM["sha"]}}])
        self.releases = [copy.deepcopy(RELEASE)]
        self.assets = [copy.deepcopy(MAC)]
        self.jobs = [{"name": f"Smoke {ITEM['tag']} ({ITEM['target']})", "status": "completed", "conclusion": "success"}]
        self.reads = []

    def pages(self, endpoint, key=None):
        self.reads.append(endpoint)
        if endpoint == ROOT + "/releases":
            return iter(copy.deepcopy(self.releases))
        if endpoint.endswith("/assets"):
            return iter(copy.deepcopy(self.assets))
        if endpoint.endswith("/jobs"):
            return iter(copy.deepcopy(self.jobs))
        return super().pages(endpoint, key)

    def request(self, endpoint, payload=None):
        if endpoint == ROOT + "/releases/21":
            return copy.deepcopy(self.releases[0])
        return super().request(endpoint, payload)


def baseline(entries=None):
    return {"schema": 1, "repository": REPO, "captured_at": "2026-11-08T00:00:00Z", "entries": entries or []}


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.api = ReleaseAPI()
        self.env = patch.dict(os.environ, ENV)
        self.env.start()
        self.quiet = contextlib.redirect_stdout(io.StringIO())
        self.quiet.start = self.quiet.__enter__
        self.quiet.start()
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.archive = self.directory / package.archive_name(ITEM)
        self.archive.write_bytes(b"tested fixture archive")
        self.receipt = self.directory / (self.archive.name + ".smoke.json")
        self.evidence = {"schema": 1, **ITEM, "archive": self.archive.name,
                         "size": self.archive.stat().st_size, "sha256": package.sha256(self.archive), "smoke": EVIDENCE}
        self.receipt.write_text(json.dumps(self.evidence))
        self.snapshot = release.mac_snapshot(self.api, RELEASE)

    def tearDown(self):
        self.temp.cleanup()
        self.quiet.__exit__(None, None, None)
        self.env.stop()

    def test_mac_snapshot_recognizes_actual_release_names(self):
        for name in ("Hyper.Jump-macOS-arm64.dmg", "Hyper Jump-macOS-x64.dmg", "Hyper-Jump-v1.2.3-darwin.zip"):
            self.api.assets[0]["name"] = name
            self.assertIsNotNone(release.mac_snapshot(self.api, RELEASE))

    def test_missing_draft_or_empty_mac_waits_without_claim(self):
        mutations = (lambda: self.api.releases.clear(),
                     lambda: self.api.releases[0].update(draft=True),
                     lambda: self.api.releases[0].update(published_at=None),
                     lambda: self.api.assets.clear(),
                     lambda: self.api.assets[0].update(size=0),
                     lambda: self.api.assets[0].update(state="new"),
                     lambda: self.api.assets[0].update(name="release-notes-macos.txt"))
        for mutate in mutations:
            self.api = ReleaseAPI()
            mutate()
            matrix, _ = release.select(self.api, baseline(), claim=True)
            self.assertEqual(matrix["include"], [])
            self.assertEqual(self.api.writes, [])

    def test_published_mac_release_claims_both_targets_once(self):
        matrix, plan = release.select(self.api, baseline(), claim=True)
        self.assertEqual(len(matrix["include"]), 2)
        self.assertEqual(len(plan), 2)
        self.assertEqual(len(self.api.writes), 2)
        self.assertTrue(all(payload["state"] == "pending" for _, payload in self.api.writes))

    def test_read_only_select_does_not_claim(self):
        matrix, _ = release.select(self.api, baseline())
        self.assertEqual(len(matrix["include"]), 2)
        self.assertEqual(self.api.writes, [])

    def test_baselined_tags_stay_excluded(self):
        rows = [{**ITEM, "target": target} for target in release.TARGETS]
        matrix, _ = release.select(self.api, baseline(rows), claim=True)
        self.assertEqual(matrix["include"], [])
        self.assertEqual(self.api.writes, [])

    def test_baselined_tag_move_fails_before_claim(self):
        old = [{**ITEM, "sha": "b" * 40, "target": target} for target in release.TARGETS]
        with self.assertRaises(ledger.GateError):
            release.select(self.api, baseline(old), claim=True)
        self.assertEqual(self.api.writes, [])

    def test_existing_partial_native_assets_skip_only_affected_target(self):
        self.api.assets.append({"name": self.archive.name + ".smoke.json"})
        matrix, _ = release.select(self.api, baseline(), claim=True)
        self.assertEqual([item["target"] for item in matrix["include"]], ["windows-x64"])
        self.assertEqual(len(self.api.writes), 1)

    def test_consumed_failure_and_success_never_rebuild(self):
        self.api.status_rows = {ITEM["sha"]: [status(state="failure"), status(target="windows-x64", state="success", identifier=2)]}
        matrix, _ = release.select(self.api, baseline(), claim=True)
        self.assertEqual(matrix["include"], [])
        self.assertEqual(self.api.writes, [])

    def test_readiness_change_before_claim_fails_before_any_write(self):
        with patch.object(release, "verify_release", side_effect=ledger.GateError("Mac asset changed")):
            with self.assertRaises(ledger.GateError):
                release.select(self.api, baseline(), claim=True)
        self.assertEqual(self.api.writes, [])

    def test_tag_move_before_claim_fails_before_any_write(self):
        original = ledger.Gate.tags
        count = 0
        def moving(gate, pattern):
            nonlocal count
            count += 1
            return [{"tag": ITEM["tag"], "sha": "b" * 40}] if count > 2 else original(gate, pattern)
        with patch.object(ledger.Gate, "tags", moving), self.assertRaises(ledger.GateError):
            release.select(self.api, baseline(), claim=True)
        self.assertEqual(self.api.writes, [])

    def test_rerun_attempt_is_refused(self):
        with patch.dict(os.environ, {"GITHUB_RUN_ATTEMPT": "2"}):
            with self.assertRaises(ledger.GateError):
                release.select(self.api, baseline(), claim=True)
            with self.assertRaises(ledger.GateError):
                release.smoke_passed(self.api, ITEM)
        self.assertEqual(self.api.writes, [])

    def test_release_or_mac_change_refuses_publication(self):
        for mutation in ({"draft": True}, {"tag_name": "v2.0.0"}):
            self.api.releases = [{**RELEASE, **mutation}]
            with self.assertRaises(ledger.GateError):
                release.verify_release(self.api, ITEM, self.snapshot)
        self.api.releases = [copy.deepcopy(RELEASE)]
        self.api.assets[0]["id"] = 52
        with self.assertRaises(ledger.GateError):
            release.verify_release(self.api, ITEM, self.snapshot)

    def test_moved_tag_refuses_publication(self):
        self.api.tag_rows[0]["commit"]["sha"] = "b" * 40
        with self.assertRaises(ledger.GateError):
            release.verify_release(self.api, ITEM, self.snapshot)

    def test_publish_requires_exact_successful_job(self):
        for jobs in ([], [{**self.api.jobs[0], "conclusion": "failure"}],
                     [{**self.api.jobs[0], "status": "in_progress"}],
                     [{**self.api.jobs[0], "name": "Smoke unrelated"}]):
            self.api.jobs = jobs
            self.assertFalse(release.smoke_passed(self.api, ITEM))
        self.api.jobs = [{"name": f"Smoke {ITEM['tag']} ({ITEM['target']})"}] * 2
        with self.assertRaises(ledger.GateError):
            release.smoke_passed(self.api, ITEM)

    def test_artifact_identity_integrity_and_file_set(self):
        release.validate_artifact(self.directory, ITEM)
        for update in ({"sha": "b" * 40}, {"tag": "v9.9.9"}, {"target": "windows-x64"},
                       {"size": 1}, {"sha256": "0" * 64}, {"smoke": {"status": "passed"}}):
            self.receipt.write_text(json.dumps({**self.evidence, **update}))
            with self.subTest(update=update), self.assertRaises((ValueError, ledger.GateError)):
                release.validate_artifact(self.directory, ITEM)
        self.receipt.write_text(json.dumps(self.evidence))
        (self.directory / "unexpected.py").touch()
        with self.assertRaises(ledger.GateError):
            release.validate_artifact(self.directory, ITEM)

    def test_publication_collision_has_no_upload(self):
        self.api.assets.append({"name": self.archive.name})
        with patch.object(release, "upload") as upload, self.assertRaises(ledger.GateError):
            release.publish(self.api, ITEM, self.snapshot, self.directory)
        upload.assert_not_called()

    def test_passing_target_publishes_receipt_then_tested_archive(self):
        self.api.jobs.append({"name": f"Smoke {ITEM['tag']} (windows-x64)", "status": "completed", "conclusion": "failure"})
        with patch.object(release, "upload", side_effect=[61, 62]) as upload:
            self.assertEqual(release.publish(self.api, ITEM, self.snapshot, self.directory), [61, 62])
        self.assertEqual([call.args[2].name for call in upload.call_args_list], [self.receipt.name, self.archive.name])
        evidence = json.loads(self.receipt.read_text())
        self.assertEqual(evidence["provenance"]["release"], self.snapshot)
        self.assertEqual(evidence["sha256"], package.sha256(self.archive))

    def test_partial_upload_failure_is_not_retried(self):
        with patch.object(release, "upload", side_effect=[61, ledger.GateError("uncertain")]) as upload:
            with self.assertRaises(ledger.GateError):
                release.publish(self.api, ITEM, self.snapshot, self.directory)
        self.assertEqual(upload.call_count, 2)

    def test_upload_digest_is_checked(self):
        asset = {"id": 62, "name": self.archive.name, "size": self.archive.stat().st_size,
                 "state": "uploaded", "digest": "sha256:" + package.sha256(self.archive)}
        result = subprocess.CompletedProcess([], 0, json.dumps(asset), "")
        with patch.object(release.subprocess, "run", return_value=result) as run:
            self.assertEqual(release.upload(self.api, 21, self.archive), 62)
            self.assertIn("https://uploads.github.com/repos/" + REPO + "/releases/21/assets?", run.call_args.args[0][8])
        asset["digest"] = "sha256:" + "0" * 64
        with patch.object(release.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, json.dumps(asset), "")):
            with self.assertRaises(ledger.GateError):
                release.upload(self.api, 21, self.archive)

    def test_uncertain_upload_fails_without_retry(self):
        with patch.object(release.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "timeout")) as run:
            with self.assertRaises(ledger.GateError):
                release.upload(self.api, 21, self.archive)
        self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
