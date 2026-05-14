# Release Reference

Use this when creating tags, GitHub Releases, release notes, changelogs, or version bumps.

## Preflight

1. Confirm desired tag, for example `v1.2.0`.
2. Check clean state: `git status --short`.
3. Find previous tag: `git describe --tags --abbrev=0` when available.
4. Inspect version files: `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `VERSION`, mobile app metadata.
5. Confirm release branch policy. For major/minor releases, use `release/vX.Y` if the repo uses release branches or the user asks.
6. Confirm whether to publish GitHub Release now or only prepare notes/tag locally.

## Version Bump

- Keep version files and tag aligned: `v1.2.0` tag means file version `1.2.0`.
- Use structured tooling when available:
  - Node: `npm pkg set version=1.2.0` when `package.json` exists and npm is appropriate.
  - Python/Rust/TOML: use a TOML-aware edit path if tooling is present; avoid brittle regex for complex files.
  - Plain `VERSION`: exact single-line replacement is acceptable.
- Commit version metadata separately when it changes:
  - `🚀 release: bump version to 1.2.0`

## Release Notes

Derive notes from actual history:

```bash
git log <previous-tag>..HEAD --oneline --decorate
```

Use bilingual sections:

```markdown
# v1.2.0

## Highlights / 亮点

## Features / 新功能

## Fixes / 修复

## Documentation / 文档

## Maintenance / 维护

## Upgrade Notes / 升级说明
```

Map commits by type:

- `✨ feat` -> Features
- `🐛 fix`, `🚑 hotfix` -> Fixes
- `📝 docs` -> Documentation
- `👷 ci`, `👷 build`, `🔧 chore`, `♻️ refactor`, `✅ test` -> Maintenance

Do not invent impact. If history is sparse, say the release is maintenance-focused.

## Publish

After user confirmation:

1. Create annotated tag: `git tag -a vX.Y.Z -m "vX.Y.Z"`.
2. Push commits and tag to the confirmed remote.
3. Create release: `gh release create vX.Y.Z --notes-file <notes-file> --title "vX.Y.Z"`.
4. Verify with `gh release view vX.Y.Z` or the release URL returned by `gh`.

Never create a tag or GitHub Release when the working tree contains unrelated uncommitted changes.
