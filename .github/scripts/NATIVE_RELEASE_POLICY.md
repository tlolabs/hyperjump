# Hyper Jump weekly native release contract

The owner's 2026-11-13 request authorizes Windows/Linux build, smoke and publication alongside their locally built/tested macOS release. It supersedes only the earlier no-publication restriction. The existing [once-per-tag smoke ledger](WEEKLY_SMOKE_POLICY.md), baseline, Sunday schedule and no-automatic-retry behavior remain unchanged.

## Eligibility and identity

- `native_release.py select` first applies the existing exact repository/tag/peeled-SHA/target ledger and tracked baseline. Only Linux x64 and Windows x64 are supported here.
- Before claiming, require a published, non-draft, same-tag release containing a nonempty uploaded Hyper Jump Mac DMG/PKG/ZIP. This is the owner's publication signal, not a claim that CI has independently verified the Mac build. Tags awaiting that asset remain unclaimed.
- Retain the selected release ID and Mac asset IDs/names/sizes/update timestamps/digests. Recheck the peeled tag SHA, release identity and Mac assets before and after publication. A moved tag or changed/deleted/replaced Mac asset stops publication.
- A known baseline tag moved to another SHA fails closed rather than pairing changed code with an old Mac binary. For future tags, the owner must keep version tags immutable and publish the Mac build from that tagged source. CI verifies release metadata, not source provenance inside an arbitrary DMG.
- Checkout the immutable source SHA. Do not overlay current application code on older tags. Future tags must include `native_smoke.py` and the opt-in `--smoke-report` entry point.

## Native verification

Build the full PyInstaller one-directory distribution on Ubuntu 24.04 x64 or Windows Server 2025 x64 using Python 3.12. Copy all runtime libraries/data, safely dereferencing in-tree symlinks, into a versioned tar.gz/ZIP. Freshly extract it away from the source/build directory and launch it with isolated user paths and a 90-second deadline. Fail on a nonzero exit, timeout, missing/invalid receipt, blank framebuffer, missing Panda model/audio files or failed gameplay operations.

The real app opens a 640x480 native software-rendered Panda3D window, runs 33 task frames, samples a nonblank framebuffer, exercises firing/enemy spawning/shield/restart, and exits normally. Xvfb supplies the Linux display; the bundled TinyDisplay backend removes a GPU requirement on both native runners. Silent audio avoids reliance on a hosted sound device: audio files are checked, **audio playback is not**. This is deliberately not a full regression suite or GPU/audio compatibility guarantee.

## Publication and failures

The isolated publisher executes only controller code from the scheduled workflow commit. Build jobs have read-only contents access, no signing/publishing secrets and no stored checkout credentials. Artifacts are current-run-only and content-digest checked by the GitHub artifact actions; the publisher independently validates identity, exact file set, SHA-256, size and smoke receipt, and checks the exact native job succeeded via the current run-attempt jobs API.

Passing targets can publish independently even if the other target fails. Before any upload, fail on existing archive/receipt names. Upload the tested-byte receipt, then the unchanged archive, to the pinned release ID, without clobber. Verify each uploaded SHA-256 (download/hash if GitHub omits its digest). No release creation, tag changes, Mac builds, signing or automatic retries. Uploads are not atomic: an interrupted attempt can leave only a receipt or an uncertain asset. Inspect the release/run before explicitly authorized manual recovery; never erase/reset the ledger or blindly replay an upload.

`success` in the original smoke status means the native build/package/extraction/smoke/artifact-transfer job passed, **not** that release uploads succeeded. The separately named Publish job and its summary report publication. The consumed ledger prevents another weekly attempt even after a publish failure. Re-run attempts are blocked. Strict recovery of provably never-executed claimed smoke jobs remains the sole automatic recovery case.

## Local validation (no Mac build)

```sh
python3 -m unittest discover -s .github/scripts -p 'test_*.py' -v
python3 -m py_compile main.py native_smoke.py .github/scripts/*.py
actionlint .github/workflows/weekly-release-smoke.yml
```

Read-only gate diagnosis (does not claim or publish):

```sh
GITHUB_REPOSITORY=tlolabs/hyperjump python3 .github/scripts/native_release.py select \
  --baseline-file .github/weekly-smoke-baseline.json
```

There are no push, tag, release, pull-request or dispatch triggers. Native runtime claims require an actual scheduled run on a new eligible release; offline controller/packaging tests alone do not prove Windows or Linux execution.
