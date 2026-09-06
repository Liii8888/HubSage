# Changelog

## v2.0.0

This version continues the HubSage release line as Private GitHub Pro Review.
Publication dates are recorded by GitHub Releases; this file groups the version's changes.

### Source and distribution

- Establish one independent source repository and reviewed Skill Vault distribution snapshots.
- Add deterministic export and verification from a full Git commit SHA, including source and distribution hashes, provenance, and license.
- Preserve explicit invocation in both Skill frontmatter and Codex metadata.
- Retain public portable state paths and sanitized field notes. Permit one declared, verifiable local default-state adaptation without moving existing review records.
- Keep the review CLI and run schema 3 unchanged. Consolidate resolved issues here and current external limits in `KNOWN-ISSUES.md`.

### Security fixes after candidate `3b70e59`

- Pin every GitHub API request to `github.com` and scope other GitHub CLI host
  selection to child processes. Verify owner, repository name, canonical URL,
  private visibility, and management marker before upload and during readback.
- Check every real path in reachable branch/tag history using NUL-delimited
  trees, retaining all names for shared blobs and keeping overrides per path.
- Scan every upload-sized blob sequentially in full, removing the 2 MB gap.
  Read failures stop publication; token recognition remains a limited safeguard.
- Require owned `0700` answer extraction directories and `0600` regular files;
  create them before writing answer bytes and reject unsafe inputs on collection.
- Pin both the installation script and exported payload to the same reviewed
  full SHA before executing any repository Python code. Stop the command chain
  on clone, directory-change, or checkout failure so a stale checkout cannot
  supply the installation script.

### Data-boundary follow-up after candidate `0d2b429`

- Bind Git reads and uploads to a checked staging remote. Resolve all effective
  fetch and push URLs before transfer, rejecting Git URL rewrites to a different
  host or repository and multiple destinations. Preserve standard HTTPS/SSH
  rewrites for the same verified GitHub repository without changing user config.
- Document the data sent to GitHub and ChatGPT, local-only records, credential
  handling, and the distinction between the Skill's public distribution repository
  and the user's private backup destination.

### Review workflow history

Dates below describe implementation history, not separate software releases. The initial workflow, run hardening, and authentication changes were integrated into the approved Vault line on 2026-08-23 under the corresponding commits below.

| Implemented | Approved Vault commit | Change |
| --- | --- | --- |
| 2026-08-19 | `f2f67ab` | Persistent private mirrors, branch/tag/history preservation, isolated approved worktree snapshots, exact Prompt submission, and review state tracking. |
| 2026-08-20 | `30999d8` | Raw-byte patch handling; exact Pro and mode checks; source binding; controlled composer submission; immutable Prompt evidence; mirror naming; pre-submission correction; owned-tab cleanup; explicit run archival and raw-URL limitations. |
| 2026-08-23 | `6232ef1` | Reuse valid GitHub authentication, retain user-owned credential steps, bound device-code recovery, and identify the active generation sentinel. |
| 2026-08-23 | `2fd50b9` | Require matching completion evidence and final container; recheck source drift; serialize active runs; freeze Prompt bytes; verify answer provenance; separate CLI and App evidence; keep legacy records unverified. |

The public repository adopted this workflow in [`8ef90a9`](https://github.com/Liii8888/HubSage/commit/8ef90a929f1c6a77f4a0772943a9e3aea8811218) on 2026-08-23. Portable defaults, public-distribution checks, and sanitized examples came with that publication; [`226c244`](https://github.com/Liii8888/HubSage/commit/226c24488afc80298d5643fd5f0f568470d1d63e) clarified the project guide.

## Legacy HubSage v1.x

Versions v1.0.0–v1.3.0 described the former repository-maintenance Skill. Their [tags and releases](https://github.com/Liii8888/HubSage/releases) remain historical records. Those version numbers are unrelated to the review run schema.
