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
- one GitHub App grant check and one exact source binding/readback;
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

Do not repair a mismatch by silently changing run metadata. Before submission,
close abandoned run-owned tabs and use `supersede` so the corrected run has its
own evidence.

## Source Binding

Verify GitHub App authorization separately from ChatGPT source indexing.

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

Use only when the run was published with `binding=raw-url`. The exact repository
URL must already be part of the unchanged prompt. Do not add a generic GitHub
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

Write the extraction to a non-symlink file under `/private/tmp` or the process
temporary directory. Compute its SHA-256 before `collect`. Collection must name
the same conversation URL, active tab, and final-container kind recorded by
`wait-complete`; it rereads the file once and rejects a hash mismatch. The
resulting evidence proves the archived local bytes and their asserted browser
source, not cryptographic provenance from ChatGPT.

## One Recovery

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
