# Private GitHub Pro Review

[简体中文](https://github.com/Liii8888/private-github-pro-review/blob/main/README.zh-CN.md) · [Installation](#install-in-codex) · [Security and data](#security-and-data) · [Workflow](SKILL.md) · [Releases](https://github.com/Liii8888/private-github-pro-review/releases) · [MIT License](LICENSE)

Let Codex back up a local Git project to **your own private GitHub repository**,
open **ChatGPT on the web**, select **Pro**, submit the repository link with your
review request, and save the answer.

This is a community Skill for **local Codex**. Each project keeps one private
backup across reviews: create it on first use, update it after changes, and keep
it for the next review. The workflow uses your GitHub account and ChatGPT session.

## Let your agent install it

Give Codex this request:

> Install https://github.com/Liii8888/private-github-pro-review as a Codex Skill.
> Read its README and security statement, then install the reviewed v2.0.1 commit
> using the instructions below. Preserve any existing installation and review
> records. Tell me where the Skill is installed and what GitHub or browser setup
> remains. Do not upload a project or start a review as part of installation.

The bundle includes the [Skill instructions](SKILL.md), Python helpers, browser
protocol, and tests. Install the complete snapshot so future tasks can use
`$private-github-pro-review` without remembering script paths.

## What it does

- Creates a private backup for a project and reuses it for later reviews.
- Backs up local branches, tags, reachable history, and your chosen uncommitted
  changes while leaving the source checkout unchanged.
- Preserves your review request exactly and adds the verified repository link
  after upload succeeds.
- Supports Pro and Pro with Deep Research, selected for each request.
- Saves the reviewed commit, conversation URL, progress, and final answer locally.
- Resumes interrupted work and prevents a new upload from changing a version
  that is still being reviewed.

## Install in Codex

Requirements: Python 3.10+, Git, GitHub CLI (`gh`), and a Codex environment with
shell access and a supported browser connection. macOS is the validated platform;
the scripts use POSIX file locks. Web reviews also need a ChatGPT account with
Pro available and a GitHub connection that can access the private backup.

After reviewing the source, run this from a directory without an existing
`private-github-pro-review` checkout. It installs **v2.0.1**, pinned to its full
release commit:

```bash
(
  PGPR_REVIEWED_SHA=fb54c1664fbf375b86358599b18a71a06a3c3b56 &&
  git clone --no-checkout https://github.com/Liii8888/private-github-pro-review.git private-github-pro-review &&
  cd private-github-pro-review &&
  git checkout --detach "$PGPR_REVIEWED_SHA" &&
  python3 scripts/export_skill.py export \
    --ref "$PGPR_REVIEWED_SHA" \
    --output "$HOME/.agents/skills/private-github-pro-review"
)
```

The installer checks out the reviewed commit **before running its code** and
exports that same commit. Each command stops on failure; an existing destination
is preserved. For a project-only installation, use that project's
`.agents/skills/private-github-pro-review` as the output directory. If a Skill
Vault manages the destination, update its reviewed snapshot through that Vault.
See [Codex skill locations](https://developers.openai.com/codex/skills#where-to-save-skills).

Start a new Codex task and invoke the Skill explicitly. If it is not visible,
restart Codex and check the installed `SKILL.md` path.

## Use it

For example:

> Use $private-github-pro-review to back up this project and review it in ChatGPT
> Pro. Include my uncommitted changes and look for correctness bugs and missing tests.

> Use $private-github-pro-review to review the committed version with Pro and
> Deep Research. Focus on the architecture and remaining security issues.

> Continue the interrupted private GitHub Pro review and collect its answer.

The sequence is **upload → select Pro → paste the link and review request →
wait → save the answer**. Later reviews update the same private backup.

Choose the mode and review scope for the task; neither Deep Research nor
uncommitted changes is imposed as a universal default. For direct CLI use,
`pro` means Pro, `review` means Pro with Deep Research, and the scope flags are
`--include-working-tree` and `--committed-only`. The upload and message-preparation
steps are documented in [SKILL.md](SKILL.md); use `scripts/review_repo.py --help`
for commands. Browser submission and collection follow the
[browser protocol](references/browser-protocol.md).

<a id="首次使用的小提示"></a>

### First-use setup tips

These are optional setup and troubleshooting notes, not a checklist to repeat
before every run:

- **GitHub connection:** connect GitHub in ChatGPT and grant it access to the
  backup. Local `gh` sign-in and ChatGPT's GitHub authorization are separate.
  See [OpenAI's plugin guide](https://learn.chatgpt.com/docs/plugins).
- **Repository access:** for repeated use, we recommend **All repositories** if
  you accept access to all repositories in that App installation's account or
  organization. New backups then do not need individual grants. **Only select
  repositories** also works; add each new backup to the selection. This does not
  make repositories public. See [GitHub App access settings](https://docs.github.com/en/apps/using-github-apps/reviewing-and-modifying-installed-github-apps).
- **Pro selection:** check that Pro is available in the web model picker and
  selected before sending. Use the actual labels shown by your account;
  `high` or `xhigh` reasoning effort is not a substitute for Pro.
- **Browser connection:** use a supported tool connected to your signed-in
  ChatGPT session. For Chrome, follow **Settings → Computer Use** in the desktop
  app to install the required plugin and extension in the correct browser
  profile. The Skill does not require a plugin with a particular name. See
  [browser setup](https://learn.chatgpt.com/docs/chrome-extension#set-up-the-chrome-extension).

## Security and data

The Skill runs only when explicitly requested with authorization to upload and
review the project. It has **no maintainer-operated collection endpoint or
telemetry**. This public source repository does not receive your project data.

| Data | Destination |
| --- | --- |
| Local branches, tags, reachable history, and chosen uncommitted changes | Your verified private GitHub backup |
| Repository link, review request, and code accessed through the authorized GitHub connection | Your signed-in ChatGPT session |
| Project mapping, request copies, source evidence, and collected answer | Your local state directory |

Authentication uses existing Git/GitHub CLI credentials and the supported browser
session. The Skill does not ask for raw tokens or copy browser cookies/profiles.
Repository grants stay under your control; it does not expand them automatically.

Before upload, it checks the repository identity, private visibility, management
marker, and actual Git destination, then scans known sensitive paths and
credential patterns. Answer extraction uses an owned private directory and file.
These checks have limits: reachable history can contain deleted files, scanning
cannot detect every secret or business-sensitive value, and commit/tag messages
are not fully scanned. Choose projects and history suitable for GitHub and ChatGPT.

A pasted URL or recorded source selection does not prove what the model actually
read. Treat the answer as advice to verify against the code. Further browser,
source-evidence, and recovery limits are in [KNOWN-ISSUES.md](KNOWN-ISSUES.md).

## Local state and recovery

State defaults to `$XDG_STATE_HOME/private-github-pro-review`, or
`~/.local/state/private-github-pro-review` when XDG is unset.
`PRIVATE_GITHUB_PRO_REVIEW_HOME` overrides that default; an explicit
`--state-root` takes precedence. A locally adapted Vault snapshot may retain its
own default while still honoring both explicit overrides. Runtime data is kept
outside the source and public packages.

On interruption, resume the saved run and conversation. If abandoning a review,
confirm it has finished or been cancelled, then record `end`; a timeout or closed
tab alone does not release the active version. Ending or archiving a run does
not delete the private backup or its local evidence.

Project identity follows the resolved local repository path in one state
directory. Reconcile mappings before moving a project, changing accounts, or
using another worktree or machine; locks do not coordinate separate machines.

## Development and validation

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'
```

Tests use temporary repositories, fake data, and mocked services. They cover
upload safety, snapshots, source binding, recovery, answer collection, and pinned
installation without a real private upload or ChatGPT review.

`scripts/export_skill.py` exports and verifies a full commit SHA, recording
provenance and checksums in `DISTRIBUTION.json` and `UPSTREAM.md`. Source development
does not move an installed snapshot. `RUN_VERSION = 3` is the record format,
separate from the release number; old records remain readable and unverified.

See [CHANGELOG.md](CHANGELOG.md) for version history. This repository was renamed
in place from HubSage; old repository links redirect here and the v1.x tags,
Releases, and history remain available. The project is [MIT-licensed](LICENSE).
