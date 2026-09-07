# Private GitHub Pro Review

[简体中文](README.zh-CN.md) · [Installation](#install-in-codex) · [Security and data](#security-and-data) · [Releases](https://github.com/Liii8888/private-github-pro-review/releases) · [MIT](LICENSE)

Let Codex upload a local project to **your own private GitHub repository**, open
**ChatGPT on the web**, select **Pro**, submit the repository link and your review
request, then save the answer. Each project keeps one backup for later reviews.

## Let your agent install it

> Install https://github.com/Liii8888/private-github-pro-review as a Codex Skill.
> Read the README and security statement, then install the reviewed v2.0.3 commit
> below. Preserve any existing installation and review records. Report any setup
> still needed; installation should not upload a project or start a review.

## Install in Codex

You need Python 3.10+, Git, GitHub CLI (`gh`), and local Codex with shell access
and a supported browser connection. macOS is the validated platform; the script
uses POSIX locks. Web reviews need a ChatGPT account with Pro and access to the
private repository through its GitHub connection.

After reviewing the source, run this in a directory without an existing
`private-github-pro-review` checkout. This installs **v2.0.3**:

```bash
(
  PGPR_REVIEWED_SHA=265e5e5c8026bf932325621254ff19885d286299 &&
  git clone --no-checkout https://github.com/Liii8888/private-github-pro-review.git private-github-pro-review &&
  cd private-github-pro-review &&
  git checkout --detach "$PGPR_REVIEWED_SHA" &&
  python3 scripts/export_skill.py export \
    --ref "$PGPR_REVIEWED_SHA" \
    --output "$HOME/.agents/skills/private-github-pro-review"
)
```

The full SHA pins both the code executed and the installed contents. Commands
stop on failure and preserve an existing destination. For one project, use its
`.agents/skills/private-github-pro-review` directory instead. Start a new Codex
task after installation; invoke the Skill explicitly.

The installed Skill contains its instructions, browser protocol, runtime script,
Codex metadata, license, and a provenance/checksum manifest. Source guides and
maintenance tests are not needed at runtime. Export or verify a snapshot using
`scripts/export_skill.py` from its recorded source commit.

## Use it

> Use $private-github-pro-review to review this project in ChatGPT Pro. Include
> my uncommitted changes and focus on correctness bugs.

> Use $private-github-pro-review with Pro + Deep Research to review the committed
> version. Focus on architecture.

> Continue the interrupted private GitHub Pro review and collect its answer.

The workflow is **upload → select Pro → paste link and request → wait → save**.
Choose Deep Research and uncommitted changes for each task. Your request is
preserved; later reviews update the same private backup. See [SKILL.md](SKILL.md)
for the workflow and `python3 scripts/review_repo.py --help` for direct commands.

### First-use setup tips

Use these for initial setup or access problems, not as a repeated checklist:

- **GitHub:** connect GitHub in ChatGPT and grant access to the backup. This is
  separate from local `gh` sign-in. See [connection setup](https://learn.chatgpt.com/docs/plugins).
- **Repository access:** for repeated use, **All repositories** avoids granting
  each new backup individually, if you accept that account/organization-wide
  access. **Only select repositories** also works. Neither makes a private
  repository public. See [GitHub App settings](https://docs.github.com/en/apps/using-github-apps/reviewing-and-modifying-installed-github-apps).
- **Pro:** confirm it is available and selected before sending. Follow the actual
  page labels; `high` or `xhigh` reasoning effort is not Pro.
- **Browser:** connect a supported tool to the signed-in ChatGPT session. Follow
  the tool's setup for its browser plugin/extension; no particular plugin name is
  required. See [browser setup](https://learn.chatgpt.com/docs/chrome-extension#set-up-the-chrome-extension).

## Security and data

Runs require an explicit request and authorization to upload and review.
**There is no maintainer-operated data receiver or telemetry.** This public
repository does not receive your projects.

| Data | Destination |
| --- | --- |
| Branches, tags, reachable history, and chosen uncommitted changes | Your verified private GitHub backup |
| Link, review request, and code accessed through the GitHub connection | Your signed-in ChatGPT session |
| Project mapping, request copies, evidence, and final answer | Your local state directory |

The Skill reuses Git/GitHub CLI credentials and the supported browser session.
It does not request raw tokens, copy cookies/profiles, or expand repository grants.
Destination checks, sensitive-path/credential scanning, and private answer files
remain automatic. Scanning cannot identify every secret; reachable history may
contain deleted files, and commit/tag messages are not fully scanned. Choose
projects and history suitable for GitHub and ChatGPT.

Browser evidence cannot attest which code the model actually read. Verify review
advice against the source. UI changes or indexing delays can require stopping and
resuming later; waiting and recovery rules are in the [browser protocol](references/browser-protocol.md).

## Local records and recovery

State lives under `$XDG_STATE_HOME/private-github-pro-review`, or
`~/.local/state/private-github-pro-review` when XDG is unset. Override it with
`PRIVATE_GITHUB_PRO_REVIEW_HOME` or, with higher priority, `--state-root`.
Records stay outside source and release packages.

Resume the saved run and conversation after interruption. To abandon a review,
confirm it finished or was cancelled, then record `end`; closing a tab or timing
out is insufficient. Ending or archiving keeps the backup and evidence.
Reconcile the mapping before moving a project or using another worktree, state
directory, or machine; locks do not coordinate separate writers. Older records
remain readable and retain their original verification status.

[Version history](CHANGELOG.md) · Formerly HubSage; old links, tags, and Releases remain available.
