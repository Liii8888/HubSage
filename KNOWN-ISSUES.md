# Known Issues And Field Notes

The v2 state machine was shaped by a private-repository review in August 2026.
V3 closes evidence gaps found during later live use.

## Resolved In V2

- **Dirty-worktree patch corruption.** WIP patches stay as raw bytes through
  `git diff --binary` and `git apply --binary`; trailing blank context is
  covered by regression.
- **`xhigh` mistaken for Pro.** `source-bound` requires the visible label to
  equal `Pro`; slider position is documented only as a UI hint.
- **Mode drift.** The run's `review` or `pro` mode is checked against the
  separately observed Deep Research state.
- **Unsafe sequential typing and Enter submission.** `composer-ready` requires
  the exact prompt hash and one-operation fill; `submitted` accepts only the
  send button and a durable conversation URL.
- **Weak source evidence.** Binding kind, repository, default branch, commit,
  App grant, and active run-owned tab must match the published run.
- **Generic mirror names.** Existing project mappings remain authoritative;
  otherwise generic local/origin names fail closed and require `--mirror`.
- **Republishing after a prompt or mode correction.** `supersede` reuses a
  verified private snapshot without Git or GitHub access and rejects no-op
  replacements or post-submission reuse.
- **Unmanaged abandoned tabs.** A per-run tab ledger rejects unrelated tabs and
  keeps saved conversations open until terminal.
- **Stale run directories looking active.** `list` shows active runs by default;
  `archive` explicitly marks a terminal run without deleting evidence.
- **Authorization confused with indexing.** `source-index-pending` records a
  verified App grant separately from a source chip that is not yet selectable.
- **Raw URL ambiguity.** It is an explicit binding whose exact URL must already
  exist in the prompt; it never claims source-chip indexing or adds a generic
  GitHub plugin pill.

## Resolved In V3

- **Premature completion after a progress response.** `wait-start` freezes the
  observed generation sentinel. `wait-complete` requires the same sentinel to be
  absent and the mode-specific final container to be present on the same active
  saved-conversation tab.
- **Published branch drift between upload and binding.** Source binding now
  rechecks repository privacy, default branch, and the live branch SHA against
  the frozen source and publication manifests.
- **Overlapping runs for one source.** A private filesystem transaction lock and
  active-state scan allow only one active run per resolved repository path.
- **Mutable prompt evidence.** The run stores prompt byte count and SHA-256 in
  all publication manifests and rechecks frozen `prompt.txt` at every v3
  lifecycle transition.
- **Raw URL overclaim.** `source-chip` and `raw-url` have distinct guarantee
  labels. Raw URL remains reference-only even when the App grant is separately
  verified.
- **Answer collection without provenance.** `collect` now requires the recorded
  final-container kind, conversation URL, active tab, a private temporary
  non-symlink source file, and matching claimed/observed SHA-256.
- **GitHub authentication boundary confusion.** GitHub CLI evidence and ChatGPT
  GitHub App evidence are stored separately. Behavior tests prove the CLI
  preflight never starts login automatically.

## Remaining External Limitations

- ChatGPT UI labels and controls can change. Visible semantic readback remains
  mandatory; the Skill intentionally has no private API fallback.
- GitHub App indexing latency is controlled by ChatGPT/GitHub. The Skill records
  pending state but cannot accelerate it and must not poll.
- Browser evidence is operator-observed and recorded, not cryptographically
  attested by ChatGPT. A mismatch must stop before submission.
- A source chip plus live commit readback does not reveal or attest ChatGPT's
  internal retrieval. A raw URL proves even less: only that the exact reference
  was present in the frozen prompt.
- Final-response extraction depends on the visible ChatGPT response/report
  container. Unknown UI states require one screenshot and a stop, not broad DOM
  scraping.
- The Chrome extension backend observed on 2026-08-23 capped
  `PlaywrightLocator.waitFor` at its short selector deadline even when
  `timeoutMs` was larger, while the read-only evaluation scope exposed neither
  `MutationObserver` nor timers. The browser protocol therefore permits only a
  five-minute, sentinel-only compatibility check with a hard mode deadline; it
  still forbids response scraping or high-frequency polling.
- ChatGPT Pro can emit a short assistant progress message while repository tools
  continue running. Absence of a guessed localized stop label is not completion;
  identify the visible generation sentinel first and extract text only after it
  disappears.
- Existing v1/v2 runs lack the complete v3 evidence. They remain readable and
  are always displayed as `legacy_unverified`, but cannot gain v3 completion or
  collection claims and are never auto-migrated.
