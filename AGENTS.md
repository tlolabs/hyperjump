# Repository guidance

## CI scheduling and native release policy (owner update, 2026-11-13)
This section supersedes the 2026-11-07 prohibition on native package publication for the owner's explicit cross-platform release request. Other prior safeguards remain in effect.

Tom builds and tests all macOS releases locally. Hosted native CI runs once weekly on Sunday morning Pacific for new version tags only, and only after a published matching GitHub release has a Mac distribution asset. Existing tags remain baselined. Native GitHub-managed Windows x64 and Linux x64 runners build the immutable tagged source, package it, and smoke-test the freshly extracted archives. Passing target packages and integrity/provenance receipts may be attached to that existing release. Never create a release, move a tag, overwrite an existing asset, build macOS on GitHub, or enable archived workflows. Do not run full regression suites automatically.

Preserve the durable once-per-tag/commit/target ledger and no-automatic-retry behavior, including publication failures. A missing Mac release must not consume a build attempt. Only previously claimed work proven never to have executed can recover under the existing strict policy. Keep build jobs read-only and publication in a separate trusted-controller job. Runtime authentication, signature verification and artifact-integrity safeguards must not be weakened. Local development and release verification requirements still apply. See `.github/scripts/NATIVE_RELEASE_POLICY.md`.

## Archived legacy automation

The former custom workflows are preserved, inactive, under `.github/workflow-archive/2026-11-08/`, with original paths and hashes recorded in its manifest. This archive supersedes older descriptions of automatic builds, retries, reporting, and release publishing. Do not move them back to `.github/workflows/`, enable, or dispatch them without a new explicit owner instruction. GitHub-managed security services remain separate and enabled.
