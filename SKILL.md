---
name: private-github-pro-review
disable-model-invocation: true
description: "Use when the user explicitly asks to back up a local Git repository to its persistent private GitHub repository, then review it in ChatGPT Pro with their chosen mode and unchanged review requirements, and save the final answer."
---

# Private GitHub Pro Review

Upload the requested local project to its private GitHub backup, paste the
verified repository link and the user's review requirements into ChatGPT Pro,
and save the completed review. First use creates the backup; later reviews
update the same repository. Keep the backup after collecting the answer.

## Scope the review

Use this Skill only when the user explicitly requests it and authorizes the
repository upload and ChatGPT review. Reuse authorization already given for the
same work. Resolve the Skill directory as `<skill-dir>`.

Choose from the current request, not a universal preference:

- `pro` means Pro without Deep Research; `review` means Pro with Deep Research.
  Both require visibly selected Pro before sending.
- If the user wants their current changes reviewed, include uncommitted changes
  with `--include-working-tree`. If they want only committed code, use
  `--committed-only`. A dirty checkout without either choice stops for clarification.
- Save user-supplied review text unchanged in a UTF-8 file. If they gave a goal
  without a message to send, draft a short request using the guidance below.
  Only ask about mode or scope when it cannot be determined from their request.

One project means one resolved local Git root, with one mapping in the selected
state directory. Do not run the same project through competing state directories
or move its folder without reconciling that mapping.

## 1. Upload the project

Use the intended existing GitHub CLI account. If authentication is invalid,
follow the conditional login recovery in the [browser protocol](references/browser-protocol.md);
do not reset a valid login. First-use GitHub App and browser setup tips are in
[README.md](README.md#首次使用的小提示); they are not a mandatory repeated checklist.

```bash
python3 <skill-dir>/scripts/review_repo.py publish --repo /absolute/project/path
```

Add the selected working-tree flag when applicable. Read the result:

- `uploaded` and `mirror_private: true`: save the returned `run_dir` and URL.
- `resume-required`: continue the listed run according to `next_action`; nothing
  was uploaded. Do not make another conversation or overwrite its review source.
- `prepared`: this was a dry run, not an upload. Archive it before publishing.
- An error: resolve the stated cause; never claim the upload succeeded.

The project mapping selects the same private backup on subsequent reviews.
For a first-use name that cannot be inferred, use `--mirror owner/repository`.
An existing repository must match this project's management marker and private
identity; the script will not adopt an unrelated private repository.

The backup includes local branches, tags, reachable history, and approved WIP.
Ignored caches/build output are excluded. Upload staging leaves the local
branch, index, working tree, and remotes unchanged. It preserves remote history
without force-pushing or deleting refs, and makes the reviewed version the
backup's default branch. Credential scanning, destination checks, and exact
commit checks remain automatic. A sensitive-path exception requires explicit
per-path authorization with `--allow-sensitive-path`; a passed scan cannot prove
that every kind of secret was found.

## 2. Prepare the message after upload

When drafting a request, keep the user's stated requirements and use their
language. For a general review, a useful direction is:

> Understand the project's intended use. Focus on issues that materially affect
> its goals, explaining their impact with supporting code. State uncertainty
> where evidence is incomplete.

Adapt the focus to the current task; let Pro choose its investigation and
response structure. Use this guidance only when drafting a message, not as text
to append to a user-supplied or already frozen request.

Select the mode from this review's request, then run:

```bash
python3 <skill-dir>/scripts/review_repo.py prepare-review \
  --run-dir /absolute/run --mode <pro-or-review> \
  --prompt-file /absolute/review-request.txt
```

The default `raw-url` route prefixes the verified GitHub URL to the unchanged
request, unless the message already starts with that exact URL alone on its first
line. Inline links and Markdown get the verified first line added; the original
request is not rewritten. `request.txt` preserves the
original bytes; `prompt.txt` is the complete frozen message to paste. Upload
receipts remain unchanged. Do not edit either file after preparation.

If the user chose an exact GitHub source chip, add `--binding source-chip`;
that route preserves the request as the complete message and binds the source
in the picker. Do not impose the picker route on a link-based review.

The original combined `publish --mode ... --prompt-file ...` command remains
supported for existing callers. Its complete Prompt stays byte-for-byte and its
existing binding default remains `source-chip`.
For its explicit `raw-url` option, put the complete repository URL alone on the
first line of the supplied message. Older frozen raw-url messages without that
first line remain readable, but cannot pass current source checks; do not rewrite
historical records to make them pass.

## 3. Send once in ChatGPT Pro

Read and follow the [browser protocol](references/browser-protocol.md) for the
browser phase, including its command examples and recovery rules. Use a
supported browser connection to the user's logged-in ChatGPT session. Never
copy cookies/profiles, use private ChatGPT APIs, or use raw browser automation
outside that supported connection.

Open one fresh saved conversation, select the chosen Pro mode, paste the frozen
message in one operation, check its value once, and click Send once. Register
only this run's tabs. Keep source/model checks, composer fill, and Send in the
same verified ChatGPT tab. If the draft tab changes before the composer is ready,
record source/model evidence again there. Save the conversation URL immediately
after sending. Existing
GitHub App authorization can be reused; change its settings only if access fails
or the user asks. A pasted URL does not prove that ChatGPT retrieved the code.

Do not split one review into multiple chats. If the local record was interrupted
around Send, inspect the owned tab first: record an already-sent conversation,
never blindly send again. Before `composer-ready`, a correction can reuse the
frozen upload through `supersede` after closing abandoned drafts. Once ready or
blocked, first inspect and `end` the old run, then publish the corrected review;
absence of a recorded URL alone cannot prove that Send never happened.

## 4. Wait, collect, and review again

Use the protocol's bounded completion wait without repeated response scraping.
Only accept completion after the recorded generation sentinel disappears and
the mode's final answer/report container is present. Create the owned `0700`
temporary directory and `0600` answer file before extraction, then collect the
final container with its hash and saved conversation/tab evidence.

On interruption, inspect the existing run with `show --run-dir /absolute/run`.
A `pending` run whose page has now finished can record the same strict
`wait-complete` evidence and collect, even after its wait budget is exhausted.
Resume only the saved conversation; do not resend or upload another version.
If its tab disconnects after completion, follow the protocol to revalidate the
same saved conversation in its replacement tab before collecting. An interrupted
`collect` can retry the same verified extraction without overwriting the answer.

If the review is abandoned, confirm in the browser that it finished or was
cancelled, then use `end` as described in the protocol. A timeout or closed tab
alone does not prove it stopped. An active upload cannot be ended while its
publisher or transfer child still holds its execution lock.

After `collected` or an explicitly recorded `ended`, the next requested review
uploads the new version to the same private backup. Keep past runs and the
repository. `archive` changes only a run's local status; it deletes no evidence.
Legacy runs remain readable and unverified, never silently upgraded.

Report the backup URL, reviewed commit, mode, conversation URL, final status,
and answer path. Treat the answer as review advice to verify against the code.
Current limitations are in [KNOWN-ISSUES.md](KNOWN-ISSUES.md).
