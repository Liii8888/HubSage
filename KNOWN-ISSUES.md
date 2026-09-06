# Known limitations

- Credential scanning recognizes only the documented path patterns and selected
  private-key/token markers. It scans all upload-sized blobs but cannot identify
  every kind of secret; a passed scan is not proof that a repository is secret-free.

- ChatGPT UI labels and controls can change. Visible semantic readback remains
  mandatory; the Skill intentionally has no private API fallback.
- Project identity is the resolved local repository path in one state directory.
  Folder moves, multiple worktrees/state directories, and other machines require
  mapping reconciliation; the local run lock does not coordinate those writers.
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
