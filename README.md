# HubSage

HubSage currently distributes the explicit-only Codex Skill
`private-github-pro-review`. It publishes a local Git repository to one
persistent private GitHub mirror, binds an exact revision in a saved ChatGPT
conversation, runs GPT Pro or GPT Pro with Deep Research, and records evidence
for the final collected answer.

## What It Does

- Preserves local branches, tags, and reachable history in one private mirror.
- Publishes an approved dirty worktree through an isolated WIP branch.
- Freezes the prompt by byte count and SHA-256 before browser submission.
- Separates GitHub CLI authentication from ChatGPT GitHub App authorization.
- Detects default-branch or review-commit drift before source binding.
- Allows only one active review run per resolved local repository.
- Records bounded browser, completion, source, and collection evidence.
- Stops on credentials, unsupported Git objects, ambiguous UI state, or access
  warnings instead of silently weakening the review contract.

The helper script is an evidence ledger and GitHub publisher. Browser actions
are performed by a supported Codex browser integration under the rules in
[`references/browser-protocol.md`](references/browser-protocol.md).

## Requirements

- Python 3.10 or newer
- Git and GitHub CLI (`gh`)
- A GitHub account able to create private repositories
- ChatGPT Pro and an authorized ChatGPT GitHub App connection for source-chip
  binding
- A supported Codex browser integration

## Install

```bash
# From a checkout of this repository:
mkdir -p "$HOME/.agents/skills/private-github-pro-review"
cp -R SKILL.md KNOWN-ISSUES.md agents references scripts \
  "$HOME/.agents/skills/private-github-pro-review/"
```

The installed Skill ID remains `private-github-pro-review`.

## Use

Invoke the Skill explicitly and provide the repository, mode, binding, and
prompt file. The deterministic publisher can also be run directly:

```bash
python3 scripts/review_repo.py publish \
  --repo /absolute/path/to/repository \
  --mode review \
  --binding source-chip \
  --prompt-file /absolute/path/to/prompt.txt
```

Use `--mode pro` for GPT Pro without Deep Research. The prompt is always sent
unchanged.

Run state defaults to `$XDG_STATE_HOME/private-github-pro-review`, or
`~/.local/state/private-github-pro-review` when `XDG_STATE_HOME` is unset.
Override it with `PRIVATE_GITHUB_PRO_REVIEW_HOME` when needed.

## Safety Boundaries

- Upload and ChatGPT access require explicit user permission.
- Mirrors must remain private and carry the Skill's management marker.
- Existing remote-only history is retained; force-push and history rewriting
  are forbidden.
- High-confidence credential paths require an explicit per-path exception.
- Browser waiting is bounded and does not repeatedly scrape the conversation.
- Browser evidence records what was observed; it is not cryptographic proof of
  ChatGPT's internal retrieval.

See [`SKILL.md`](SKILL.md) for the operating contract and
[`KNOWN-ISSUES.md`](KNOWN-ISSUES.md) for current external limitations.

## License

MIT
