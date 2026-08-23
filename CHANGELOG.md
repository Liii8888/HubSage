# Changelog

## Unreleased

### Added

- Persistent private GitHub mirrors that preserve branches, tags, and reachable
  repository history.
- Isolated WIP publication for explicitly approved dirty worktrees.
- GPT Pro and GPT Pro with Deep Research review modes.
- Byte-for-byte prompt freezing with SHA-256 checks at every lifecycle stage.
- Exact repository, default-branch, and review-commit binding with live drift
  detection.
- A single-active-run lock for each resolved local repository.
- Strict completion evidence based on the recorded generation sentinel and the
  expected final response container.
- Bounded browser waiting, one controlled reconnect, and terminal handling for
  access warnings or unknown UI states.
- Final-answer provenance containing the conversation, tab, container, byte
  count, and claimed and observed SHA-256 values.
- Separate evidence domains for GitHub CLI authentication and ChatGPT GitHub App
  authorization.
- Fail-closed checks for credential paths, submodules, Git LFS pointers,
  oversized GitHub blobs, and unsupported source states.
- Read-only visibility for legacy run records without upgrading their evidence
  claims.
