# Browser Protocol

This protocol bounds browser access while GPT Pro or Deep Research generates a
long response. The CLI state is an evidence ledger; it does not itself operate
the browser.

The v3 ledger is fail-closed: a browser observation becomes a state transition
only when its required evidence is supplied. Narrative claims such as "looks
done" or a progress assistant message are not completion evidence.

## Call Budget

For one run, the browser side may perform:

- when `gh auth status` is invalid and the user explicitly authorizes it, one
  GitHub CLI device-authorization attempt plus one fresh attempt only if the
  first code expires while the user completes sudo-mode authentication;
- one new saved-chat navigation;
- one targeted visible-capability read;
- one targeted Deep Research state read;
- at most one GitHub App grant check when existing authorization is unknown,
  and one exact source binding/readback;
- one single-operation composer fill and one value readback;
- one send-button click;
- one long completion wait, plus one more only after a genuine disconnect;
- one reattachment to the saved conversation URL;
- one targeted final-response extraction; and
- one screenshot only for a blocking warning or unknown UI state.

There is no allowance for periodic full-page reads, repeated screenshots,
conversation-wide `innerText`, progress scraping, reload loops, or repeated
history searches.

GitHub CLI authentication is conditional. Skip it completely when
`gh auth status -h github.com` already verifies the intended active account.
Codex may enter the one-time device code and click the GitHub CLI authorization
button only after explicit user authorization for this Skill. Passwords,
passkeys, authenticator codes, recovery codes, and GitHub Mobile confirmations
always remain user-operated. After that handoff, use a fresh code if the pending
one expired; do not reuse it or continue retrying.

The CLI and App are different principals. `gh auth status` proves only the local
GitHub CLI account used to publish and read back the mirror. The visible ChatGPT
GitHub App grant proves only connector authorization. Never infer either one
from the other. The CLI preflight must stop on invalid authentication; it never
starts `gh auth login` automatically.

## Owned Tabs

Register every ChatGPT draft, saved conversation, or temporary GitHub tab created
for the run. Activate a registered tab before recording browser evidence.

- Never record, activate, or close an unrelated user tab.
- Close abandoned drafts and temporary GitHub tabs before superseding a run.
- Keep the active saved conversation open while it may be needed for waiting,
  reconnecting, or collection.
- If a saved tab actually closes during a disconnect, record its close with
  `reason=disconnected`, then register and activate the replacement saved tab.
- Closing a tab in the ledger records an actual browser close; it is not a
  substitute for performing that close.

## Capability And Mode

Use semantic roles, accessible names, and visible control state. Do not bind to
minified classes or private endpoints.

The only acceptance label is visibly rendered `Pro`. A reasoning-strength label
such as `xhigh` or `极高` is not proof of Pro. In one observed UI, Pro was the
fifth/maximum slider position, but that position is only a current navigation
hint and not a stable invariant. If the visible label cannot be verified, stop.

Deep Research is a separate state:

- `review`: Pro visible and Deep Research active.
- `pro`: Pro visible and Deep Research inactive.

Select the mode from the current user request; neither mode is preferred for
all users. Do not repair a mismatch by silently changing run metadata. Before submission,
close abandoned run-owned tabs and use `supersede` while the run is still before
`composer-ready`. Once ready or blocked, use `end` with the actual observation,
then publish the corrected review. A missing URL does not prove it was unsent.

## Source Binding

Reuse an already established GitHub App grant. Check authorization separately
from source indexing when access is unknown or fails; do not reopen App settings
on every review or change the user's repository permissions automatically.

### Source Chip

Require the exact `owner/repository`, default branch, and commit recorded by the
publisher. If the App grant is verified but the exact source is not selectable,
record `source-index-pending` once and stop. Do not poll the source picker. Resume
the same run only when the user or a later bounded check establishes readiness.

Before accepting either `source-index-pending` or `source-bound`, the CLI
re-verifies that the mirror remains private, its default branch is unchanged,
and that branch still resolves to the published review commit. The accepted
assurance label is `github-app-source-chip-exact-commit-v1`. It binds the local
evidence chain; it does not attest ChatGPT's internal retrieval.

### Raw URL

This is the default route for `prepare-review`. After a verified upload it
combines the repository URL and unchanged request into frozen `prompt.txt`.
The legacy combined `publish` form still requires the URL already in its Prompt. Do not add a generic GitHub
plugin pill, switch the conversation to Work, or describe this as source-chip
indexing. Still verify repository privacy, default branch, commit, and App grant
as recorded evidence.

Its assurance label remains `raw-url-reference-only-v1`, even after a separately
verified App grant. A URL in the prompt is a reference, not proof that ChatGPT
opened, indexed, or read repository contents.

## Composer And Submission

1. Prepare the entire prompt outside the composer.
2. Fill or paste it in one operation. Do not use sequential keyboard typing.
3. Read the composer once and compare it byte-for-byte with `prompt.txt`.
4. Record `composer-ready` with the exact prompt SHA-256 and
   `fill-method=single-operation`.
5. Click the visible send button once. Never press Enter to submit or create a
   line break.
6. Wait for a durable `https://chatgpt.com/c/...` saved-conversation URL, then
   record `submitted` with `submission-method=send-button`.

If any readback differs, stop before sending. Do not clear and retype in the same
run unless the exact composer value can still be established as one operation;
otherwise supersede it.

`prompt.txt` itself is frozen by its recorded byte count and SHA-256. Every v3
tab registration/activation, browser-state, supersede, and collection operation
rechecks those bytes; closing an owned tab remains available for safe cleanup.
Changing the local evidence file invalidates the run rather than silently
changing what was reviewed.

## Waiting And Collection

Before `wait-start`, identify the currently visible generation sentinel using
targeted semantic button metadata and record one bounded opaque sentinel ID.
After `wait-start`, use one locator wait or page-side observer for the final
assistant action area or Deep Research report control. Do not issue status reads
while that wait is active.

First establish the currently visible generation sentinel from targeted button
metadata. Do not infer completion merely because a guessed or localized stop
locator has no match, and do not treat an assistant progress message as the final
answer. Browser-client timeout options use `timeoutMs`, not Playwright's usual
`timeout` spelling.

If the selected browser backend demonstrably caps long locator waits and its
read-only evaluation scope exposes no usable observer, a bounded compatibility
fallback is allowed: wait at least five minutes without reading the page, then
check only whether the already-identified generation sentinel is still visible.
Do not read response text, take repeated snapshots, or inspect new selectors
between checks. Stop at the mode deadline and record `pending`; never extend the
deadline by continuing sentinel checks.

Default upper bounds are 30 minutes for `pro` and 90 minutes for `review`.
Timeout alone does not authorize checks beyond the bounded sentinel fallback.
Record `pending`.

`wait-complete` requires all of the following in one transition:

- the same active saved-conversation tab and recorded sentinel ID;
- `generation-sentinel-absent-and-final-container-present` as the proof type;
- `deep-research-report` for `review`, or `assistant-turn` for `pro`; and
- the recorded generation sentinel absent before the final container is treated
  as stable.

Then target only that final container and extract it once, preserving visible
links when possible. Do not read the entire transcript. A short progress-only
assistant container is not completion evidence.

Before writing any answer bytes, create a current-user-owned `0700` temporary
directory and an empty `0600` regular file inside it. For example:

```bash
python3 - <<'PYTHON'
import os
import tempfile
from pathlib import Path

directory = Path(tempfile.mkdtemp(prefix="pgpr-answer-", dir="/private/tmp"))
answer = directory / "answer.md"
fd = os.open(answer, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
os.close(fd)
print(answer)
PYTHON
```

The process temporary directory is also allowed. Write the extraction into that
pre-created file without replacing it with a file of different permissions.
`collect` checks the opened directory and file for current-user ownership and
modes `0700` / `0600`; it rejects shared directories, symlinks, non-regular files,
and broader permissions before reading the answer. Never write into a public
file and then chmod it. If an extraction was exposed, re-extract into a newly
created private file; validation cannot undo earlier exposure.

Compute its SHA-256 before `collect`. Collection must name
the same conversation URL, active tab, and final-container kind recorded by
`wait-complete`; it rereads the file once and rejects a hash mismatch. The
resulting evidence proves the archived local bytes and their asserted browser
source, not cryptographic provenance from ChatGPT.

## Resume or End an Interrupted Run

`show` and an upload-only `publish` return `next_action` for the existing run.
Neither uploads again nor sends a message. Use the saved conversation URL;
never create another chat merely because the local record says `pending`.

After a later requested resume, make one targeted completion-state observation.
If the page has finished, `wait-complete` also accepts `pending` using the
recorded `last_incomplete_wait`. All sentinel, final-container, Prompt, and
conversation checks still apply; no extra wait or reconnect is charged. If it
is still generating and the wait budget is exhausted, keep it pending.

If the old tab actually disconnected, record its close, then register and
activate a replacement saved-conversation tab with exactly the same URL.
Pending completion may use that replacement; evidence retains the original
wait tab as well. An unrelated tab or a different conversation is rejected.

If abandoning a run, first observe in the saved conversation that generation
finished or was cancelled. Preserve an available answer through collection when
it is still wanted. To release a deliberately abandoned submitted run:

```bash
python3 <skill-dir>/scripts/review_repo.py end --run-dir /absolute/run \
  --observed cancelled --conversation-url https://chatgpt.com/c/CONVERSATION \
  --reason "review cancelled in its saved conversation"
```

Use `finished` instead if that is what was observed. For a run actually never
sent, use `--observed not-submitted` without a conversation URL. If Send happened
before recording was interrupted, record the existing submission first; local
`composer-ready` is not permission to assert that no message was sent. If a warning
prevented recording that submission, register and activate its actual saved
conversation tab. After observing that it finished or was cancelled, `end` can
accept that exact tab's URL. This recovers an ended record only; it does not
manufacture completion or answer evidence.

`end` retains every record and the private repository. It will not release an
upload while the publisher or its transfer child holds the execution lock.
For an old `preparing` run without that lock contract, first stop and verify the
old publisher and all Git/gh children have exited; only then add
`--publisher-stopped`. Never infer this from the run's age or a missing PID.
A partially uploaded backup stays mapped to the project, so the next upload
finishes against that same destination instead of leaving abandoned copies.

Every `blocked` run still protects its source, including a warning immediately
after Send but before its saved URL was recorded. `archive` cannot bypass that
protection; record the observed end first. Timeouts and closed tabs are
not proof that the web review stopped reading the repository.

### One disconnected-session recovery

Use the single recovery only for a disconnected browser session, closed tab, or
wait transport failure. Reopen the recorded conversation URL, make one targeted
completion-state read, then either collect or start the second long wait.

Do not recover from:

- an access-frequency warning;
- a repository, branch, commit, binding, capability, or mode mismatch;
- a duplicate or changed prompt;
- an authorization or indexing screen;
- an unknown confirmation that could send or publish; or
- a tab not owned by the run.

## Warning Handling

For frequent-access, unusual-automation, or rate-limit warnings:

1. stop all page reads;
2. record `warning`;
3. optionally capture one diagnostic screenshot;
4. do not dismiss, reload, resubmit, or open a replacement conversation; and
5. leave the saved conversation and run evidence intact for human inspection.


## CLI evidence examples

Use actual observed values for the placeholders. `--deep-research` is `inactive`
and the final container is `assistant-turn` in `pro` mode; they are `active` and
`deep-research-report` in `review` mode. The CLI only records observations.

```bash
python3 <skill-dir>/scripts/review_repo.py tab --run-dir /absolute/run \
  --action register --tab-id TAB --kind chatgpt-draft --url https://chatgpt.com/
python3 <skill-dir>/scripts/review_repo.py tab --run-dir /absolute/run \
  --action activate --tab-id TAB
python3 <skill-dir>/scripts/review_repo.py event --run-dir /absolute/run \
  --event source-bound --capability-label Pro --deep-research <active-or-inactive> \
  --app-grant verified --binding raw-url --repository owner/repository \
  --default-branch BRANCH --commit COMMIT --tab-id TAB
python3 <skill-dir>/scripts/review_repo.py event --run-dir /absolute/run \
  --event composer-ready --prompt-sha256 PROMPT_SHA256 \
  --fill-method single-operation --tab-id TAB
```

After clicking Send once and observing the saved URL:

```bash
python3 <skill-dir>/scripts/review_repo.py event --run-dir /absolute/run \
  --event submitted --conversation-url https://chatgpt.com/c/CONVERSATION \
  --submission-method send-button --tab-id TAB
python3 <skill-dir>/scripts/review_repo.py event --run-dir /absolute/run \
  --event wait-start --generation-sentinel OBSERVED_SENTINEL --tab-id TAB
```

After the bounded wait and full completion proof, extract into the private file
created by the example above, then collect:

```bash
python3 <skill-dir>/scripts/review_repo.py event --run-dir /absolute/run \
  --event wait-complete --generation-sentinel OBSERVED_SENTINEL \
  --completion-proof generation-sentinel-absent-and-final-container-present \
  --final-container <assistant-turn-or-deep-research-report> --tab-id TAB
python3 <skill-dir>/scripts/review_repo.py collect --run-dir /absolute/run \
  --answer-file /private/tmp/pgpr-answer-RANDOM/answer.md --answer-sha256 ANSWER_SHA256 \
  --source-kind <assistant-turn-or-deep-research-report> \
  --source-conversation-url https://chatgpt.com/c/CONVERSATION --source-tab-id TAB
```

For a correction before `composer-ready`, close abandoned owned tabs and use
`supersede` with the corrected mode, binding, reason, and complete message file.
Ready or blocked runs cannot be superseded: use the observed `end` path first,
then publish a new run against the same project backup. When using
`raw-url`, that replacement message must contain the exact verified URL; retain
the user's requirements unchanged. The old combined CLI remains supported.
