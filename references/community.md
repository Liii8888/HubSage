# Community Reference

Use this when adding `.github` templates, codes of conduct, discussion norms, or lightweight GitHub Actions for community interaction.

## Issue Templates

Create `.github/ISSUE_TEMPLATE/bug_report.md` with YAML frontmatter:

```markdown
---
name: Bug report
about: Report a reproducible problem
title: "[Bug]: "
labels: bug, triage
assignees: ""
---

## Description

## Steps to Reproduce
1.
2.
3.

## Expected Behavior

## Actual Behavior

## Environment
- OS:
- Version:
- Runtime/toolchain:

## Additional Context
```

Create `.github/ISSUE_TEMPLATE/feature_request.md`:

```markdown
---
name: Feature request
about: Suggest an improvement or new capability
title: "[Feature]: "
labels: enhancement, triage
assignees: ""
---

## Problem

## Proposed Solution

## Alternatives Considered

## Additional Context
```

## Pull Request Template

Create `.github/PULL_REQUEST_TEMPLATE.md`:

```markdown
## Summary

## Related Issue
Closes #

## Changes
- _List the main changes._

## Verification
- [ ] I ran the relevant tests or checks.
- [ ] I updated documentation where needed.
- [ ] I added screenshots/logs for user-visible changes where useful.
```

Commit template additions with `📝 docs: add community templates` when the user requested a commit.

## Code Of Conduct

- Prefer the current Contributor Covenant text when the project is truly open to outside contributors.
- If offline, create a concise placeholder and tell the user it should be reviewed before public launch.
- Do not add a code of conduct to a private/internal repo unless the user asks.

## Basic GitHub Actions

For small projects, prefer useful checks over decorative automation:

- CI workflow for the detected stack if tests/build commands are known.
- Issue greeting/triage workflow only when the user wants community automation.
- Use least privileges:

```yaml
permissions:
  issues: write
  contents: read
```

Avoid `pull_request_target` unless there is a reviewed security reason. Do not promise visible automation for `watch.started`; GitHub cannot comment to stargazers without another target surface.
