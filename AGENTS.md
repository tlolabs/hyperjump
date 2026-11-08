# Repository guidance

## CI scheduling policy (owner update, 2026-11-07)

This section supersedes older instructions for automatic CI coverage and publication.

Hosted native CI runs once weekly on Sunday morning Pacific, and only for newly introduced version tags. Existing tags are baselined. The active workflow builds supported Linux and Windows targets and performs basic startup smoke checks only. It does not run macOS builds, full regression suites, automatic retries, publishing, signing, or release creation. Legacy workflows are retained but disabled. GitHub-managed security services remain separate. Runtime authentication, signature verification, and artifact-integrity safeguards must not be weakened. Local development and release verification requirements still apply before any separately authorized publication.

## Archived legacy automation

The former custom workflows are preserved, inactive, under `.github/workflow-archive/2026-11-08/`, with original paths and hashes recorded in its manifest. This archive supersedes older descriptions of automatic builds, retries, reporting, and release publishing. Do not move them back to `.github/workflows/`, enable, or dispatch them without a new explicit owner instruction. GitHub-managed security services remain separate and enabled.
