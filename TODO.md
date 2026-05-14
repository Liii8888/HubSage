# HubSage Roadmap

## Current Rhythm

- [x] Treat `/Users/li/Agent/Projects/HubSage` as the GitHub source repository.
- [x] Treat `/Users/li/.codex/skills/HubSage` as the local installed runtime copy.
- [x] Record every small evolution in `CHANGELOG.md` under `Unreleased`.
- [x] Push each evolution to `origin/develop`.
- [x] Reserve GitHub Releases for behavior-level updates.

## v1.3.0 Released

- [x] Split detailed SOPs into progressive `references/` files.
- [x] Add public-action guardrails for dirty worktrees, push, tag, and release actions.
- [x] Add Codex UI metadata in `agents/openai.yaml`.
- [x] Add `CHANGELOG.md` as the small-update ledger.
- [x] Cut `release/v1.3.0` from `develop`.
- [x] Promote `CHANGELOG.md#Unreleased` into a dated `v1.3.0` section.
- [x] Merge the release branch to `main`, create an annotated tag, and publish GitHub Release notes.

## Future Improvements

- [ ] Add a deterministic validation script for frontmatter, reference links, and `agents/openai.yaml`.
- [ ] Add compact example prompts that show safe HubSage usage for docs, bootstrap, community templates, and releases.
- [ ] Add a minimal CI workflow that validates Markdown and skill metadata without requiring secrets.

## Anti-Goals

- [ ] Do not add hidden project config such as `.hubsage.yml`; HubSage should ask for project-specific preferences each time.
- [ ] Do not force subagents for normal work; use them only when the user explicitly requests delegation.
- [ ] Do not publish a GitHub Release for every small update.
