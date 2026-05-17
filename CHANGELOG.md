# Changelog

All notable changes to HubSage are recorded here.

This project uses a two-speed release rhythm:

- Small evolutions are recorded under `Unreleased`, committed, and pushed to `origin/develop`.
- Behavior-level updates are promoted into a versioned release, tagged, and published on GitHub.

## Unreleased

### Added

- Added `assets/hubsage-cover.svg` as a custom visual identity asset for the repository front page.

### Changed

- Reworked `README.md` into a stronger terminal-editorial front page with a custom cover image, sharper positioning, and a more distinctive maintainer-tool voice.

## v1.3.0 - 2026-05-17

### Added

- Added progressive `references/` files for documentation, bootstrap, community, and release workflows.
- Added `agents/openai.yaml` so Codex can present HubSage with clearer UI metadata.
- Added this changelog as the source of truth for small-update notes before the next release.

### Changed

- Refined `README.md` into an editorial maintainer-style repository front door with a stronger first screen, capability matrix, repository map, and tighter release-rhythm explanation.
- Reworked `CONTRIBUTING.md` around Codex installation, branch rhythm, validation checks, and staged-file hygiene.
- Reworked `SKILL.md` into a concise routing layer with separate reference files for detailed procedures.
- Updated the HubSage release cadence: every evolution is pushed to `develop`, while GitHub Releases are reserved for behavior-level updates.

### Fixed

- Replaced the stale Gemini skill install path in contributor setup with the current Codex path.
- Resolved the previous commit-policy mismatch by explicitly allowing `🎉 init:`.
- Removed stale assumptions that forced subagent use or automatic release actions in cases where user confirmation is required.

### Security/Guardrails

- Added stronger safeguards for dirty worktrees, public GitHub actions, release notes accuracy, and `pull_request_target` usage.
- Added an explicit rule that tag, release, repo creation, and other public actions require confirmation.
