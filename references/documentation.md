# Documentation Reference

Use this when generating or polishing `README.md`, `CONTRIBUTING.md`, docs badges, architecture diagrams, or bilingual public-facing copy.

## README Shape

Default structure:

1. Project title and concise bilingual tagline.
2. Real badges only: license, package version, CI workflow, release, language/runtime.
3. What it does / Why it exists.
4. Features grounded in observed code or user-provided scope.
5. Architecture or data flow with Mermaid.
6. Quick Start with copyable commands.
7. Usage examples and configuration.
8. Project structure, if the repo is non-trivial.
9. Contributing link and license.

Write bilingual docs as paired sections, not two disconnected documents:

```markdown
## 快速开始 / Quick Start

中文说明。

English explanation.
```

## README Rules

- Do not invent features, benchmarks, compatibility promises, or CI status.
- Prefer accurate plain language over startup-style claims.
- If a command was run successfully, say so only in the final user response; the README itself should stay timeless.
- If the setup command is uncertain, include a short note such as `TODO: confirm install command` only when the user accepts placeholders.
- Use Mermaid for architecture when it clarifies the repo. Keep diagrams simple enough to maintain.

## CONTRIBUTING Shape

Include:

- Local setup and required tools.
- Branch naming: `feat/<topic>`, `fix/<topic>`, `docs/<topic>`, `release/vX.Y`.
- Commit convention, either existing project style or HubSage policy.
- Pull request steps: description, linked issue, tests, screenshots/logs when relevant.
- Review expectations and code style.
- Release process pointer if maintainers need it.

## AI Agent Skill Projects

For skill repositories:

- `README.md`: professional, objective, platform-aware; explain install path, trigger cases, safety boundaries, and examples.
- `SKILL.md`: concise operational instructions for the agent; vivid role framing is acceptable only when it improves compliance.
- Avoid platform-specific terms in public docs unless the skill truly depends on that platform.
