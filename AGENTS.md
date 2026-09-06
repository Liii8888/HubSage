# Private GitHub Pro Review maintenance

- This repository is the canonical source of `private-github-pro-review`.
- Skill Vault holds reviewed distribution snapshots. Edit this source, then export
  a fixed commit; do not edit through an installed Skill link.
- Preserve the review CLI, explicit invocation, prompt bytes, evidence boundaries,
  and compatibility with existing run records. `RUN_VERSION` is a record schema,
  not the release version.
- Keep machine configuration, private repository identities, run records, and
  recovery material outside tracked source and public release artifacts.
- Record behavior and distribution changes in `CHANGELOG.md`. Keep resolved
  history there and current external limitations in `KNOWN-ISSUES.md`.
- Run the focused tests and verify exported snapshots before handing over a
  candidate commit. Preserve unrelated worktree changes.
- Public push, tags, GitHub Releases, remote branch deletion, and promotion to the
  installed Vault snapshot require the user's review and release authorization.
