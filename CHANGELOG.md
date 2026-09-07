# Changelog

## v2.0.1

- Freeze backup branch/tag targets from the staging snapshot and scan the exact
  upload roots, including WIP and non-commit tags. Missing objects or a changed
  review branch stop before repository creation or transfer.
- Recover collection after a completed conversation tab disconnects by recording
  the same conversation's replacement and fresh completion evidence, retaining
  earlier observations without resetting wait limits.
- Resume an interrupted collection when the existing private answer file matches
  the fully verified extraction; reject different bytes or unsafe saved files.
- Archive branch/tag destinations with Git ref prefix conflicts, preserving
  previous backups even when a user ref occupies the usual archive namespace.
- Reuse HEAD when included staged/worktree changes yield an unchanged final tree,
  avoiding an empty-commit failure and leaving the source index untouched.
- Require source, composer and submission evidence from the same ChatGPT tab.
  A replacement draft can rebind its source before the composer becomes ready.

- Add brief, optional direction for drafting a review request from the user's
  goal. Supplied messages remain unchanged; Pro chooses its investigation and
  response structure.
- Validate the proposed GitHub destination before recording a first project
  mapping. A rejected repository name or failed lookup no longer prevents retrying
  with another name.
- Still reserve the destination before creating or uploading a backup, so a lost
  creation reply or interrupted upload retains the original repository for retry.

- Reorganize the project guide around agent installation, features, usage,
  optional first-use setup, security, recovery, and validation. Add a Chinese
  companion README and pin the installation example to the v2.0.0 release SHA.

## v2.0.0

This version continues the HubSage release line as Private GitHub Pro Review.
Publication dates are recorded by GitHub Releases; this file groups the version's changes.

### Source and distribution

- Establish one independent source repository and reviewed Skill Vault distribution snapshots.
- Rename the existing GitHub repository from HubSage to `private-github-pro-review`,
  retaining repository identity, history, old releases and GitHub URL redirects.
- Add deterministic export and verification from a full Git commit SHA, including source and distribution hashes, provenance, and license.
- Preserve explicit invocation in both Skill frontmatter and Codex metadata.
- Retain public portable state paths and sanitized field notes. Permit one declared, verifiable local default-state adaptation without moving existing review records.
- Keep existing review CLI forms compatible and retain run schema 3. Consolidate resolved issues here and current external limits in `KNOWN-ISSUES.md`.

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

### SOP and recovery follow-up after candidate `f21e702`

- Keep one persistent private backup per local project: create it on first use,
  update it for later reviews, and retain it after collection. Document one-time
  optional All repositories authorization and project-path mapping limits.
- Allow upload before choosing the review mode or preparing its text. A new
  `prepare-review` command freezes the verified repository link and unchanged
  original request separately; the earlier combined command remains compatible.
- Support an explicit committed-only scope for dirty worktrees, alongside approved
  WIP snapshots. Neither Pro mode nor WIP scope is a universal preference.
- Return an existing run and its next step from the upload-only entrypoint.
  Complete pending reviews through the original strict proof, including a
  disconnected tab's verified replacement, without resetting wait limits.
- Keep warning states active until the review is confirmed ended or never sent,
  including interruption after Send but before its saved URL is recorded.
  Neither archive nor supersede can bypass that observation; snapshot-only
  supersede remains available before the composer becomes ready. Add evidence-preserving `end` and a per-run upload execution lock that
  also covers transfer children; interrupted uploads retain their target mapping.
- Shorten the Skill to the main SOP and keep browser details in the protocol.

### Source-link correction after candidate `bec1c70`

- Put the exact verified repository URL alone on the message's first line,
  prefixing it unless that line already exists. Preserve original request bytes,
  including inline links and Markdown, and leave source-chip behavior unchanged.
  Substrings and whitespace token matching cannot establish this prefix: both can
  mistake link text for a target, including multi-line Markdown labels found in
  the follow-up review of `cdaa61b`.
- Recheck raw references before browser use, including the legacy combined CLI.
  Its explicit raw-url message now requires this first line; historical records
  without it stay readable but cannot gain current source checks by rewriting.
- Add regressions for incorrect repository suffixes, embedded query links,
  inline/multi-line Markdown, unchanged request/upload receipts, and preparation
  through composer-ready with the correct first-line URL.
- Document the authorized destinations, credential/session handling, optional
  repository grants, and limits of scanning and browser evidence in a concise
  README security statement after the independent follow-up review.

### Review workflow history

Dates below describe implementation history, not separate software releases. The initial workflow, run hardening, and authentication changes were integrated into the approved Vault line on 2026-08-23 under the corresponding commits below.

| Implemented | Approved Vault commit | Change |
| --- | --- | --- |
| 2026-08-19 | `f2f67ab` | Persistent private mirrors, branch/tag/history preservation, isolated approved worktree snapshots, exact Prompt submission, and review state tracking. |
| 2026-08-20 | `30999d8` | Raw-byte patch handling; exact Pro and mode checks; source binding; controlled composer submission; immutable Prompt evidence; mirror naming; pre-submission correction; owned-tab cleanup; explicit run archival and raw-URL limitations. |
| 2026-08-23 | `6232ef1` | Reuse valid GitHub authentication, retain user-owned credential steps, bound device-code recovery, and identify the active generation sentinel. |
| 2026-08-23 | `2fd50b9` | Require matching completion evidence and final container; recheck source drift; serialize active runs; freeze Prompt bytes; verify answer provenance; separate CLI and App evidence; keep legacy records unverified. |

The public repository adopted this workflow in [`8ef90a9`](https://github.com/Liii8888/private-github-pro-review/commit/8ef90a929f1c6a77f4a0772943a9e3aea8811218) on 2026-08-23. Portable defaults, public-distribution checks, and sanitized examples came with that publication; [`226c244`](https://github.com/Liii8888/private-github-pro-review/commit/226c24488afc80298d5643fd5f0f568470d1d63e) clarified the project guide.

## Legacy HubSage v1.x

Versions v1.0.0–v1.3.0 described the former repository-maintenance Skill. Their [tags and releases](https://github.com/Liii8888/private-github-pro-review/releases) remain historical records. Those version numbers are unrelated to the review run schema.
