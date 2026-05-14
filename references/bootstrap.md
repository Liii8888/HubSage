# Bootstrap Reference

Use this when initializing a new repository or standardizing a bare project for GitHub.

## Questions To Confirm

Ask only what affects generated files or public actions:

- Repository name, one-sentence description, public/private visibility.
- Primary stack and package manager.
- License preference:
  - permissive commercial use: MIT or Apache-2.0;
  - patent protection: Apache-2.0;
  - derivatives must stay open: GPL-3.0;
  - file-level copyleft: MPL-2.0;
  - not open source yet: proprietary/no license.
- Documentation language: bilingual by default, or project-specific.
- Whether to create/push the GitHub remote now.
- Whether to add community templates and basic Actions now.

Do not use remembered answers from other projects.

## Initialization Flow

1. Run preflight: `git status --short`, `git remote -v`, `git branch --show-current`, `gh --version`, `gh auth status` when GitHub operations are requested.
2. Generate minimal project foundation:
   - `.gitignore` matched to stack;
   - `LICENSE` from confirmed license;
   - `README.md`;
   - `CONTRIBUTING.md`;
   - optional `.github` files from `community.md`.
3. If no git repo exists: `git init`, then `git branch -M main`.
4. Review diff and run `git diff --check`.
5. Commit only after the user has approved the generated foundation:
   - `🎉 init: initial project foundation`
6. Create remote with `gh repo create` only after confirming owner/name/visibility.
7. Push with `git push -u origin main` only after confirming remote URL and branch.

## .gitignore Guidance

- Prefer a generated `.gitignore` tailored to the detected stack.
- Preserve existing ignore rules unless they expose secrets or generated artifacts.
- Common additions: dependency folders, build outputs, editor caches, OS metadata, local env files.
- Do not ignore lockfiles by default; follow the package manager convention.

## License Guidance

- A missing license means no open-source grant. Say this plainly.
- Do not default to MIT without asking.
- If the user is uncertain, recommend MIT for small permissive tools, Apache-2.0 for broader public projects where patent language matters, and GPL-3.0 when reciprocal openness is the goal.
