# Contributing to HubSage

Thanks for helping make HubSage a sharper maintainer skill.

感谢你参与 HubSage。这个项目最看重两件事：仓库维护体验是否更稳，以及 Agent 执行时是否更不容易误伤。

## Working Model

| Branch | Purpose |
| --- | --- |
| `main` | Latest formal release |
| `develop` | Ongoing small evolutions |
| `release/vX.Y.Z` | Release stabilization |
| `feat/<topic>` | New capability or behavior |
| `fix/<topic>` | Bug fix or instruction correction |
| `docs/<topic>` | Documentation-only work |

Small changes land on `develop` first. Formal GitHub Releases are reserved for behavior-level updates.

## Local Setup

Clone the repository and install the skill into Codex:

```bash
git clone https://github.com/Liii8888/HubSage.git
cd HubSage
mkdir -p ~/.codex/skills/HubSage
cp -R SKILL.md references agents ~/.codex/skills/HubSage/
```

If you are testing with another Agent runtime, keep the repository source unchanged and adapt only the local install path.

## Commit Convention

Use Gitmoji + Conventional Commits:

```text
✨ feat(skill): add release-note routing
🐛 fix(docs): correct Codex install path
📝 docs(readme): refine capability matrix
🔧 chore(release): update changelog ledger
```

Keep one topic per commit. Avoid vague messages such as `update`, `misc`, or `fix stuff`.

## Change Checklist

Before opening a PR or pushing a small evolution:

- [ ] `SKILL.md` frontmatter has `name` and `description`.
- [ ] Every `references/*.md` path mentioned in `SKILL.md` exists.
- [ ] `agents/openai.yaml` still describes the current skill.
- [ ] `CHANGELOG.md#Unreleased` records the change.
- [ ] Public docs do not promise unverified commands, badges, or release status.
- [ ] No unrelated drafts, article exports, or generated files are included.

## Validation

Run lightweight checks before committing:

```bash
git diff --check
```

Also review the staged file list:

```bash
git diff --cached --name-only
```

For release work, verify `gh auth status` before tag or GitHub Release creation.

## Pull Requests

PRs should include:

- A short summary of the behavior or documentation change.
- The validation performed.
- A note about whether the change should stay in `Unreleased` or become part of the next formal version.

HubSage should stay practical, auditable, and calm under pressure. When in doubt, prefer smaller instructions, clearer guardrails, and fewer assumptions.
