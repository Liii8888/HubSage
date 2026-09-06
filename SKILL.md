---
name: private-github-pro-review
disable-model-invocation: true
description: "Use when the user explicitly asks to back up a local Git repository with its branches, tags, and history to one persistent private GitHub repository, then send an unchanged prompt to ChatGPT Pro or ChatGPT Pro with Deep Research, wait without repeated page scraping, and save the final answer."
---

# Private GitHub Pro Review

Back up one local Git repository to one long-lived private GitHub repository,
bind that exact source in a fresh saved ChatGPT conversation, submit the user's
unchanged prompt once, and collect the final answer once.

## Hard Boundaries

- Run only after explicit permission to upload the repository and use ChatGPT.
- Use `review` for Pro with Deep Research and `pro` for Pro without it. Do not
  split one requested review into multiple independent conversations.
- Send the prompt byte-for-byte. Do not prepend, append, summarize, or improve it.
- Keep one persistent private GitHub backup per local repository. Never create a
  new remote per review, delete remote-only refs, force-push, or rewrite history.
- Keep only one active review run per resolved local repository path. The
  publisher serializes run creation and rejects a second active run; finish,
  block/archive, or explicitly supersede the first run instead.
- A disposable clone is staging only. Do not change the source repository's
  branch, index, worktree, remotes, or commits.
- Do not upload credentials silently. User-approved private content is allowed;
  high-confidence credential paths require an explicit per-path override.
- Use the supported connected browser. Do not use private ChatGPT APIs, copy
  cookies or profiles, or automate ChatGPT through raw Playwright.
- Do not poll page content. Follow
  [references/browser-protocol.md](references/browser-protocol.md) exactly; only
  its bounded generation-sentinel fallback is allowed when an event wait is
  demonstrably unavailable.

## Publish The Persistent Backup

Resolve this Skill directory as `<skill-dir>`. Required inputs are the repository
root, `review` or `pro`, a UTF-8 prompt file, and a binding:

- `source-chip` (default): bind the exact private repository in ChatGPT.
- `raw-url`: use only when explicitly chosen. The exact
  `https://github.com/owner/repository` URL must already be present unchanged in
  the prompt; do not add a generic GitHub plugin pill or claim connector indexing.

### GitHub CLI authentication preflight

Before invoking the publisher, run `gh auth status -h github.com` and verify the
active account is the intended repository owner. If it succeeds, skip the entire
browser/device authorization flow. Do not refresh a valid login merely because a
new review is starting.

If the login is missing or invalid, proceed only with the user's explicit
permission to authenticate GitHub for this Skill. Run:

```bash
gh auth login -h github.com --web --git-protocol https
```

Within this Skill only, Codex may enter the one-time device code in the supported
browser and click the GitHub CLI authorization button when the user has explicitly
authorized that automation. Never read or enter the user's password, passkey,
authenticator code, recovery code, or GitHub Mobile confirmation. Hand those
controls to the user and wait.

After a user completes GitHub's sudo-mode confirmation, the original device code
may already have expired. If so, generate one fresh device code and complete it
immediately; never reuse an expired code or loop through repeated login attempts.
If that single fresh retry fails, stop and report the authentication blocker.

Finally, rerun `gh auth status -h github.com` and verify the intended active
account before publishing. Do not print, copy, inspect, or persist the OAuth token.
This conditional authorization is part of this Skill's GitHub publishing SOP and
does not grant permission to automate authentication for unrelated workflows.

GitHub CLI authentication authorizes only repository creation, upload, and
readback by this local workflow. It does not prove that ChatGPT's GitHub App is
authorized, and a ChatGPT GitHub App grant does not prove that `gh` is logged in.
The v3 ledger stores these as separate evidence domains. Behavior tests prove
that the CLI preflight never invokes `gh auth login` by itself; login remains a
separate, explicitly user-authorized recovery action.

Run:

```bash
python3 <skill-dir>/scripts/review_repo.py publish \
  --repo /absolute/project/path \
  --mode review \
  --binding source-chip \
  --prompt-file /absolute/prompt.txt
```

For approved WIP, add `--include-working-tree`. For a deliberate credential-path
exception, repeat `--allow-sensitive-path relative/path`.

The publisher reuses the source's existing project mapping. Without one, an
explicit `--mirror` wins; otherwise it uses a meaningful GitHub origin basename
or local repository dirname. Generic names such as `Li`, `repo`, or `project`
fail closed and require `--mirror owner/repository`.

It then:

- verifies the destination is private and has this Skill's project marker;
- uploads every local branch, tag, and reachable history without deleting
  remote-only history;
- archives a non-fast-forward local ref under a unique remote archival ref;
- creates `review/wip/<run-id>` only for explicitly approved dirty content;
- makes the reviewed branch the GitHub default branch;
- freezes `prompt.txt` by byte length and SHA-256 and rechecks it at every v3
  browser or collection transition;
- serializes run creation and rejects a second active run for the same resolved
  source path;
- rejects submodules, Git LFS pointer-only content, oversized GitHub blobs, and
  unapproved credential paths; and
- records the exact private mirror, default branch, commit, prompt hash, binding,
  source manifest, and upload result in a private v3 run directory.

Do not enter the browser phase unless output status is `published` and
`mirror_private` is `true`.

## Bind And Submit In ChatGPT

Open one fresh saved ChatGPT conversation, never Temporary Chat. Register and
activate only the tabs created for this run:

```bash
python3 <skill-dir>/scripts/review_repo.py tab \
  --run-dir /absolute/run --action register --tab-id <browser-tab-id> \
  --kind chatgpt-draft --url https://chatgpt.com/
python3 <skill-dir>/scripts/review_repo.py tab \
  --run-dir /absolute/run --action activate --tab-id <browser-tab-id>
```

Before binding, verify the ChatGPT GitHub App grant separately from both GitHub
CLI authentication and source indexing. If a `source-chip` mirror is authorized
but not yet selectable, record
`source-index-pending` once and stop without polling:

```bash
python3 <skill-dir>/scripts/review_repo.py event \
  --run-dir /absolute/run --event source-index-pending \
  --app-grant verified --binding source-chip \
  --repository owner/repository --default-branch branch --commit SHA \
  --tab-id <browser-tab-id>
```

When the exact source is available, record structured source evidence. The
visible capability must literally be `Pro`; a reasoning-strength label such as
`xhigh` or `极高` is not sufficient. Deep Research must be active only for
`review`. The command re-reads the private GitHub repository's current default
branch and branch SHA immediately before accepting browser evidence. Any drift
from the published review commit fails closed:

```bash
python3 <skill-dir>/scripts/review_repo.py event \
  --run-dir /absolute/run --event source-bound \
  --capability-label Pro --deep-research active --app-grant verified \
  --binding source-chip --repository owner/repository \
  --default-branch branch --commit SHA --tab-id <browser-tab-id>
```

Prepare the full prompt outside the composer and fill it in one operation. Read
the composer once, compare it to the frozen `prompt.txt`, calculate the exact
SHA-256, and record readiness. Editing or replacing `prompt.txt` after run
creation makes every v3 transition fail closed:

```bash
python3 <skill-dir>/scripts/review_repo.py event \
  --run-dir /absolute/run --event composer-ready \
  --prompt-sha256 SHA256 --fill-method single-operation \
  --tab-id <browser-tab-id>
```

Click the visible send button once. Never press Enter to submit. After the URL
becomes a durable saved conversation URL, record:

```bash
python3 <skill-dir>/scripts/review_repo.py event \
  --run-dir /absolute/run --event submitted \
  --conversation-url https://chatgpt.com/c/CONVERSATION \
  --submission-method send-button --tab-id <browser-tab-id>
```

The v3 state machine rejects model/mode/source/branch/SHA/prompt/tab mismatches,
remote review-commit drift, sequential typing, Enter submission, duplicate
submission, unrelated tabs, and unsupported completion claims.

Binding assurance is explicit:

- `github-app-source-chip-exact-commit-v1` means the App grant, visible source
  chip, exact repository/default branch/commit, and live GitHub readback all
  matched. It still does not cryptographically attest what ChatGPT read.
- `raw-url-reference-only-v1` means only that the unchanged prompt contains the
  exact private repository URL. Even with a separately verified App grant, it
  must never be described as source-chip binding or proof that repository
  contents were retrieved.

## Correct A Pre-Submission Run

If mode, binding, or prompt is wrong after publication, close every abandoned
run-owned draft or temporary GitHub tab in the browser and record each close.
Then reuse the already verified snapshot without touching Git or GitHub:

```bash
python3 <skill-dir>/scripts/review_repo.py supersede \
  --run-dir /absolute/old-run --mode review --binding source-chip \
  --prompt-file /absolute/corrected-prompt.txt --reason "correct review mode"
```

An identical replacement is rejected. A submitted conversation cannot be
superseded this way.

## Wait, Collect, And Resume

Identify the current generation sentinel from targeted semantic button metadata,
then record `wait-start` with that exact opaque identifier:

```bash
python3 <skill-dir>/scripts/review_repo.py event \
  --run-dir /absolute/run --event wait-start \
  --generation-sentinel <observed-sentinel-id> \
  --tab-id <browser-tab-id>
```

Use one event-driven wait. Do not read response text or status while it is
active. Completion is accepted only after the recorded sentinel is absent and
the mode-specific final container is present. `review` requires
`deep-research-report`; `pro` requires `assistant-turn`:

```bash
python3 <skill-dir>/scripts/review_repo.py event \
  --run-dir /absolute/run --event wait-complete \
  --generation-sentinel <same-observed-sentinel-id> \
  --completion-proof generation-sentinel-absent-and-final-container-present \
  --final-container deep-research-report --tab-id <browser-tab-id>
```

Before writing any answer bytes, create a current-user-owned `0700` temporary
directory under `/private/tmp` or the process temporary directory, and an empty
`0600` regular file inside it, using the safe creation example in the
[browser protocol](references/browser-protocol.md#waiting-and-collection).
Extract only that final container once into the pre-created file, preserving its
permissions. Do not use symlinks or a shared directory, and do not repair an
already exposed file with chmod; re-extract into a new private file instead.
Calculate its SHA-256 before collection and bind it to the recorded conversation,
tab, and container:

```bash
python3 <skill-dir>/scripts/review_repo.py collect \
  --run-dir /absolute/run --answer-file /private/tmp/pgpr-answer-RANDOM/answer.md \
  --answer-sha256 SHA256 --source-kind deep-research-report \
  --source-conversation-url https://chatgpt.com/c/CONVERSATION \
  --source-tab-id <browser-tab-id>
```

Collection records the asserted browser source path, conversation, tab,
container kind, byte count, claimed hash, and observed hash. This proves which
local bytes were archived; it remains operator-observed browser provenance, not
a cryptographic attestation from ChatGPT.

For a genuine disconnect, record `pending`, then `reconnect`, reopen only the
saved conversation URL, register and activate the replacement tab, and use the
one remaining long wait. If the original tab actually closed, record its close
with `--reason disconnected`. A second reconnect,
third wait, warning retry, duplicate collection, or conversation search is
forbidden. A frequency warning is terminal: record `warning`, optionally save
one diagnostic screenshot, and stop.

## Inspect And Archive

Read state without external access:

```bash
python3 <skill-dir>/scripts/review_repo.py show --run-dir /absolute/run
python3 <skill-dir>/scripts/review_repo.py list
python3 <skill-dir>/scripts/review_repo.py list --all
```

Archive only an explicitly selected terminal run. A dry-run `prepared` record is
also archivable so it does not permanently occupy the source's single active
slot. Archiving changes status; it does not delete or move evidence:

```bash
python3 <skill-dir>/scripts/review_repo.py archive --run-dir /absolute/run
```

Legacy v1/v2 runs remain readable and are marked `legacy_unverified`, but they
cannot acquire v3 completion or collection claims. Record `warning` to block and
archive an abandoned legacy run; never migrate or reinterpret its browser
evidence automatically.

Report the private backup URL, reviewed ref and commit, binding, mode,
conversation URL, final status, and `answer.md` path. Treat GPT output as review
advice, not verified local truth. Consult [KNOWN-ISSUES.md](KNOWN-ISSUES.md)
before changing browser or state-machine behavior.
