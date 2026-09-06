#!/usr/bin/env python3
"""Back up a local Git repository and track one bounded ChatGPT review run."""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from contextlib import ExitStack, contextmanager
from functools import wraps
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator, Mapping


def default_state_root(
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    values = os.environ if environment is None else environment
    configured = values.get("PRIVATE_GITHUB_PRO_REVIEW_HOME")
    if configured:
        return Path(configured).expanduser()

    state_home = values.get("XDG_STATE_HOME")
    if state_home:
        return Path(state_home).expanduser() / "private-github-pro-review"

    return (Path.home() if home is None else home) / ".local" / "state" / (
        "private-github-pro-review"
    )


DEFAULT_STATE_ROOT = default_state_root()
MAX_GITHUB_BLOB_BYTES = 100_000_000
MANAGER = "private-github-pro-review"
DESCRIPTION_PREFIX = f"Managed by {MANAGER}; project="
RUN_VERSION = 3
_UPLOAD_LOCK_FD: int | None = None
COMPLETION_PROOF = "generation-sentinel-absent-and-final-container-present"
SOURCE_CHIP_PENDING_ASSURANCE = "source-chip-pending-v1"
SOURCE_CHIP_BOUND_ASSURANCE = "github-app-source-chip-exact-commit-v1"
RAW_URL_ASSURANCE = "raw-url-reference-only-v1"
GENERIC_REPOSITORY_NAMES = {
    "code",
    "git",
    "home",
    "local",
    "project",
    "repo",
    "repository",
    "source",
    "src",
    "workspace",
}
ACTIVE_STATUSES = {
    "preparing",
    "prepared",
    "uploaded",
    "published",
    "source-index-pending",
    "source-bound",
    "composer-ready",
    "submitted",
    "waiting",
    "pending",
    "reconnecting",
    "completed",
}
ARCHIVABLE_STATUSES = {"prepared", "collected", "blocked", "failed", "superseded", "ended"}
# Once the composer is ready, Send may happen before its acknowledgement is
# saved. Retire that uncertain run only through end's explicit observation.
SUPERSEDEABLE_STATUSES = {"published", "source-index-pending", "source-bound"}
CHATGPT_CONVERSATION_RE = re.compile(
    r"^https://chatgpt\.com/(?:c/[^/?#]+|g/[^/?#]+/c/[^/?#]+)(?:[?#].*)?$"
)
PRIVATE_KEY_MARKERS = (
    b"-----BEGIN PRIVATE KEY-----",
    b"-----BEGIN RSA PRIVATE KEY-----",
    b"-----BEGIN EC PRIVATE KEY-----",
    b"-----BEGIN OPENSSH PRIVATE KEY-----",
)
TOKEN_PATTERNS = (
    re.compile(rb"\bghp_[A-Za-z0-9]{30,}\b"),
    re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{40,}\b"),
    re.compile(rb"\bsk-[A-Za-z0-9]{24,}\b"),
)
SENSITIVE_PATH_RE = re.compile(
    r"(?:^|/)(?:"
    r"\.env(?:\.[^/]+)?|"
    r"\.netrc|\.npmrc|"
    r"id_(?:rsa|ed25519|ecdsa)(?:\.pub)?|"
    r"credentials?(?:\.(?:json|ya?ml|toml))?|"
    r"service-account[^/]*\.json|"
    r"[^/]+\.(?:pem|p12|pfx|key|keychain-db)"
    r")$",
    re.IGNORECASE,
)


class ReviewError(RuntimeError):
    pass


def abort(message: str) -> None:
    raise ReviewError(message)


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        text=True,
        input=input_text,
        env=env,
        pass_fds=(() if _UPLOAD_LOCK_FD is None else (_UPLOAD_LOCK_FD,)),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        abort(f"command failed ({result.returncode}): {' '.join(command)}\n{detail}")
    return result


def github(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    # Scope host selection to this child; never alter the user's gh configuration.
    command = ["gh", *args]
    if args and args[0] == "api":
        command[2:2] = ["--hostname", "github.com"]
    return run(command, check=check, env={**os.environ, "GH_HOST": "github.com"})


def run_bytes(
    command: list[str],
    *,
    cwd: Path | None = None,
    input_data: bytes | None = None,
) -> bytes:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        input=input_data,
        pass_fds=(() if _UPLOAD_LOCK_FD is None else (_UPLOAD_LOCK_FD,)),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        abort(f"command failed ({result.returncode}): {' '.join(command)}\n{detail}")
    return result.stdout


def git(repo: Path, *args: str, check: bool = True, input_text: str | None = None) -> str:
    return run(
        ["git", *args],
        cwd=repo,
        check=check,
        input_text=input_text,
    ).stdout.strip()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return sha256_bytes(payload)


def slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    return normalized or "repository"


def ref_slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._/-]+", "-", value).strip("-./")
    return normalized or "ref"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def make_run_id(repo: Path) -> str:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    nonce = os.urandom(4).hex()
    return f"{stamp}-{slug(repo.name).lower()}-{nonce}"


def ensure_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


@contextmanager
def state_transaction(state_root: Path) -> Iterator[None]:
    ensure_private_directory(state_root)
    lock_path = state_root / ".state.lock"
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


@contextmanager
def upload_execution(run_dir: Path) -> Iterator[None]:
    """Hold a per-run lease, including in upload children, without a time limit."""
    global _UPLOAD_LOCK_FD
    descriptor = os.open(run_dir / ".upload.lock", os.O_RDWR | os.O_CREAT, 0o600)
    previous = _UPLOAD_LOCK_FD
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            abort("the publisher or its upload child is still running; resume after it exits")
        _UPLOAD_LOCK_FD = descriptor
        yield
    finally:
        _UPLOAD_LOCK_FD = previous
        # Closing (not explicitly unlocking) keeps the lease held by any child
        # still doing a transfer after its parent exits.
        os.close(descriptor)


def atomic_write(path: Path, data: bytes, mode: int = 0o600) -> None:
    ensure_private_directory(path.parent)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(temporary, flags, mode)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(mode)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_json(path: Path, value: Any) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    atomic_write(path, (payload + "\n").encode("utf-8"))


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        abort(f"cannot read valid JSON from {path}: {exc}")


def repository_root(value: str) -> Path:
    candidate = Path(value).expanduser().resolve()
    result = run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=candidate,
        check=False,
    )
    if result.returncode:
        abort(f"not a readable Git repository: {candidate}")
    root = Path(result.stdout.strip()).resolve()
    if root != candidate:
        abort(f"pass the repository root, not a nested path: {root}")
    return root


def read_prompt(path_value: str) -> bytes:
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        abort(f"prompt file is not a regular file: {path}")
    data = path.read_bytes()
    if not data:
        abort("prompt file is empty")
    if b"\x00" in data:
        abort("prompt file contains NUL bytes")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        abort(f"prompt file is not UTF-8: {exc}")
    return data


def read_regular_file_bytes(
    path_value: str,
    *,
    label: str,
    allowed_roots: Iterable[Path] | None = None,
) -> tuple[Path, bytes]:
    raw = Path(path_value).expanduser()
    if not raw.is_absolute():
        raw = Path.cwd() / raw
    lexical = Path(os.path.abspath(raw))
    if lexical.is_symlink():
        abort(f"{label} must not be a symlink: {lexical}")
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as exc:
        abort(f"cannot resolve {label}: {lexical}: {exc}")
    if allowed_roots is not None:
        roots = [root.expanduser().resolve() for root in allowed_roots]
        if not any(resolved == root or root in resolved.parents for root in roots):
            abort(
                f"{label} must be under a private temporary root: {resolved}"
            )
    if lexical.parent.is_symlink():
        abort(f"{label} directory must not be a symlink: {lexical.parent}")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        directory = os.open(resolved.parent, directory_flags)
    except OSError as exc:
        abort(f"cannot open {label} directory: {resolved.parent}: {exc}")
    try:
        metadata = os.fstat(directory)
        if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
            abort(f"{label} directory must be owned by the current user with mode 0700")
        # Open relative to the checked directory, refusing symlinks and avoiding
        # blocking on a FIFO before we can reject non-regular files.
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        try:
            descriptor = os.open(resolved.name, flags, dir_fd=directory)
        except OSError as exc:
            abort(f"cannot open {label}: {resolved}: {exc}")
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                abort(f"{label} is not a regular file: {resolved}")
            if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) != 0o600:
                abort(f"{label} must be owned by the current user with mode 0600")
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                data = handle.read()
        finally:
            os.close(descriptor)
    finally:
        os.close(directory)
    return resolved, data


def split_nul(data: bytes) -> list[str]:
    return [item.decode("utf-8", errors="surrogateescape") for item in data.split(b"\0") if item]


def git_paths(repo: Path, *args: str) -> list[str]:
    return split_nul(run_bytes(["git", *args, "-z"], cwd=repo))


def current_branch(repo: Path) -> str | None:
    result = run(
        ["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
        cwd=repo,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def ref_map(repo: Path, prefix: str) -> dict[str, str]:
    output = git(repo, "for-each-ref", "--format=%(refname)%09%(objectname)", prefix)
    result: dict[str, str] = {}
    for line in output.splitlines():
        if not line:
            continue
        refname, object_id = line.split("\t", 1)
        result[refname] = object_id
    return result


def copy_untracked(source: Path, destination: Path, paths: Iterable[str]) -> None:
    for relative in paths:
        source_path = source / relative
        destination_path = destination / relative
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        if source_path.is_symlink():
            destination_path.symlink_to(os.readlink(source_path))
        elif source_path.is_file():
            shutil.copy2(source_path, destination_path, follow_symlinks=False)
        else:
            abort(f"unsupported untracked entry: {relative}")


def prepare_staging_repository(
    source: Path,
    include_working_tree: bool,
    run_id: str,
    staging_parent: Path,
    *,
    committed_only: bool = False,
) -> dict[str, Any]:
    head = git(source, "rev-parse", "HEAD")
    head_tree = git(source, "rev-parse", "HEAD^{tree}")
    branch = current_branch(source)
    status = run_bytes(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=source,
    )
    source_dirty = bool(status)
    if include_working_tree and committed_only:
        abort("choose either --include-working-tree or --committed-only")
    if source_dirty and not include_working_tree and not committed_only:
        abort("working tree is dirty; choose --include-working-tree or --committed-only explicitly")
    dirty = source_dirty and include_working_tree

    untracked = git_paths(source, "ls-files", "--others", "--exclude-standard")
    ignored = git_paths(source, "ls-files", "--others", "--ignored", "--exclude-standard")
    stage = staging_parent / "repository"
    run(
        ["git", "clone", "--quiet", "--no-hardlinks", "--no-checkout", str(source), str(stage)]
    )
    git(stage, "fetch", "--quiet", str(source), "+refs/heads/*:refs/remotes/source/*")
    git(stage, "fetch", "--quiet", "--tags", str(source))
    git(stage, "checkout", "--quiet", "--detach", head)
    git(stage, "config", "user.name", "Private GitHub Pro Review")
    git(stage, "config", "user.email", "private-github-pro-review@example.invalid")

    review_commit = head
    review_ref = branch or f"review/detached/{run_id}"
    if dirty:
        patch = run_bytes(
            ["git", "diff", "--binary", "--full-index", "HEAD"],
            cwd=source,
        )
        if patch:
            run_bytes(
                ["git", "apply", "--binary", "--whitespace=nowarn", "-"],
                cwd=stage,
                input_data=patch,
            )
        copy_untracked(source, stage, untracked)
        git(stage, "add", "--all")
        git(
            stage,
            "commit",
            "--quiet",
            "-m",
            f"review(wip): {run_id}\n\nSource-Commit: {head}\nSource-Tree: {head_tree}",
        )
        review_commit = git(stage, "rev-parse", "HEAD")
        review_ref = f"review/wip/{run_id}"

    return {
        "stage": stage,
        "source_head": head,
        "source_head_tree": head_tree,
        "source_branch": branch,
        "dirty": dirty,
        "source_dirty": source_dirty,
        "untracked": sorted(untracked),
        "ignored": sorted(ignored),
        "review_commit": review_commit,
        "review_ref": review_ref,
        "branches": ref_map(source, "refs/heads"),
        "tags": ref_map(source, "refs/tags"),
    }


def tree_entries(repo: Path, commit: str) -> list[dict[str, str]]:
    output = run_bytes(
        ["git", "ls-tree", "-r", "-z", "--full-tree", commit],
        cwd=repo,
    )
    entries: list[dict[str, str]] = []
    for record in output.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, object_type, object_id = metadata.decode("ascii").split(" ")
        entries.append(
            {
                "mode": mode,
                "type": object_type,
                "object": object_id,
                "path": raw_path.decode("utf-8", errors="surrogateescape"),
            }
        )
    return entries


def object_sizes(repo: Path, objects: Iterable[str]) -> dict[str, tuple[str, int]]:
    unique = sorted(set(objects))
    if not unique:
        return {}
    query = "\n".join(unique) + "\n"
    output = git(
        repo,
        "cat-file",
        "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        input_text=query,
    )
    result: dict[str, tuple[str, int]] = {}
    for line in output.splitlines():
        object_id, object_type, raw_size = line.split(" ", 2)
        result[object_id] = (object_type, int(raw_size))
    return result


def reachable_objects(
    repo: Path, commit: str
) -> tuple[dict[str, set[str]], dict[str, tuple[str, int]]]:
    # Object IDs are line-safe; paths are not. rev-list's object names also
    # discard aliases, so obtain every real path from NUL-delimited trees.
    object_ids = git(repo, "rev-list", "--objects", "--no-object-names", "--all", commit).splitlines()
    sizes = object_sizes(repo, object_ids)
    roots = set(git(repo, "rev-list", "--all", commit, "--format=%T", "--no-commit-header").splitlines())
    # Git also permits tags directly naming trees or blobs. Scan tree tags with
    # their full paths, and retain unnamed blobs in sizes for content scanning.
    for object_id in set(git(repo, "for-each-ref", "--format=%(objectname)").splitlines()):
        if sizes[object_id][0] == "tag":
            object_id = git(repo, "rev-parse", f"{object_id}^{{}}")
        if sizes[object_id][0] == "tree":
            roots.add(object_id)
    names: dict[str, set[str]] = {}
    submodules: set[str] = set()
    for tree in sorted(roots):
        for entry in tree_entries(repo, tree):
            if entry["mode"] == "160000":
                submodules.add(entry["path"])
            if entry["type"] == "blob":
                names.setdefault(entry["object"], set()).add(entry["path"])
    if submodules:
        abort("submodule content is not backed up by this repository: " + ", ".join(sorted(submodules)))
    return names, sizes


def sensitive_path(path: str) -> bool:
    lowered = path.casefold()
    if lowered.endswith(("/.env.example", "/.env.sample")) or lowered in {
        ".env.example",
        ".env.sample",
    }:
        return False
    return bool(SENSITIVE_PATH_RE.search(path))


def iter_blob_contents(repo: Path, objects: Iterable[str]) -> Iterable[tuple[str, bytes]]:
    process = subprocess.Popen(
        ["git", "cat-file", "--batch"],
        cwd=repo,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None
    try:
        for object_id in objects:
            process.stdin.write(object_id.encode("ascii") + b"\n")
            process.stdin.flush()
            header = process.stdout.readline().decode("ascii", errors="replace").strip()
            parts = header.split(" ")
            if len(parts) != 3 or parts[1] != "blob":
                abort(f"invalid git cat-file response for {object_id}: {header}")
            size = int(parts[2])
            content = process.stdout.read(size)
            if len(content) != size or process.stdout.read(1) != b"\n":
                abort(f"truncated git cat-file response for {object_id}")
            yield object_id, content
        process.stdin.close()
        return_code = process.wait()
        if return_code:
            detail = process.stderr.read().decode("utf-8", errors="replace").strip()
            abort(f"git cat-file --batch failed: {detail}")
    finally:
        if not process.stdin.closed:
            process.stdin.close()
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stdout.close()
        process.stderr.close()


def validate_backup_payload(
    repo: Path,
    review_commit: str,
    allowed_sensitive_paths: set[str],
) -> dict[str, Any]:
    entries = tree_entries(repo, review_commit)
    names, sizes = reachable_objects(repo, review_commit)
    oversized = []
    for object_id, (object_type, size) in sizes.items():
        if object_type == "blob" and size >= MAX_GITHUB_BLOB_BYTES:
            oversized.append(f"{sorted(names.get(object_id, {object_id}))!r} ({size} bytes)")
    if oversized:
        abort("GitHub oversized blob(s): " + "; ".join(sorted(oversized)))

    history_sensitive = sorted(
        {
            path
            for paths in names.values()
            for path in paths
            if sensitive_path(path) and path not in allowed_sensitive_paths
        }
    )
    if history_sensitive:
        abort(
            "credential-like path(s) require --allow-sensitive-path: "
            + ", ".join(history_sensitive)
        )

    candidate_blobs = sorted(
        object_id
        for object_id, (object_type, size) in sizes.items()
        if object_type == "blob"
    )
    lfs_paths: set[str] = set()
    content_sensitive: set[str] = set()
    for object_id, content in iter_blob_contents(repo, candidate_blobs):
        paths = names.get(object_id, set())
        display_paths = paths or {f"unnamed Git blob {object_id}"}
        if content.startswith(b"version https://git-lfs.github.com/spec/v1\n"):
            lfs_paths.update(display_paths)
        if any(marker in content for marker in PRIVATE_KEY_MARKERS) or any(
            pattern.search(content) for pattern in TOKEN_PATTERNS
        ):
            content_sensitive.update(paths - allowed_sensitive_paths if paths else display_paths)

    entry_sizes = object_sizes(repo, (entry["object"] for entry in entries if entry["type"] == "blob"))
    inventory: list[dict[str, Any]] = []
    for entry in entries:
        if entry["type"] != "blob":
            continue
        _, size = entry_sizes[entry["object"]]
        inventory.append({"path": entry["path"], "object": entry["object"], "size": size})
    if lfs_paths:
        abort("Git LFS pointer-only content is not reviewable: " + ", ".join(sorted(lfs_paths)))
    if content_sensitive:
        abort(
            "credential-like content requires --allow-sensitive-path: "
            + ", ".join(sorted(content_sensitive))
        )
    return {
        "file_count": len(inventory),
        "files": sorted(inventory, key=lambda item: item["path"]),
        "reachable_object_count": len(sizes),
    }


def active_github_owner() -> str:
    result = github("auth", "status", "--hostname", "github.com", check=False)
    if result.returncode:
        abort("gh is not authenticated to github.com")
    owner = github("api", "user", "--jq", ".login").stdout.strip()
    if not owner:
        abort("cannot determine the active GitHub account")
    return owner


def project_key(repo: Path) -> str:
    return sha256_bytes(str(repo).encode("utf-8"))[:20]


def github_origin_name(repo: Path) -> str | None:
    result = run(["git", "remote", "get-url", "origin"], cwd=repo, check=False)
    if result.returncode:
        return None
    value = result.stdout.strip()
    patterns = (
        r"^https://github\.com/[^/]+/([^/]+?)(?:\.git)?$",
        r"^git@github\.com:[^/]+/([^/]+?)(?:\.git)?$",
        r"^ssh://git@github\.com/[^/]+/([^/]+?)(?:\.git)?$",
    )
    for pattern in patterns:
        match = re.match(pattern, value, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def useful_repository_name(value: str | None) -> str | None:
    if not value:
        return None
    candidate = slug(value)
    if candidate.casefold() in GENERIC_REPOSITORY_NAMES:
        return None
    return candidate


def resolve_mirror(
    owner: str,
    repo: Path,
    explicit: str | None,
    existing_mapping: dict[str, Any] | None,
) -> str:
    mapped = (existing_mapping or {}).get("mirror")
    if mapped:
        if explicit and explicit.casefold() != str(mapped).casefold():
            abort(
                "this source already has a persistent mirror mapping; "
                f"refusing a second destination ({mapped} != {explicit})"
            )
        return str(mapped)
    if explicit:
        return explicit

    candidate = useful_repository_name(github_origin_name(repo))
    if candidate is None:
        candidate = useful_repository_name(repo.name)
    if candidate is None:
        abort(
            "cannot derive a meaningful private mirror name from this repository; "
            "pass --mirror owner/repository explicitly"
        )
    return f"{owner}/{candidate}-private-backup"


def require_raw_repository_url(prompt: bytes, mirror: str) -> str:
    url = f"https://github.com/{mirror}"
    if url.encode("utf-8") not in prompt:
        abort(
            "raw-url binding requires the exact private repository URL to already "
            f"appear unchanged in the prompt: {url}"
        )
    return url


def load_project_map(state_root: Path) -> dict[str, Any]:
    path = state_root / "projects.json"
    return read_json(path) if path.exists() else {"version": 1, "projects": {}}


def save_project_map(state_root: Path, value: dict[str, Any]) -> None:
    write_json(state_root / "projects.json", value)


def mirror_identity(mirror: str) -> tuple[str, str]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}", mirror):
        abort(f"invalid GitHub owner/repository: {mirror}")
    owner, name = mirror.split("/")
    if name in {".", ".."}:
        abort(f"invalid GitHub repository name: {mirror}")
    return owner, name


def github_repo_info(mirror: str) -> dict[str, Any] | None:
    mirror_identity(mirror)
    result = github("api", f"repos/{mirror}", check=False)
    if result.returncode:
        if "404" in result.stderr or "Not Found" in result.stderr:
            return None
        abort(result.stderr.strip() or f"cannot inspect GitHub repository {mirror}")
    try:
        info = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        abort(f"GitHub repository metadata is invalid: {exc}")
    if not isinstance(info, dict):
        abort("GitHub repository metadata must be an object")
    return info


def validate_mirror_info(mirror: str, marker: str, info: dict[str, Any] | None) -> dict[str, Any]:
    owner, name = mirror_identity(mirror)
    if info is None:
        abort(f"GitHub repository is unavailable: {mirror}")
    actual_owner = info.get("owner")
    if not isinstance(actual_owner, dict) or any(
        not isinstance(actual, str) or actual.casefold() != expected.casefold()
        for actual, expected in (
            (actual_owner.get("login"), owner),
            (info.get("name"), name),
            (info.get("full_name"), mirror),
            (info.get("html_url"), f"https://github.com/{mirror}"),
        )
    ):
        abort(f"GitHub repository identity mismatch: {mirror}")
    if info.get("private") is not True:
        abort(f"refusing non-private GitHub repository: {mirror}")
    if info.get("description") != marker:
        abort(f"GitHub repository management marker drift: {mirror}")
    return info


def ensure_private_mirror(mirror: str, marker: str) -> tuple[dict[str, Any], bool]:
    info = github_repo_info(mirror)
    created = False
    if info is None:
        github(
            "repo", "create", mirror, "--private", "--disable-issues",
            "--disable-wiki", "--description", marker,
        )
        info = github_repo_info(mirror)
        created = True
    return validate_mirror_info(mirror, marker, info), created


def verified_upload_remote(stage: Path, mirror: str, run_id: str) -> str:
    mirror_identity(mirror)
    remote = f"{MANAGER}-upload-{run_id}"
    # Only the disposable staging repository is changed. Use this same named
    # remote for every subsequent read and push, including any pushurl rules.
    git(stage, "remote", "add", remote, f"https://github.com/{mirror}.git")
    allowed = {
        (prefix + mirror + suffix + "\n").encode("ascii").lower()
        for prefix in (
            "https://github.com/", "https://github.com:443/",
            "git@github.com:", "ssh://git@github.com/",
            "ssh://git@github.com:22/",
        )
        for suffix in ("", ".git")
    }
    for direction, options in (("fetch", []), ("push", ["--push"])):
        effective = run_bytes(
            ["git", "remote", "get-url", *options, "--all", remote], cwd=stage
        )
        # Exact byte matching also rejects multiple destinations and embedded
        # newlines. Never expose rewritten URLs, which may contain credentials.
        if effective.lower() not in allowed:
            abort(
                f"effective Git {direction} URL does not match the verified GitHub "
                "repository; inspect Git URL rewrite and remote configuration"
            )
    return remote


def remote_refs(repo: Path, remote_url: str) -> dict[str, str]:
    result = run(["git", "ls-remote", remote_url], cwd=repo)
    refs: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if not line:
            continue
        object_id, refname = line.split("\t", 1)
        if refname.endswith("^{}"):
            continue
        refs[refname] = object_id
    return refs


def is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    result = run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repo,
        check=False,
    )
    if result.returncode not in {0, 1}:
        abort(result.stderr.strip() or "git merge-base failed")
    return result.returncode == 0


def push_ref(repo: Path, remote_url: str, object_id: str, destination: str) -> None:
    run(["git", "push", "--porcelain", remote_url, f"{object_id}:{destination}"], cwd=repo)


def publish_branch(
    repo: Path,
    remote_url: str,
    remote: dict[str, str],
    branch: str,
    object_id: str,
    run_id: str,
) -> str:
    desired = f"refs/heads/{branch}"
    existing = remote.get(desired)
    if existing == object_id:
        return desired
    if existing is None or is_ancestor(repo, existing, object_id):
        push_ref(repo, remote_url, object_id, desired)
        remote[desired] = object_id
        return desired
    archival = f"refs/heads/archive/{ref_slug(branch)}/{run_id}"
    if archival in remote:
        abort(f"archival branch collision: {archival}")
    push_ref(repo, remote_url, object_id, archival)
    remote[archival] = object_id
    return archival


def publish_tag(
    repo: Path,
    remote_url: str,
    remote: dict[str, str],
    tag: str,
    object_id: str,
    run_id: str,
) -> str:
    desired = f"refs/tags/{tag}"
    existing = remote.get(desired)
    if existing == object_id:
        return desired
    if existing is None:
        push_ref(repo, remote_url, object_id, desired)
        remote[desired] = object_id
        return desired
    archival = f"refs/tags/archive/{ref_slug(tag)}/{run_id}"
    if archival in remote:
        abort(f"archival tag collision: {archival}")
    push_ref(repo, remote_url, object_id, archival)
    remote[archival] = object_id
    return archival


def publish_backup(
    stage: Path,
    mirror: str,
    staging: dict[str, Any],
    run_id: str,
    *,
    marker: str,
) -> dict[str, Any]:
    validate_mirror_info(mirror, marker, github_repo_info(mirror))
    upload_remote = verified_upload_remote(stage, mirror, run_id)
    remote = remote_refs(stage, upload_remote)
    if remote:
        run(
            [
                "git",
                "fetch",
                "--quiet",
                "--no-tags",
                upload_remote,
                "+refs/heads/*:refs/remotes/private-review/*",
            ],
            cwd=stage,
        )
        run(
            [
                "git",
                "fetch",
                "--quiet",
                upload_remote,
                "+refs/tags/*:refs/private-review/tags/*",
            ],
            cwd=stage,
        )
    branch_destinations: dict[str, str] = {}
    for refname, object_id in sorted(staging["branches"].items()):
        branch = refname.removeprefix("refs/heads/")
        branch_destinations[branch] = publish_branch(
            stage, upload_remote, remote, branch, object_id, run_id
        )

    tag_destinations: dict[str, str] = {}
    for refname, object_id in sorted(staging["tags"].items()):
        tag = refname.removeprefix("refs/tags/")
        tag_destinations[tag] = publish_tag(
            stage, upload_remote, remote, tag, object_id, run_id
        )

    if staging["dirty"] or staging["source_branch"] is None:
        review_destination = publish_branch(
            stage,
            upload_remote,
            remote,
            staging["review_ref"],
            staging["review_commit"],
            run_id,
        )
    else:
        review_destination = branch_destinations[staging["source_branch"]]

    review_branch = review_destination.removeprefix("refs/heads/")
    github("api", "--method", "PATCH", f"repos/{mirror}", "-f", f"default_branch={review_branch}")
    info = validate_mirror_info(mirror, marker, github_repo_info(mirror))
    if info.get("default_branch") != review_branch:
        abort("GitHub default branch verification failed")
    remote_commit = github(
        "api", f"repos/{mirror}/git/ref/heads/{review_branch}", "--jq", ".object.sha"
    ).stdout.strip()
    if remote_commit != staging["review_commit"]:
        abort(
            f"GitHub review branch SHA mismatch: expected {staging['review_commit']}, got {remote_commit}"
        )
    return {
        "branch_destinations": branch_destinations,
        "tag_destinations": tag_destinations,
        "review_branch": review_branch,
        "review_commit": remote_commit,
        "mirror_private": True,
        "mirror_url": info.get("html_url", f"https://github.com/{mirror}"),
    }


def append_event(run_dir: Path, value: dict[str, Any]) -> None:
    path = run_dir / "browser-events.jsonl"
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        with os.fdopen(descriptor, "ab") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        path.chmod(0o600)


def managed_run_dir(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    marker = path / ".managed-private-github-pro-review"
    if not path.is_dir() or not marker.is_file():
        abort(f"not a managed review run directory: {path}")
    return path


def load_run(run_dir: Path) -> dict[str, Any]:
    return read_json(run_dir / "run.json")


def save_run(run_dir: Path, value: dict[str, Any]) -> None:
    value["updated_at"] = utc_now()
    write_json(run_dir / "run.json", value)


def run_holds_source(state: dict[str, Any]) -> bool:
    # A warning also can land after Send but before its saved URL was recorded.
    # Only observed end/collection can release that uncertain submission window.
    return state.get("status") in ACTIVE_STATUSES or state.get("status") == "blocked"


def next_action(state: dict[str, Any]) -> str:
    status = state.get("status")
    if status == "preparing":
        return "wait-for-publisher-or-end-interrupted-upload"
    if status == "uploaded":
        return "prepare-review"
    if status == "prepared":
        return "archive-dry-run-before-upload"
    if status in {"published", "source-index-pending", "source-bound"}:
        return "continue-same-draft"
    if status == "composer-ready":
        return "inspect-owned-tab-before-send; never-resend-if-already-sent"
    if status in {"submitted", "waiting", "pending", "reconnecting"}:
        return "resume-saved-conversation; complete-and-collect-or-end-after-it-stops"
    if status == "completed":
        return "collect"
    if status == "blocked":
        return "inspect-owned-tab; end-after-confirming-review-stopped-or-was-not-submitted"
    return "start-next-review-if-requested"


def displayed_run(state: dict[str, Any]) -> dict[str, Any]:
    result = dict(state)
    result["legacy_unverified"] = int(result.get("version", 1)) < RUN_VERSION
    result["next_action"] = next_action(state)
    return result


def require_current_run(state: dict[str, Any], operation: str) -> None:
    if int(state.get("version", 1)) < RUN_VERSION:
        abort(
            f"{operation} is unavailable for legacy runs; they remain readable "
            "but cannot acquire v3 evidence"
        )


def state_root_for_run(run_dir: Path) -> Path:
    if run_dir.parent.name != "runs":
        abort(f"managed run is not under a runs directory: {run_dir}")
    return run_dir.parent.parent


def active_runs_for_source(
    state_root: Path,
    source: Path,
    *,
    excluding: Iterable[str] = (),
) -> list[dict[str, Any]]:
    excluded = set(excluding)
    runs_dir = state_root / "runs"
    if not runs_dir.is_dir():
        return []
    source_value = str(source.resolve())
    active: list[dict[str, Any]] = []
    for path in sorted(runs_dir.iterdir()):
        if not path.is_dir() or not (path / ".managed-private-github-pro-review").is_file():
            continue
        state = load_run(path)
        if state.get("run_id") in excluded:
            continue
        if not run_holds_source(state):
            continue
        recorded = Path(str(state.get("source_repo", ""))).expanduser().resolve()
        if str(recorded) == source_value:
            active.append(state)
    return active


def require_no_active_run(
    state_root: Path,
    source: Path,
    *,
    excluding: Iterable[str] = (),
) -> None:
    active = active_runs_for_source(state_root, source, excluding=excluding)
    if active:
        details = ", ".join(
            f"{item.get('run_id')}:{item.get('status')}" for item in active
        )
        abort(
            "an active review run already exists for this source repository: "
            + details
        )


def verify_prompt_snapshot(run_dir: Path, state: dict[str, Any]) -> dict[str, Any]:
    prompt_path = run_dir / "prompt.txt"
    if prompt_path.is_symlink() or not prompt_path.is_file():
        abort(f"frozen prompt is not a regular non-symlink file: {prompt_path}")
    data = prompt_path.read_bytes()
    observed = {"sha256": sha256_bytes(data), "bytes": len(data)}
    expected = {
        "sha256": state.get("prompt_sha256"),
        "bytes": state.get("prompt_bytes"),
    }
    if observed != expected:
        abort(f"frozen prompt byte drift: expected {expected}, got {observed}")
    if state.get("review_input_version") == 1:
        request_path = run_dir / "request.txt"
        if request_path.is_symlink() or not request_path.is_file():
            abort("original request is not a regular non-symlink file")
        request = request_path.read_bytes()
        if (sha256_bytes(request), len(request)) != (
            state.get("request_sha256"), state.get("request_bytes")
        ):
            abort("original request byte drift")
        if compose_review_prompt(request, str(state.get("mirror")), str(state.get("binding"))) != data:
            abort("frozen prompt is not the verified URL plus unchanged original request")
    return observed


def verify_uploaded_identity(run_dir: Path, state: dict[str, Any]) -> dict[str, Any]:
    manifest_path = run_dir / "source-manifest.json"
    published_path = run_dir / "publish-result.json"
    if not manifest_path.is_file() or not published_path.is_file():
        abort("published identity requires source-manifest.json and publish-result.json")
    manifest = read_json(manifest_path)
    published = read_json(published_path)
    if published.get("status") not in {"uploaded", "published"} or published.get("mirror_private") is not True:
        abort("published identity requires a verified private publication")
    checks = (
        ("run_id", state.get("run_id"), manifest.get("run_id")),
        ("run_id", state.get("run_id"), published.get("run_id")),
        ("source_repo", state.get("source_repo"), manifest.get("source_repo")),
        ("source_repo", state.get("source_repo"), published.get("source_repo")),
        ("review_commit", state.get("review_commit"), manifest.get("review_commit")),
        ("review_commit", state.get("review_commit"), published.get("review_commit")),
        ("mirror", state.get("mirror"), published.get("mirror")),
        ("review_branch", state.get("review_branch"), published.get("review_branch")),
        (
            "github_cli_owner",
            (state.get("github_cli_auth") or {}).get("owner"),
            (published.get("github_cli_auth") or {}).get("owner"),
        ),
    )
    for key, expected, actual in checks:
        if expected in {None, ""} or actual != expected:
            abort(
                f"published identity drift for {key}: expected {expected!r}, got {actual!r}"
            )
    return {
        "mirror": state["mirror"],
        "default_branch": state["review_branch"],
        "review_commit": state["review_commit"],
    }


def verify_published_identity(run_dir: Path, state: dict[str, Any]) -> dict[str, Any]:
    identity = verify_uploaded_identity(run_dir, state)
    verify_prompt_snapshot(run_dir, state)
    if state.get("review_input_version") == 1:
        receipt = read_json(run_dir / "review-input.json")
        fields = ("run_id", "mode", "binding", "prompt_sha256", "prompt_bytes",
                  "request_sha256", "request_bytes", "mirror", "review_commit")
        documents = (receipt,)
    else:
        fields = ("binding", "prompt_sha256", "prompt_bytes")
        documents = (read_json(run_dir / "source-manifest.json"),
                     read_json(run_dir / "publish-result.json"))
    for document in documents:
        for key in fields:
            expected = state.get(key)
            if expected in {None, ""} or document.get(key) != expected:
                abort(f"published identity drift for {key}")
    return identity


def verify_remote_review_commit(
    run_dir: Path, state: dict[str, Any], *, require_prompt: bool = True
) -> dict[str, Any]:
    identity = (verify_published_identity if require_prompt else verify_uploaded_identity)(run_dir, state)
    mirror = str(identity["mirror"])
    expected_owner = mirror.split("/", 1)[0]
    stored_cli = state.get("github_cli_auth") or {}
    if (
        stored_cli.get("status") != "verified"
        or str(stored_cli.get("owner", "")).casefold() != expected_owner.casefold()
    ):
        abort("published GitHub CLI authentication evidence is missing or mismatched")
    owner = active_github_owner()
    if owner.casefold() != expected_owner.casefold():
        abort(
            f"active GitHub CLI account drift: expected {expected_owner}, got {owner}"
        )
    expected_marker = DESCRIPTION_PREFIX + project_key(
        Path(str(state.get("source_repo"))).expanduser().resolve()
    )
    info = validate_mirror_info(mirror, expected_marker, github_repo_info(mirror))
    if info.get("default_branch") != identity["default_branch"]:
        abort(
            "remote review default branch drift: expected "
            f"{identity['default_branch']}, got {info.get('default_branch')}"
        )
    remote_commit = github(
        "api", f"repos/{mirror}/git/ref/heads/{identity['default_branch']}", "--jq", ".object.sha"
    ).stdout.strip()
    if remote_commit != identity["review_commit"]:
        abort(
            "remote review commit drift: expected "
            f"{identity['review_commit']}, got {remote_commit}"
        )
    evidence = {
        **identity,
        "github_cli_owner": owner,
        "verified_at": utc_now(),
    }
    evidence["evidence_sha256"] = canonical_json_sha256(evidence)
    return evidence


def binding_assurance(binding: str, *, source_bound: bool) -> str:
    if binding == "raw-url":
        return RAW_URL_ASSURANCE
    return SOURCE_CHIP_BOUND_ASSURANCE if source_bound else SOURCE_CHIP_PENDING_ASSURANCE


def open_owned_tab(state: dict[str, Any], tab_id: str | None) -> dict[str, Any]:
    if not tab_id:
        abort("a run-owned browser tab ID is required")
    tab = state.get("owned_tabs", {}).get(tab_id)
    if not tab:
        abort(f"browser tab is not owned by this run: {tab_id}")
    if tab.get("closed_at"):
        abort(f"browser tab is already closed: {tab_id}")
    return tab


def require_active_owned_tab(state: dict[str, Any], tab_id: str | None) -> dict[str, Any]:
    tab = open_owned_tab(state, tab_id)
    if state.get("active_tab_id") != tab_id:
        abort(f"browser tab is not the active run-owned tab: {tab_id}")
    return tab


def expected_deep_research(mode: str) -> str:
    return "active" if mode == "review" else "inactive"


def validate_source_evidence(
    run_dir: Path, state: dict[str, Any], args: argparse.Namespace
) -> dict[str, Any]:
    if args.capability_label != "Pro":
        abort("source-bound requires the visible capability label to be exactly Pro")
    expected_research = expected_deep_research(str(state.get("mode")))
    if args.deep_research != expected_research:
        abort(
            f"mode {state.get('mode')} requires Deep Research {expected_research}, "
            f"got {args.deep_research}"
        )
    if args.app_grant != "verified":
        abort("source-bound requires a verified ChatGPT GitHub App grant")
    expected = {
        "binding": state.get("binding"),
        "repository": state.get("mirror"),
        "default_branch": state.get("review_branch"),
        "commit": state.get("review_commit"),
    }
    actual = {
        "binding": args.binding,
        "repository": args.repository,
        "default_branch": args.default_branch,
        "commit": args.commit,
    }
    for key, expected_value in expected.items():
        if not expected_value or actual[key] != expected_value:
            abort(
                f"source-bound {key} mismatch: expected {expected_value!r}, "
                f"got {actual[key]!r}"
            )
    tab = require_active_owned_tab(state, args.tab_id)
    if not str(tab.get("kind", "")).startswith("chatgpt-"):
        abort("source-bound requires an active run-owned ChatGPT tab")
    verify_published_identity(run_dir, state)
    remote_evidence = verify_remote_review_commit(run_dir, state)
    return {
        "capability_label": args.capability_label,
        "deep_research": args.deep_research,
        "app_grant": args.app_grant,
        **actual,
        "tab_id": args.tab_id,
        "binding_assurance": binding_assurance(str(state.get("binding")), source_bound=True),
        "review_commit_verification": remote_evidence,
    }


def create_run(
    state_root: Path,
    source: Path,
    mode: str | None,
    prompt: bytes | None,
    run_id: str,
    binding: str | None = "source-chip",
) -> Path:
    source = source.resolve()
    ensure_private_directory(state_root)
    runs = state_root / "runs"
    ensure_private_directory(runs)
    run_dir = runs / run_id
    if run_dir.exists():
        abort(f"run directory collision: {run_dir}")
    ensure_private_directory(run_dir)
    if prompt is not None:
        atomic_write(run_dir / "prompt.txt", prompt)
    now = utc_now()
    write_json(
        run_dir / "run.json",
        {
            "version": RUN_VERSION,
            "run_id": run_id,
            "source_repo": str(source),
            "mode": mode,
            "binding": binding,
            "prompt_sha256": sha256_bytes(prompt) if prompt is not None else None,
            "prompt_bytes": len(prompt) if prompt is not None else None,
            "binding_assurance": binding_assurance(binding, source_bound=False) if binding else None,
            "github_cli_auth": {"status": "unverified"},
            "github_app_auth": {"status": "unverified"},
            "status": "preparing",
            "conversation_url": None,
            "owned_tabs": {},
            "active_tab_id": None,
            "wait_count": 0,
            "reconnect_count": 0,
            "active_wait": None,
            "created_at": now,
            "updated_at": now,
        },
    )
    atomic_write(
        run_dir / ".managed-private-github-pro-review",
        f"version={RUN_VERSION}\n".encode("ascii"),
    )
    return run_dir


def command_publish(args: argparse.Namespace) -> None:
    with ExitStack() as execution:
        publish_with_lease(args, execution)


def publish_with_lease(args: argparse.Namespace, execution: ExitStack) -> None:
    source = repository_root(args.repo)
    if bool(args.prompt_file) != bool(args.mode):
        abort("provide both --mode and --prompt-file, or omit both and use prepare-review after upload")
    prompt = read_prompt(args.prompt_file) if args.prompt_file else None
    binding = (getattr(args, "binding", None) or "source-chip") if prompt is not None else None
    if prompt is None and getattr(args, "binding", None):
        abort("choose --binding in prepare-review after upload")
    state_root = Path(args.state_root).expanduser().resolve()
    run_id = make_run_id(source)
    with state_transaction(state_root):
        active = active_runs_for_source(state_root, source)
        if active and prompt is None:
            if args.mirror and any(item.get("mirror") and item["mirror"] != args.mirror for item in active):
                abort("requested mirror differs from the active project's mirror")
            result = {"status": "resume-required", "upload_performed": False, "source_repo": str(source), "runs": [
                {**displayed_run(item), "run_dir": str(state_root / "runs" / item["run_id"])}
                for item in active
            ]}
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return
        require_no_active_run(state_root, source)
        run_dir = create_run(state_root, source, args.mode, prompt, run_id, binding)
        execution.enter_context(upload_execution(run_dir))
        run_state = load_run(run_dir)
        run_state["publisher_lock"] = "flock-v1"
        save_run(run_dir, run_state)
    allowed = {PurePosixPath(item).as_posix().lstrip("/") for item in args.allow_sensitive_path}

    try:
        with tempfile.TemporaryDirectory(prefix=f"{MANAGER}-{run_id}-", dir="/private/tmp") as temporary:
            staging = prepare_staging_repository(
                source,
                args.include_working_tree,
                run_id,
                Path(temporary),
                committed_only=getattr(args, "committed_only", False),
            )
            payload = validate_backup_payload(
                staging["stage"], staging["review_commit"], allowed
            )
            source_manifest = {
                "version": RUN_VERSION,
                "run_id": run_id,
                "source_repo": str(source),
                "source_head": staging["source_head"],
                "source_head_tree": staging["source_head_tree"],
                "source_branch": staging["source_branch"],
                "working_tree_included": staging["dirty"],
                "source_dirty": staging["source_dirty"],
                "untracked_included": staging["untracked"] if staging["dirty"] else [],
                "untracked_excluded": [] if staging["dirty"] else staging["untracked"],
                "ignored_excluded": staging["ignored"],
                "review_commit": staging["review_commit"],
                "binding": binding,
                "prompt_sha256": sha256_bytes(prompt) if prompt is not None else None,
                "prompt_bytes": len(prompt) if prompt is not None else None,
                "local_branches": staging["branches"],
                "local_tags": staging["tags"],
                "payload": payload,
            }
            write_json(run_dir / "source-manifest.json", source_manifest)

            owner = active_github_owner()
            cli_auth = {
                "status": "verified",
                "owner": owner,
                "verified_at": utc_now(),
                "scope": "GitHub CLI upload and readback only",
            }
            projects = load_project_map(state_root)
            path_key = str(source)
            existing_mapping = projects.get("projects", {}).get(path_key)
            mirror = resolve_mirror(owner, source, args.mirror, existing_mapping)
            mirror_owner, _ = mirror_identity(mirror)
            if mirror_owner.casefold() != owner.casefold():
                abort(f"mirror must belong to the active GitHub account {owner}: {mirror}")
            raw_repository_url = None
            if binding == "raw-url":
                raw_repository_url = require_raw_repository_url(prompt, mirror)
            marker = DESCRIPTION_PREFIX + project_key(source)

            if args.dry_run:
                result = {
                    "status": "prepared",
                    "run_id": run_id,
                    "run_dir": str(run_dir),
                    "source_repo": str(source),
                    "mirror": mirror,
                    "mirror_private": None,
                    "review_commit": staging["review_commit"],
                    "review_branch": staging["review_ref"],
                    "binding": binding,
                    "binding_assurance": binding_assurance(binding, source_bound=False) if binding else None,
                    "raw_repository_url": raw_repository_url,
                    "prompt_sha256": sha256_bytes(prompt) if prompt is not None else None,
                    "prompt_bytes": len(prompt) if prompt is not None else None,
                    "github_cli_auth": cli_auth,
                    "github_app_auth": {"status": "unverified"},
                }
            else:
                # Reserve the destination before the first remote side effect;
                # a hard interruption can have created or partly uploaded it.
                run_state = load_run(run_dir)
                run_state.update({"mirror": mirror, "github_cli_auth": cli_auth,
                                  "review_commit": staging["review_commit"]})
                save_run(run_dir, run_state)
                with state_transaction(state_root):
                    projects = load_project_map(state_root)
                    projects.setdefault("projects", {})[path_key] = {
                        "mirror": mirror, "project_key": project_key(source),
                        "updated_at": utc_now(),
                    }
                    save_project_map(state_root, projects)
                _, created = ensure_private_mirror(mirror, marker)
                published = publish_backup(staging["stage"], mirror, staging, run_id, marker=marker)
                result = {
                    "status": "published" if prompt is not None else "uploaded",
                    "run_id": run_id,
                    "run_dir": str(run_dir),
                    "source_repo": str(source),
                    "mirror": mirror,
                    "mirror_created": created,
                    "binding": binding,
                    "binding_assurance": binding_assurance(binding, source_bound=False) if binding else None,
                    "raw_repository_url": raw_repository_url,
                    "prompt_sha256": sha256_bytes(prompt) if prompt is not None else None,
                    "prompt_bytes": len(prompt) if prompt is not None else None,
                    "github_cli_auth": cli_auth,
                    "github_app_auth": {"status": "unverified"},
                    **published,
                }

            run_state = load_run(run_dir)
            run_state.update(result)
            write_json(run_dir / "publish-result.json", result)
            save_run(run_dir, run_state)
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    except Exception as exc:
        run_state = load_run(run_dir)
        run_state["status"] = "failed"
        run_state["error"] = str(exc)
        save_run(run_dir, run_state)
        raise


def compose_review_prompt(request: bytes, mirror: str, binding: str) -> bytes:
    url = f"https://github.com/{mirror}".encode("ascii")
    if binding == "source-chip":
        return request
    try:
        require_raw_repository_url(request, mirror)
        return request
    except ReviewError:
        return url + b"\n\n" + request


def command_prepare_review(args: argparse.Namespace) -> None:
    run_dir = managed_run_dir(args.run_dir)
    with state_transaction(state_root_for_run(run_dir)):
        state = load_run(run_dir)
        require_current_run(state, "prepare-review")
        if state.get("status") != "uploaded":
            abort(f"prepare-review requires uploaded, got {state.get('status')}; resume this run instead")
        verify_remote_review_commit(run_dir, state, require_prompt=False)
        request = read_prompt(args.prompt_file)
        prompt = compose_review_prompt(request, state["mirror"], args.binding)
        receipt = {
            "review_input_version": 1, "run_id": state["run_id"],
            "mode": args.mode, "binding": args.binding,
            "mirror": state["mirror"], "review_commit": state["review_commit"],
            "request_sha256": sha256_bytes(request), "request_bytes": len(request),
            "prompt_sha256": sha256_bytes(prompt), "prompt_bytes": len(prompt),
        }
        atomic_write(run_dir / "request.txt", request)
        atomic_write(run_dir / "prompt.txt", prompt)
        write_json(run_dir / "review-input.json", receipt)
        state.update(receipt)
        state.update({
            "status": "published",
            "binding_assurance": binding_assurance(args.binding, source_bound=False),
            "raw_repository_url": f"https://github.com/{state['mirror']}" if args.binding == "raw-url" else None,
        })
        verify_published_identity(run_dir, state)
        save_run(run_dir, state)
    print(json.dumps(displayed_run(state), ensure_ascii=False, indent=2, sort_keys=True))


def locked_run_command(function):
    @wraps(function)
    def command(args: argparse.Namespace) -> None:
        run_dir = managed_run_dir(args.run_dir)
        with state_transaction(state_root_for_run(run_dir)):
            function(args)
    return command


@locked_run_command
def command_event(args: argparse.Namespace) -> None:
    run_dir = managed_run_dir(args.run_dir)
    state = load_run(run_dir)
    status = state.get("status")
    event = args.event
    version = int(state.get("version", 1))
    evidence: dict[str, Any] | None = None
    if version < RUN_VERSION and event != "warning":
        abort(
            "legacy runs are read-only under the strict v3 evidence contract; "
            "record warning to block and archive the run"
        )
    if version >= RUN_VERSION and event != "warning":
        verify_prompt_snapshot(run_dir, state)

    if event == "source-index-pending":
        require_current_run(state, event)
        if status != "published":
            abort(f"source-index-pending requires published, got {status}")
        if state.get("binding") != "source-chip" or args.binding != "source-chip":
            abort("source-index-pending is valid only for source-chip binding")
        if args.app_grant != "verified":
            abort("source-index-pending requires a verified ChatGPT GitHub App grant")
        expected = (
            state.get("mirror"),
            state.get("review_branch"),
            state.get("review_commit"),
        )
        actual = (args.repository, args.default_branch, args.commit)
        if actual != expected:
            abort(f"source-index-pending source mismatch: expected {expected}, got {actual}")
        require_active_owned_tab(state, args.tab_id)
        verify_published_identity(run_dir, state)
        remote_evidence = verify_remote_review_commit(run_dir, state)
        evidence = {
            "app_grant": args.app_grant,
            "binding": args.binding,
            "repository": args.repository,
            "default_branch": args.default_branch,
            "commit": args.commit,
            "tab_id": args.tab_id,
            "review_commit_verification": remote_evidence,
        }
        state["review_commit_verification"] = remote_evidence
        state["github_app_auth"] = {
            "status": "verified",
            "evidence_scope": "ChatGPT GitHub App grant only",
            "recorded_at": utc_now(),
            "tab_id": args.tab_id,
        }
        state["source_index"] = "pending"
        state["status"] = "source-index-pending"
    elif event == "source-bound":
        if status != "published":
            if version < RUN_VERSION or status != "source-index-pending":
                abort(f"source-bound requires published or source-index-pending, got {status}")
        if version >= RUN_VERSION:
            evidence = validate_source_evidence(run_dir, state, args)
            state["source_evidence"] = evidence
            state["review_commit_verification"] = evidence[
                "review_commit_verification"
            ]
            state["github_app_auth"] = {
                "status": "verified",
                "evidence_scope": "ChatGPT GitHub App grant only",
                "recorded_at": utc_now(),
                "tab_id": args.tab_id,
            }
            state["binding_assurance"] = evidence["binding_assurance"]
            state["source_index"] = (
                "ready" if state.get("binding") == "source-chip" else "not-applicable"
            )
        state["status"] = "source-bound"
    elif event == "composer-ready":
        require_current_run(state, event)
        if status != "source-bound":
            abort(f"composer-ready requires source-bound, got {status}")
        if args.prompt_sha256 != state.get("prompt_sha256"):
            abort(
                "composer-ready prompt SHA-256 mismatch: "
                f"expected {state.get('prompt_sha256')}, got {args.prompt_sha256}"
            )
        if args.fill_method != "single-operation":
            abort("composer-ready requires one single-operation composer fill")
        require_active_owned_tab(state, args.tab_id)
        evidence = {
            "prompt_sha256": args.prompt_sha256,
            "fill_method": args.fill_method,
            "tab_id": args.tab_id,
        }
        state["composer_evidence"] = evidence
        state["status"] = "composer-ready"
    elif event == "submitted":
        required = "source-bound" if version < RUN_VERSION else "composer-ready"
        if status != required:
            abort(f"submitted requires {required}, got {status}")
        if not args.conversation_url or not CHATGPT_CONVERSATION_RE.match(
            args.conversation_url
        ):
            abort("submitted requires a durable https://chatgpt.com/ conversation URL")
        if version >= RUN_VERSION:
            if args.submission_method != "send-button":
                abort("submitted requires submission-method=send-button; Enter is forbidden")
            tab = require_active_owned_tab(state, args.tab_id)
            tab["kind"] = "chatgpt-conversation"
            tab["url"] = args.conversation_url
            tab["saved"] = True
            evidence = {
                "submission_method": args.submission_method,
                "conversation_url": args.conversation_url,
                "tab_id": args.tab_id,
            }
            state["submission_evidence"] = evidence
        state["conversation_url"] = args.conversation_url
        state["status"] = "submitted"
    elif event == "wait-start":
        if status not in {"submitted", "reconnecting"}:
            abort(f"wait-start requires submitted or reconnecting, got {status}")
        if int(state.get("wait_count", 0)) >= 2:
            abort("a third browser wait is forbidden")
        if version >= RUN_VERSION:
            tab = require_active_owned_tab(state, args.tab_id)
            if tab.get("kind") != "chatgpt-conversation" or tab.get("url") != state.get(
                "conversation_url"
            ):
                abort("wait-start requires the active saved conversation tab")
            sentinel = str(args.generation_sentinel or "").strip()
            if not sentinel or len(sentinel) > 512:
                abort("wait-start requires a bounded non-empty generation sentinel")
        state["wait_count"] = int(state.get("wait_count", 0)) + 1
        if version >= RUN_VERSION:
            evidence = {
                "wait_sequence": state["wait_count"],
                "generation_sentinel": sentinel,
                "tab_id": args.tab_id,
                "conversation_url": state.get("conversation_url"),
                "started_at": utc_now(),
            }
            state["active_wait"] = evidence
        state["status"] = "waiting"
    elif event == "wait-complete":
        if status not in {"waiting", "pending"}:
            abort(f"wait-complete requires waiting or pending, got {status}")
        if version >= RUN_VERSION:
            active_wait = state.get("active_wait" if status == "waiting" else "last_incomplete_wait")
            if not isinstance(active_wait, dict):
                abort("wait-complete requires recorded active wait evidence")
            if args.completion_proof != COMPLETION_PROOF:
                abort(
                    "wait-complete requires completion proof that the recorded "
                    "generation sentinel is absent and the final container is present"
                )
            if args.generation_sentinel != active_wait.get("generation_sentinel"):
                abort(
                    "wait-complete generation sentinel mismatch: expected "
                    f"{active_wait.get('generation_sentinel')!r}, "
                    f"got {args.generation_sentinel!r}"
                )
            expected_container = (
                "deep-research-report" if state.get("mode") == "review" else "assistant-turn"
            )
            if args.final_container != expected_container:
                abort(
                    "wait-complete final container mismatch: expected "
                    f"{expected_container}, got {args.final_container}"
                )
            tab = require_active_owned_tab(state, args.tab_id)
            same_tab = args.tab_id == active_wait.get("tab_id")
            old_tab = state.get("owned_tabs", {}).get(active_wait.get("tab_id"), {})
            replacement = (
                status == "pending" and old_tab.get("closed_at")
                and old_tab.get("close_reason") == "disconnected"
                and old_tab.get("url") == state.get("conversation_url")
            )
            if (
                not (same_tab or replacement)
                or tab.get("kind") != "chatgpt-conversation"
                or tab.get("url") != state.get("conversation_url")
                or active_wait.get("conversation_url") != state.get("conversation_url")
            ):
                abort("wait-complete requires the same active saved conversation tab or its recorded disconnected replacement")
            evidence = {
                "wait_sequence": active_wait.get("wait_sequence"),
                "wait_tab_id": active_wait.get("tab_id"),
                "generation_sentinel": args.generation_sentinel,
                "completion_proof": args.completion_proof,
                "final_container": args.final_container,
                "tab_id": args.tab_id,
                "conversation_url": state.get("conversation_url"),
                "observed_at": utc_now(),
            }
            state["completion_evidence"] = evidence
            state["active_wait"] = None
        state["status"] = "completed"
    elif event == "pending":
        if status != "waiting":
            abort(f"pending requires waiting, got {status}")
        if version >= RUN_VERSION:
            state["last_incomplete_wait"] = state.get("active_wait")
            state["active_wait"] = None
        state["status"] = "pending"
    elif event == "reconnect":
        if status != "pending":
            abort(f"reconnect requires pending, got {status}")
        if int(state.get("reconnect_count", 0)) >= 1:
            abort("a second browser reconnect is forbidden")
        if int(state.get("wait_count", 0)) >= 2:
            abort("the browser wait budget is exhausted")
        if version >= RUN_VERSION:
            tab = require_active_owned_tab(state, args.tab_id)
            if tab.get("kind") != "chatgpt-conversation" or tab.get("url") != state.get(
                "conversation_url"
            ):
                abort("reconnect requires the active saved conversation tab")
        state["reconnect_count"] = int(state.get("reconnect_count", 0)) + 1
        state["status"] = "reconnecting"
    elif event == "warning":
        if status in {"preparing", "uploaded", "prepared"}:
            abort("warning requires the browser phase; it cannot release a publisher")
        if status in {"collected", "blocked", "failed", "superseded", "archived", "ended"}:
            abort(f"warning is invalid after terminal state {status}")
        state["status"] = "blocked"
        state["warning"] = args.message or "browser access-frequency warning"
    else:
        abort(f"unsupported event: {event}")

    event_record = {
        "event": event,
        "status": state["status"],
        "at": utc_now(),
    }
    if args.message:
        event_record["message"] = args.message
    if evidence is not None:
        event_record["evidence"] = evidence
    append_event(run_dir, event_record)
    save_run(run_dir, state)
    print(json.dumps(displayed_run(state), ensure_ascii=False, indent=2, sort_keys=True))


@locked_run_command
def command_tab(args: argparse.Namespace) -> None:
    run_dir = managed_run_dir(args.run_dir)
    state = load_run(run_dir)
    require_current_run(state, "tab ledger")
    if args.action != "close":
        verify_prompt_snapshot(run_dir, state)
    tabs = state.setdefault("owned_tabs", {})
    now = utc_now()
    if not args.tab_id:
        abort("tab ledger requires a non-empty browser tab ID")

    if args.action == "register":
        if args.tab_id in tabs:
            abort(f"browser tab is already registered to this run: {args.tab_id}")
        tabs[args.tab_id] = {
            "tab_id": args.tab_id,
            "kind": args.kind,
            "url": args.url,
            "saved": args.kind == "chatgpt-conversation",
            "registered_at": now,
            "closed_at": None,
        }
    elif args.action == "activate":
        open_owned_tab(state, args.tab_id)
        state["active_tab_id"] = args.tab_id
    elif args.action == "close":
        tab = open_owned_tab(state, args.tab_id)
        if (
            tab.get("kind") == "chatgpt-conversation"
            and state.get("status")
            not in {"collected", "blocked", "failed", "superseded", "ended"}
            and args.reason != "disconnected"
        ):
            abort("the active saved conversation must remain open until the run is terminal")
        tab["closed_at"] = now
        tab["close_reason"] = args.reason
        if state.get("active_tab_id") == args.tab_id:
            state["active_tab_id"] = None
    else:
        abort(f"unsupported tab action: {args.action}")

    append_event(
        run_dir,
        {
            "event": f"tab-{args.action}",
            "status": state.get("status"),
            "tab_id": args.tab_id,
            "reason": args.reason,
            "at": now,
        },
    )
    save_run(run_dir, state)
    print(json.dumps(displayed_run(state), ensure_ascii=False, indent=2, sort_keys=True))


@locked_run_command
def command_supersede(args: argparse.Namespace) -> None:
    old_dir = managed_run_dir(args.run_dir)
    old_state = load_run(old_dir)
    require_current_run(old_state, "supersede")
    verify_prompt_snapshot(old_dir, old_state)
    if old_state.get("status") not in SUPERSEDEABLE_STATUSES:
        abort(
            "supersede requires an unsent run before composer-ready; "
            "use end after checking a ready or blocked run; got "
            f"{old_state.get('status')}"
        )
    if old_state.get("conversation_url"):
        abort("supersede cannot reuse a snapshot after a conversation was submitted")
    prompt = read_prompt(args.prompt_file)
    prompt_hash = sha256_bytes(prompt)
    if (
        old_state.get("mode") == args.mode
        and old_state.get("binding") == args.binding
        and old_state.get("prompt_sha256") == prompt_hash
    ):
        abort("supersede would not change mode, binding, or prompt")
    open_disposable = [
        tab_id
        for tab_id, tab in old_state.get("owned_tabs", {}).items()
        if not tab.get("closed_at")
    ]
    if open_disposable:
        abort(
            "close all abandoned run-owned tabs before superseding: "
            + ", ".join(sorted(open_disposable))
        )

    verify_published_identity(old_dir, old_state)
    manifest = read_json(old_dir / "source-manifest.json")
    published = read_json(old_dir / "publish-result.json")
    if args.binding == "raw-url":
        require_raw_repository_url(prompt, str(published.get("mirror")))

    source = Path(str(old_state.get("source_repo")))
    run_id = make_run_id(source)
    state_root = state_root_for_run(old_dir)
    require_no_active_run(
        state_root, source, excluding={str(old_state.get("run_id"))}
    )
    new_dir = create_run(
        state_root, source, args.mode, prompt, run_id, args.binding
    )
    new_manifest = dict(manifest)
    new_manifest["run_id"] = run_id
    new_manifest["reused_from_run"] = old_state.get("run_id")
    new_manifest["binding"] = args.binding
    new_manifest["prompt_sha256"] = prompt_hash
    new_manifest["prompt_bytes"] = len(prompt)
    write_json(new_dir / "source-manifest.json", new_manifest)
    new_published = dict(published)
    new_published.update(
        {
            "run_id": run_id,
            "run_dir": str(new_dir),
            "status": "published",
            "binding": args.binding,
            "binding_assurance": binding_assurance(args.binding, source_bound=False),
            "raw_repository_url": (
                f"https://github.com/{published.get('mirror')}"
                if args.binding == "raw-url"
                else None
            ),
            "prompt_sha256": prompt_hash,
            "prompt_bytes": len(prompt),
            "github_cli_auth": old_state.get("github_cli_auth"),
            "github_app_auth": {"status": "unverified"},
            "reused_from_run": old_state.get("run_id"),
        }
    )
    write_json(new_dir / "publish-result.json", new_published)
    new_state = load_run(new_dir)
    new_state.update(new_published)
    new_state["supersedes"] = old_state.get("run_id")
    new_state["snapshot_reused"] = True
    save_run(new_dir, new_state)

    old_state["status"] = "superseded"
    old_state["superseded_by"] = run_id
    old_state["supersede_reason"] = args.reason
    append_event(
        old_dir,
        {
            "event": "superseded",
            "status": "superseded",
            "replacement_run_id": run_id,
            "reason": args.reason,
            "at": utc_now(),
        },
    )
    save_run(old_dir, old_state)
    append_event(
        new_dir,
        {
            "event": "snapshot-reused",
            "status": "published",
            "source_run_id": old_state.get("run_id"),
            "at": utc_now(),
        },
    )
    print(json.dumps(displayed_run(new_state), ensure_ascii=False, indent=2, sort_keys=True))


def command_list(args: argparse.Namespace) -> None:
    state_root = Path(args.state_root).expanduser().resolve()
    runs_dir = state_root / "runs"
    results: list[dict[str, Any]] = []
    if runs_dir.is_dir():
        for path in sorted(runs_dir.iterdir()):
            marker = path / ".managed-private-github-pro-review"
            if not path.is_dir() or not marker.is_file():
                continue
            state = displayed_run(load_run(path))
            if args.all or run_holds_source(state):
                results.append(state)
    print(json.dumps({"runs": results}, ensure_ascii=False, indent=2, sort_keys=True))


def command_end(args: argparse.Namespace) -> None:
    run_dir = managed_run_dir(args.run_dir)
    with state_transaction(state_root_for_run(run_dir)), upload_execution(run_dir):
        state = load_run(run_dir)
        if not run_holds_source(state) and state.get("status") != "blocked":
            abort(f"end requires an unfinished run, got {state.get('status')}")
        if not args.reason.strip():
            abort("end requires a non-empty reason")
        if (state.get("status") == "preparing" and state.get("publisher_lock") != "flock-v1"
                and not getattr(args, "publisher_stopped", False)):
            abort("legacy preparing run has no publisher lease; confirm the old publisher and all Git/gh children stopped, then use --publisher-stopped")
        url = state.get("conversation_url")
        if not url and args.conversation_url:
            # Recovery for Send acknowledged by the page but not by the ledger.
            # This records an observed end only, never completion/answer proof.
            if (state.get("status") not in {"composer-ready", "blocked"}
                    or args.observed not in {"finished", "cancelled"}
                    or not CHATGPT_CONVERSATION_RE.fullmatch(args.conversation_url)):
                abort("unrecorded submission requires an observed stopped saved conversation")
            tab = require_active_owned_tab(state, state.get("active_tab_id"))
            if tab.get("kind") != "chatgpt-conversation" or tab.get("url") != args.conversation_url:
                abort("unrecorded submission requires the active owned saved conversation tab")
            url = args.conversation_url
            state["conversation_url"] = url
            state["submission_recovered_for_end_only"] = True
        if url:
            if args.conversation_url != url or args.observed not in {"finished", "cancelled"}:
                abort("end requires the saved conversation URL and an observed finished or cancelled review")
        elif args.observed != "not-submitted" or args.conversation_url:
            abort("end requires confirmation that this run was not submitted")
        evidence = {"observed": args.observed, "conversation_url": url,
                    "publisher_stopped": bool(getattr(args, "publisher_stopped", False)),
                    "reason": args.reason, "at": utc_now()}
        state["ended_from_status"] = state.get("status")
        state["status"] = "ended"
        state["end_evidence"] = evidence
        append_event(run_dir, {"event": "ended", "status": "ended", "evidence": evidence, "at": utc_now()})
        save_run(run_dir, state)
    print(json.dumps(displayed_run(state), ensure_ascii=False, indent=2, sort_keys=True))


@locked_run_command
def command_archive(args: argparse.Namespace) -> None:
    run_dir = managed_run_dir(args.run_dir)
    state = load_run(run_dir)
    status = state.get("status")
    if status == "blocked":
        abort("archive cannot release a blocked review; confirm whether it was sent and use end first")
    if status not in ARCHIVABLE_STATUSES:
        abort(
            "archive is manual and requires prepared, collected, blocked, failed, "
            "or superseded; "
            f"got {status}"
        )
    state["archived_from_status"] = status
    state["status"] = "archived"
    append_event(
        run_dir,
        {"event": "archived", "status": "archived", "at": utc_now()},
    )
    save_run(run_dir, state)
    print(json.dumps(displayed_run(state), ensure_ascii=False, indent=2, sort_keys=True))


@locked_run_command
def command_collect(args: argparse.Namespace) -> None:
    run_dir = managed_run_dir(args.run_dir)
    state = load_run(run_dir)
    require_current_run(state, "collect")
    if state.get("status") != "completed":
        abort(f"collect requires completed, got {state.get('status')}")
    if int(state.get("version", 1)) >= RUN_VERSION:
        verify_prompt_snapshot(run_dir, state)
        completion = state.get("completion_evidence")
        if not isinstance(completion, dict):
            abort("collect requires strict wait-complete evidence")
        if args.source_kind != completion.get("final_container"):
            abort(
                "collect source kind mismatch: expected "
                f"{completion.get('final_container')}, got {args.source_kind}"
            )
        if args.source_conversation_url != state.get("conversation_url"):
            abort(
                "collect conversation URL mismatch: expected "
                f"{state.get('conversation_url')}, got {args.source_conversation_url}"
            )
        if args.source_tab_id != completion.get("tab_id"):
            abort(
                "collect source tab mismatch: expected "
                f"{completion.get('tab_id')}, got {args.source_tab_id}"
            )
        require_active_owned_tab(state, args.source_tab_id)
        if not re.fullmatch(r"[0-9a-f]{64}", str(args.answer_sha256 or "")):
            abort("collect requires a lowercase SHA-256 for the browser extraction")
    source, data = read_regular_file_bytes(
        args.answer_file,
        label="answer file",
        allowed_roots=(Path(tempfile.gettempdir()), Path("/private/tmp")),
    )
    if not data.strip():
        abort("answer is empty")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        abort(f"answer is not UTF-8: {exc}")
    observed_sha256 = sha256_bytes(data)
    if (
        int(state.get("version", 1)) >= RUN_VERSION
        and args.answer_sha256 != observed_sha256
    ):
        abort(
            "answer SHA-256 mismatch: expected "
            f"{args.answer_sha256}, got {observed_sha256}"
        )
    destination = run_dir / "answer.md"
    if destination.exists():
        abort("answer was already collected")
    atomic_write(destination, data)
    state["status"] = "collected"
    state["answer_path"] = str(destination)
    state["answer_sha256"] = observed_sha256
    state["answer_bytes"] = len(data)
    if int(state.get("version", 1)) >= RUN_VERSION:
        state["answer_source"] = {
            "source_kind": args.source_kind,
            "conversation_url": args.source_conversation_url,
            "tab_id": args.source_tab_id,
            "source_path": str(source),
            "claimed_sha256": args.answer_sha256,
            "observed_sha256": observed_sha256,
            "bytes": len(data),
            "assurance": "operator-identified-browser-extract-with-byte-hash-v1",
            "collected_at": utc_now(),
        }
    append_event(
        run_dir,
        {
            "event": "collected",
            "status": "collected",
            "evidence": state.get("answer_source"),
            "at": utc_now(),
        },
    )
    save_run(run_dir, state)
    print(json.dumps(displayed_run(state), ensure_ascii=False, indent=2, sort_keys=True))


def command_show(args: argparse.Namespace) -> None:
    run_dir = managed_run_dir(args.run_dir)
    print(
        json.dumps(
            displayed_run(load_run(run_dir)), ensure_ascii=False, indent=2, sort_keys=True
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="review_repo.py", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    publish = subparsers.add_parser("publish", help="back up a repository and create a review run")
    publish.add_argument("--repo", required=True)
    publish.add_argument("--mode", choices=("review", "pro"))
    publish.add_argument("--prompt-file")
    publish.add_argument("--binding", choices=("source-chip", "raw-url"))
    scope = publish.add_mutually_exclusive_group()
    scope.add_argument("--include-working-tree", action="store_true")
    scope.add_argument("--committed-only", action="store_true")
    publish.add_argument("--mirror")
    publish.add_argument("--allow-sensitive-path", action="append", default=[])
    publish.add_argument("--state-root", default=str(DEFAULT_STATE_ROOT))
    publish.add_argument("--dry-run", action="store_true")
    publish.set_defaults(func=command_publish)

    prepare = subparsers.add_parser("prepare-review", help="freeze the verified repo URL and unchanged review request after upload")
    prepare.add_argument("--run-dir", required=True)
    prepare.add_argument("--mode", choices=("review", "pro"), required=True)
    prepare.add_argument("--prompt-file", required=True)
    prepare.add_argument("--binding", choices=("raw-url", "source-chip"), default="raw-url")
    prepare.set_defaults(func=command_prepare_review)

    end = subparsers.add_parser("end", help="release an unfinished run after observing that its review has stopped")
    end.add_argument("--run-dir", required=True)
    end.add_argument("--observed", choices=("not-submitted", "finished", "cancelled"), required=True)
    end.add_argument("--conversation-url")
    end.add_argument("--reason", required=True)
    end.add_argument("--publisher-stopped", action="store_true",
                     help="legacy preparing runs only: record that the publisher and all upload children have stopped")
    end.set_defaults(func=command_end)

    event = subparsers.add_parser("event", help="record one bounded browser transition")
    event.add_argument("--run-dir", required=True)
    event.add_argument(
        "--event",
        required=True,
        choices=(
            "source-index-pending",
            "source-bound",
            "composer-ready",
            "submitted",
            "wait-start",
            "wait-complete",
            "pending",
            "reconnect",
            "warning",
        ),
    )
    event.add_argument("--conversation-url")
    event.add_argument("--message")
    event.add_argument("--capability-label")
    event.add_argument("--deep-research", choices=("active", "inactive"))
    event.add_argument("--app-grant", choices=("verified", "pending"))
    event.add_argument("--binding", choices=("source-chip", "raw-url"))
    event.add_argument("--repository")
    event.add_argument("--default-branch")
    event.add_argument("--commit")
    event.add_argument("--tab-id")
    event.add_argument("--prompt-sha256")
    event.add_argument("--fill-method", choices=("single-operation", "sequential-typing"))
    event.add_argument("--submission-method", choices=("send-button", "enter"))
    event.add_argument("--generation-sentinel")
    event.add_argument(
        "--completion-proof",
        choices=(COMPLETION_PROOF,),
    )
    event.add_argument(
        "--final-container",
        choices=("assistant-turn", "deep-research-report"),
    )
    event.set_defaults(func=command_event)

    tab = subparsers.add_parser("tab", help="maintain the run-owned browser tab ledger")
    tab.add_argument("--run-dir", required=True)
    tab.add_argument("--action", choices=("register", "activate", "close"), required=True)
    tab.add_argument("--tab-id", required=True)
    tab.add_argument(
        "--kind",
        choices=("chatgpt-draft", "chatgpt-conversation", "github-temporary"),
        default="chatgpt-draft",
    )
    tab.add_argument("--url")
    tab.add_argument("--reason")
    tab.set_defaults(func=command_tab)

    supersede = subparsers.add_parser(
        "supersede", help="reuse one published snapshot for a corrected pre-submission run"
    )
    supersede.add_argument("--run-dir", required=True)
    supersede.add_argument("--mode", choices=("review", "pro"), required=True)
    supersede.add_argument("--prompt-file", required=True)
    supersede.add_argument("--binding", choices=("source-chip", "raw-url"), required=True)
    supersede.add_argument("--reason", required=True)
    supersede.set_defaults(func=command_supersede)

    list_runs = subparsers.add_parser("list", help="list active or all saved runs")
    list_runs.add_argument("--state-root", default=str(DEFAULT_STATE_ROOT))
    list_runs.add_argument("--all", action="store_true")
    list_runs.set_defaults(func=command_list)

    archive = subparsers.add_parser("archive", help="manually archive one terminal run")
    archive.add_argument("--run-dir", required=True)
    archive.set_defaults(func=command_archive)

    collect = subparsers.add_parser("collect", help="save the final targeted answer")
    collect.add_argument("--run-dir", required=True)
    collect.add_argument("--answer-file", required=True)
    collect.add_argument("--answer-sha256")
    collect.add_argument(
        "--source-kind", choices=("assistant-turn", "deep-research-report")
    )
    collect.add_argument("--source-conversation-url")
    collect.add_argument("--source-tab-id")
    collect.set_defaults(func=command_collect)

    show = subparsers.add_parser("show", help="show a saved run without external access")
    show.add_argument("--run-dir", required=True)
    show.set_defaults(func=command_show)
    return parser


def main() -> int:
    os.umask(0o077)
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
        return 0
    except ReviewError as exc:
        print(f"{MANAGER}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
