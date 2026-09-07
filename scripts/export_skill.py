#!/usr/bin/env python3
"""Export and verify a Skill snapshot from one immutable local Git commit."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


UPSTREAM = "https://github.com/Liii8888/private-github-pro-review"
PAYLOAD = (
    "SKILL.md",
    "LICENSE",
    "agents/openai.yaml",
    "references/browser-protocol.md",
    "scripts/review_repo.py",
)

STATE_ASSIGNMENT = b"DEFAULT_STATE_ROOT = default_state_root()\n"


class DistributionError(RuntimeError):
    pass


def git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", *args], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_REPLACE_OBJECTS": "1"},
    )
    if result.returncode:
        raise DistributionError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def prepare(repo: Path, ref: str, local_state_root: str | None = None) -> dict[str, tuple[bytes, int]]:
    if not re.fullmatch(r"[0-9a-f]{40}", ref):
        raise DistributionError("--ref must be a full immutable 40-character commit SHA")
    if git(repo, "rev-parse", "--verify", ref + "^{commit}").decode().strip() != ref:
        raise DistributionError("--ref does not identify the requested commit")
    if local_state_root is not None and not Path(local_state_root).is_absolute():
        raise DistributionError("--local-state-root must be an absolute path")

    changelog = git(repo, "show", ref + ":CHANGELOG.md").decode()
    version = re.search(r"^## (v\d+\.\d+\.\d+)\s*$", changelog, re.MULTILINE)
    if version is None:
        raise DistributionError("commit has no versioned CHANGELOG section")
    records = {}
    output = {}
    for relative in PAYLOAD:
        entry = git(repo, "ls-tree", "-z", ref, "--", relative)
        if not entry or entry.count(b"\0") != 1:
            raise DistributionError(f"missing or ambiguous payload: {relative}")
        metadata, name = entry[:-1].split(b"\t", 1)
        mode, kind, blob = metadata.decode().split()
        if kind != "blob" or mode not in {"100644", "100755"} or name.decode() != relative:
            raise DistributionError(f"payload must be a regular Git file: {relative}")
        source = git(repo, "cat-file", "blob", blob)
        content = source
        if relative == "scripts/review_repo.py" and local_state_root is not None:
            if source.count(STATE_ASSIGNMENT) != 1:
                raise DistributionError("default-state assignment changed; review the local adaptation")
            replacement = (
                'DEFAULT_STATE_ROOT = Path(os.environ.get("PRIVATE_GITHUB_PRO_REVIEW_HOME") or '
                + json.dumps(local_state_root, ensure_ascii=True) + ').expanduser()\n'
            ).encode()
            content = source.replace(STATE_ASSIGNMENT, replacement)
        output[relative] = (content, int(mode[-3:], 8))
        records[relative] = {
            "git_blob": blob, "mode": mode,
            "source_sha256": digest(source), "distributed_sha256": digest(content),
        }

    if b"disable-model-invocation: true" not in output["SKILL.md"][0]:
        raise DistributionError("source must preserve explicit Skill invocation")
    if b"allow_implicit_invocation: false" not in output["agents/openai.yaml"][0]:
        raise DistributionError("source must preserve explicit Codex invocation")
    adaptation = None if local_state_root is None else {
        "kind": "local-default-state-root-v1", "path": "scripts/review_repo.py",
        "state_root": local_state_root,
    }
    manifest = {
        "schema_version": 1, "skill": "private-github-pro-review",
        "version": version.group(1), "upstream": UPSTREAM, "source_commit": ref,
        "local_adaptation": adaptation, "files": records,
    }
    output["DISTRIBUTION.json"] = (encoded(manifest), 0o644)
    return output


def export_snapshot(repo: Path, ref: str, destination: Path, local_state_root: str | None = None) -> None:
    payload = prepare(repo, ref, local_state_root)
    if destination.exists() or destination.is_symlink():
        raise DistributionError("destination already exists; export to a new directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir(mode=0o700)
    # Write the manifest last: an interrupted export is not a verified snapshot.
    for relative in sorted(payload, key=lambda p: p == "DISTRIBUTION.json"):
        content, mode = payload[relative]
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(content)
        path.chmod(mode)


def verify_snapshot(repo: Path, ref: str, directory: Path, local_state_root: str | None = None) -> None:
    expected = prepare(repo, ref, local_state_root)
    if not directory.is_dir() or directory.is_symlink():
        raise DistributionError("snapshot must be a real directory")
    actual = set()
    for parent, directories, names in os.walk(directory, followlinks=False):
        for name in directories + names:
            path = Path(parent) / name
            if path.is_symlink():
                raise DistributionError(f"snapshot contains a symlink: {path.relative_to(directory)}")
        for name in names:
            path = Path(parent) / name
            relative = path.relative_to(directory).as_posix()
            actual.add(relative)
            if relative not in expected:
                raise DistributionError(f"unexpected snapshot file: {relative}")
            content, mode = expected[relative]
            if not path.is_file() or path.read_bytes() != content or path.stat().st_mode & 0o777 != mode:
                raise DistributionError(f"snapshot content or mode differs: {relative}")
    if actual != set(expected):
        raise DistributionError("snapshot is incomplete")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ["export", "verify"]:
        command = sub.add_parser(name)
        command.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
        command.add_argument("--ref", required=True, help="full source commit SHA")
        command.add_argument("--local-state-root", help="explicitly approved local default; omit for public distribution")
        command.add_argument("--output" if name == "export" else "--directory", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "export":
            export_snapshot(args.repo, args.ref, args.output, args.local_state_root)
            directory = args.output
        else:
            directory = args.directory
        verify_snapshot(args.repo, args.ref, directory, args.local_state_root)
    except (DistributionError, OSError, UnicodeError, ValueError) as error:
        print(f"distribution error: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"result": "verified", "commit": args.ref, "directory": str(directory)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
