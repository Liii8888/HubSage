from __future__ import annotations

import importlib.util
import io
import json
import stat
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "review_repo.py"
SPEC = importlib.util.spec_from_file_location("review_repo", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def command(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        list(args),
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def init_repo(path: Path, bare: bool = False) -> None:
    path.mkdir(parents=True)
    args = ["git", "init", "--quiet"]
    if bare:
        args.append("--bare")
    subprocess.run(args, cwd=path, check=True)
    if not bare:
        command("git", "config", "user.name", "Test User", cwd=path)
        command("git", "config", "user.email", "test@example.invalid", cwd=path)


def commit_file(repo: Path, name: str, content: str, message: str) -> str:
    (repo / name).write_text(content, encoding="utf-8")
    command("git", "add", "--", name, cwd=repo)
    command("git", "commit", "--quiet", "-m", message, cwd=repo)
    return command("git", "rev-parse", "HEAD", cwd=repo)


def private_answer(path: Path, content: str = "final answer\n") -> Path:
    # The temporary parent already exists with mode 0700. Create the file with
    # its final permissions before any answer bytes are written.
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


def mirror_metadata(mirror: str, marker: str, **changes: object) -> dict[str, object]:
    owner, name = mirror.split("/")
    return {
        "owner": {"login": owner}, "name": name, "full_name": mirror,
        "html_url": f"https://github.com/{mirror}", "private": True,
        "description": marker, "default_branch": "main", **changes,
    }


class PersistentBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_diverged_branch_is_archived_without_rewriting_remote(self) -> None:
        source = self.root / "source"
        remote = self.root / "remote.git"
        init_repo(source)
        init_repo(remote, bare=True)
        command("git", "branch", "-M", "main", cwd=source)
        first = commit_file(source, "value.txt", "one\n", "one")
        remote_map: dict[str, str] = {}
        destination = MODULE.publish_branch(
            source, str(remote), remote_map, "main", first, "run-one"
        )
        self.assertEqual(destination, "refs/heads/main")
        command(
            "git",
            "--git-dir",
            str(remote),
            "update-ref",
            "refs/heads/remote-only",
            first,
            cwd=self.root,
        )

        second = commit_file(source, "value.txt", "two\n", "two")
        destination = MODULE.publish_branch(
            source, str(remote), remote_map, "main", second, "run-two"
        )
        self.assertEqual(destination, "refs/heads/main")
        self.assertEqual(
            command("git", "--git-dir", str(remote), "rev-parse", "refs/heads/main", cwd=self.root),
            second,
        )

        command("git", "checkout", "--quiet", "--detach", first, cwd=source)
        divergent = commit_file(source, "other.txt", "three\n", "three")
        destination = MODULE.publish_branch(
            source, str(remote), remote_map, "main", divergent, "run-three"
        )
        self.assertEqual(destination, "refs/heads/archive/main/run-three")
        self.assertEqual(
            command("git", "--git-dir", str(remote), "rev-parse", "refs/heads/main", cwd=self.root),
            second,
        )
        self.assertEqual(
            command("git", "--git-dir", str(remote), "rev-parse", destination, cwd=self.root),
            divergent,
        )
        self.assertEqual(
            command(
                "git",
                "--git-dir",
                str(remote),
                "rev-parse",
                "refs/heads/remote-only",
                cwd=self.root,
            ),
            first,
        )

    def test_wip_staging_preserves_source_and_includes_nonignored_files(self) -> None:
        source = self.root / "source"
        init_repo(source)
        command("git", "branch", "-M", "main", cwd=source)
        head = commit_file(source, "tracked.txt", "base\n", "base")
        (source / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
        command("git", "add", ".gitignore", cwd=source)
        command("git", "commit", "--quiet", "-m", "ignore", cwd=source)
        head = command("git", "rev-parse", "HEAD", cwd=source)
        (source / "tracked.txt").write_text("changed\n", encoding="utf-8")
        (source / "new.txt").write_text("new\n", encoding="utf-8")
        (source / "ignored.txt").write_text("ignored\n", encoding="utf-8")
        before = command("git", "status", "--short", cwd=source)

        staging = MODULE.prepare_staging_repository(
            source, True, "run-wip", self.root / "stage"
        )
        self.assertTrue(staging["dirty"])
        self.assertEqual(staging["review_ref"], "review/wip/run-wip")
        self.assertEqual(command("git", "rev-parse", "HEAD", cwd=source), head)
        self.assertEqual(command("git", "status", "--short", cwd=source), before)
        self.assertEqual((staging["stage"] / "tracked.txt").read_text(), "changed\n")
        self.assertEqual((staging["stage"] / "new.txt").read_text(), "new\n")
        self.assertFalse((staging["stage"] / "ignored.txt").exists())
        self.assertEqual(
            command("git", "rev-parse", "HEAD^", cwd=staging["stage"]), head
        )

    def test_wip_staging_preserves_trailing_blank_context_line(self) -> None:
        source = self.root / "source"
        init_repo(source)
        command("git", "branch", "-M", "main", cwd=source)
        head = commit_file(source, "tracked.txt", "alpha\nold\n\n", "base")
        (source / "tracked.txt").write_text("alpha\nnew\n\n", encoding="utf-8")

        staging = MODULE.prepare_staging_repository(
            source, True, "run-trailing-blank", self.root / "stage"
        )

        self.assertEqual(
            (staging["stage"] / "tracked.txt").read_text(encoding="utf-8"),
            "alpha\nnew\n\n",
        )
        self.assertEqual(command("git", "rev-parse", "HEAD^", cwd=staging["stage"]), head)

    def test_payload_rejects_sensitive_path_lfs_and_large_history_blob(self) -> None:
        source = self.root / "source"
        init_repo(source)
        command("git", "branch", "-M", "main", cwd=source)
        commit_file(source, ".env", "TOKEN=value\n", "secret path")
        with self.assertRaisesRegex(MODULE.ReviewError, "credential-like path"):
            MODULE.validate_backup_payload(source, command("git", "rev-parse", "HEAD", cwd=source), set())

        MODULE.validate_backup_payload(
            source,
            command("git", "rev-parse", "HEAD", cwd=source),
            {".env"},
        )
        (source / ".env").unlink()
        (source / "asset.bin").write_text(
            "version https://git-lfs.github.com/spec/v1\n"
            "oid sha256:" + "0" * 64 + "\nsize 123\n",
            encoding="utf-8",
        )
        command("git", "add", "--all", cwd=source)
        command("git", "commit", "--quiet", "-m", "lfs", cwd=source)
        with self.assertRaisesRegex(MODULE.ReviewError, "Git LFS pointer"):
            MODULE.validate_backup_payload(
                source,
                command("git", "rev-parse", "HEAD", cwd=source),
                {".env"},
            )

        original_limit = MODULE.MAX_GITHUB_BLOB_BYTES
        try:
            MODULE.MAX_GITHUB_BLOB_BYTES = 8
            with self.assertRaisesRegex(MODULE.ReviewError, "oversized blob"):
                MODULE.validate_backup_payload(
                    source,
                    command("git", "rev-parse", "HEAD", cwd=source),
                    {".env"},
                )
        finally:
            MODULE.MAX_GITHUB_BLOB_BYTES = original_limit

    def test_conflicting_tag_is_archived(self) -> None:
        source = self.root / "source"
        remote = self.root / "remote.git"
        init_repo(source)
        init_repo(remote, bare=True)
        first = commit_file(source, "value.txt", "one\n", "one")
        command("git", "tag", "release", first, cwd=source)
        remote_map: dict[str, str] = {}
        destination = MODULE.publish_tag(
            source, str(remote), remote_map, "release", first, "run-one"
        )
        self.assertEqual(destination, "refs/tags/release")
        second = commit_file(source, "value.txt", "two\n", "two")
        destination = MODULE.publish_tag(
            source, str(remote), remote_map, "release", second, "run-two"
        )
        self.assertEqual(destination, "refs/tags/archive/release/run-two")
        self.assertEqual(
            command("git", "--git-dir", str(remote), "rev-parse", "refs/tags/release", cwd=self.root),
            first,
        )

    def test_dry_run_copies_prompt_and_records_all_local_refs(self) -> None:
        source = self.root / "source"
        init_repo(source)
        command("git", "branch", "-M", "main", cwd=source)
        head = commit_file(source, "value.txt", "one\n", "one")
        command("git", "branch", "topic", head, cwd=source)
        command("git", "tag", "v1", head, cwd=source)
        prompt = self.root / "prompt.txt"
        prompt_bytes = "逐字提交这个提示。\n".encode("utf-8")
        prompt.write_bytes(prompt_bytes)
        state_root = self.root / "state"
        args = SimpleNamespace(
            repo=str(source),
            mode="review",
            prompt_file=str(prompt),
            binding="source-chip",
            include_working_tree=False,
            mirror="tester/source-backup",
            allow_sensitive_path=[],
            state_root=str(state_root),
            dry_run=True,
        )
        with mock.patch.object(MODULE, "active_github_owner", return_value="tester"):
            with redirect_stdout(io.StringIO()):
                MODULE.command_publish(args)
        run_dirs = list((state_root / "runs").iterdir())
        self.assertEqual(len(run_dirs), 1)
        run_dir = run_dirs[0]
        self.assertEqual((run_dir / "prompt.txt").read_bytes(), prompt_bytes)
        state = MODULE.load_run(run_dir)
        self.assertEqual(state["status"], "prepared")
        self.assertEqual(state["prompt_bytes"], len(prompt_bytes))
        self.assertEqual(state["github_cli_auth"]["status"], "verified")
        self.assertEqual(state["github_cli_auth"]["owner"], "tester")
        self.assertEqual(state["github_app_auth"]["status"], "unverified")
        manifest = MODULE.read_json(run_dir / "source-manifest.json")
        published = MODULE.read_json(run_dir / "publish-result.json")
        for evidence in (manifest, published):
            self.assertEqual(evidence["prompt_sha256"], MODULE.sha256_bytes(prompt_bytes))
            self.assertEqual(evidence["prompt_bytes"], len(prompt_bytes))
        self.assertEqual(
            set(manifest["local_branches"]),
            {"refs/heads/main", "refs/heads/topic"},
        )
        self.assertEqual(set(manifest["local_tags"]), {"refs/tags/v1"})
        self.assertEqual(command("git", "rev-parse", "HEAD", cwd=source), head)

    def test_publish_allows_only_one_active_run_per_source_repository(self) -> None:
        source = self.root / "source"
        init_repo(source)
        commit_file(source, "value.txt", "one\n", "one")
        prompt = self.root / "prompt.txt"
        prompt.write_text("review\n", encoding="utf-8")
        state_root = self.root / "state"
        args = SimpleNamespace(
            repo=str(source),
            mode="review",
            prompt_file=str(prompt),
            binding="source-chip",
            include_working_tree=False,
            mirror="tester/source-backup",
            allow_sensitive_path=[],
            state_root=str(state_root),
            dry_run=True,
        )

        with mock.patch.object(MODULE, "active_github_owner", return_value="tester"):
            with redirect_stdout(io.StringIO()):
                MODULE.command_publish(args)
            with self.assertRaisesRegex(MODULE.ReviewError, "active review run"):
                MODULE.command_publish(args)

        runs = list((state_root / "runs").iterdir())
        self.assertEqual(len(runs), 1)
        with redirect_stdout(io.StringIO()):
            MODULE.command_archive(SimpleNamespace(run_dir=str(runs[0])))
        self.assertEqual(MODULE.load_run(runs[0])["status"], "archived")
        with mock.patch.object(MODULE, "active_github_owner", return_value="tester"):
            with redirect_stdout(io.StringIO()):
                MODULE.command_publish(args)
        self.assertEqual(len(list((state_root / "runs").iterdir())), 2)

    def test_state_transaction_lock_serializes_separate_processes(self) -> None:
        state_root = self.root / "state"
        child_code = "\n".join(
            (
                "import importlib.util, pathlib, sys",
                "spec = importlib.util.spec_from_file_location('review_repo_child', sys.argv[1])",
                "module = importlib.util.module_from_spec(spec)",
                "spec.loader.exec_module(module)",
                "pathlib.Path(sys.argv[3]).write_text('ready', encoding='utf-8')",
                "with module.state_transaction(pathlib.Path(sys.argv[2])):",
                "    print('acquired', flush=True)",
            )
        )
        ready = self.root / "child-ready"
        with MODULE.state_transaction(state_root):
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    child_code,
                    str(SCRIPT),
                    str(state_root),
                    str(ready),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={
                    **os.environ,
                    "PYTHONPYCACHEPREFIX": str(self.root / "pycache"),
                },
            )
            deadline = time.monotonic() + 5
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(ready.is_file())
            time.sleep(0.1)
            self.assertIsNone(child.poll())
        stdout, stderr = child.communicate(timeout=5)
        self.assertEqual(child.returncode, 0, stderr)
        self.assertEqual(stdout.strip(), "acquired")
        self.assertEqual((state_root / ".state.lock").stat().st_mode & 0o777, 0o600)

    def test_github_cli_preflight_never_starts_login_or_claims_app_access(self) -> None:
        calls: list[list[str]] = []

        def successful(command_args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            calls.append(command_args)
            if command_args[:3] == ["gh", "auth", "status"]:
                return subprocess.CompletedProcess(command_args, 0, "", "")
            if command_args[:5] == ["gh", "api", "--hostname", "github.com", "user"]:
                return subprocess.CompletedProcess(command_args, 0, "tester\n", "")
            raise AssertionError(command_args)

        with mock.patch.object(MODULE, "run", side_effect=successful):
            self.assertEqual(MODULE.active_github_owner(), "tester")
        self.assertEqual(len(calls), 2)
        self.assertFalse(any(item == "login" for call in calls for item in call))

        calls.clear()

        def missing(command_args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            calls.append(command_args)
            return subprocess.CompletedProcess(command_args, 1, "", "not logged in")

        with mock.patch.object(MODULE, "run", side_effect=missing):
            with self.assertRaisesRegex(MODULE.ReviewError, "not authenticated"):
                MODULE.active_github_owner()
        self.assertEqual(len(calls), 1)
        self.assertFalse(any(item == "login" for call in calls for item in call))

    def test_mirror_naming_rejects_generic_paths_and_uses_meaningful_origin(self) -> None:
        source = self.root / "repo"
        init_repo(source)
        commit_file(source, "value.txt", "one\n", "one")
        with self.assertRaisesRegex(MODULE.ReviewError, "meaningful private mirror"):
            MODULE.resolve_mirror("tester", source, None, None)

        command(
            "git",
            "remote",
            "add",
            "origin",
            "git@github.com:upstream/meaningful-project.git",
            cwd=source,
        )
        self.assertEqual(
            MODULE.resolve_mirror("tester", source, None, None),
            "tester/meaningful-project-private-backup",
        )
        mapping = {"mirror": "tester/persistent-backup"}
        self.assertEqual(
            MODULE.resolve_mirror("tester", source, None, mapping),
            "tester/persistent-backup",
        )
        with self.assertRaisesRegex(MODULE.ReviewError, "persistent mirror mapping"):
            MODULE.resolve_mirror("tester", source, "tester/second-backup", mapping)

    def test_raw_url_binding_requires_exact_repository_url(self) -> None:
        mirror = "tester/private-project"
        expected = "https://github.com/tester/private-project"
        for prompt in (expected, f"{expected}\n请审查。", f"{expected}\r\nexact request\t"):
            with self.subTest(prompt=prompt):
                self.assertEqual(
                    MODULE.require_raw_repository_url(prompt.encode("utf-8"), mirror), expected
                )
        with self.assertRaisesRegex(MODULE.ReviewError, "exact private repository URL"):
            MODULE.require_raw_repository_url(b"review this repository\n", mirror)

    def test_raw_url_does_not_accept_substrings_or_ambiguous_markup(self) -> None:
        mirror = "tester/private-project"
        url = f"https://github.com/{mirror}"
        for reference in (
            url + "-old", url + "/tree/main", url + "?query=other", url + "#fragment",
            "https://example.invalid/?repo=" + url,
            "https://example.invalid/(" + url + ")",
            "prefix" + url, "[" + url + "](https://example.invalid/)",
            "[repository](" + url + ")", "<" + url + ">", url + ".",
            "[ " + url + " ](https://example.invalid/)",
            "[\n" + url + "\n](https://example.invalid/)",
            "Review " + url, "    " + url,
        ):
            original = ("检查 " + reference + "\r\n  exact bytes  \n").encode()
            with self.subTest(reference=reference):
                with self.assertRaisesRegex(MODULE.ReviewError, "exact private repository URL"):
                    MODULE.require_raw_repository_url(original, mirror)
                self.assertEqual(MODULE.compose_review_prompt(original, mirror, "raw-url"),
                                 url.encode() + b"\n\n" + original)
                self.assertEqual(MODULE.compose_review_prompt(original, mirror, "source-chip"), original)


class BrowserStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        init_repo(self.repo)
        commit_file(self.repo, "file.txt", "value\n", "base")
        self.run_dir = MODULE.create_run(
            self.root / "state",
            self.repo,
            "review",
            b"exact prompt\n",
            "run-state",
            "source-chip",
        )
        state = MODULE.load_run(self.run_dir)
        state.update(
            {
                "status": "published",
                "mirror": "tester/private-project",
                "mirror_private": True,
                "review_branch": "main",
                "review_commit": "a" * 40,
                "binding_assurance": "source-chip-pending-v1",
                "github_cli_auth": {"status": "verified", "owner": "tester"},
                "github_app_auth": {"status": "unverified"},
            }
        )
        MODULE.save_run(self.run_dir, state)
        MODULE.write_json(
            self.run_dir / "source-manifest.json",
            {
                "run_id": "run-state",
                "source_repo": str(self.repo.resolve()),
                "review_commit": "a" * 40,
                "binding": "source-chip",
                "prompt_sha256": MODULE.sha256_bytes(b"exact prompt\n"),
                "prompt_bytes": len(b"exact prompt\n"),
            },
        )
        MODULE.write_json(
            self.run_dir / "publish-result.json",
            {
                "status": "published",
                "run_id": "run-state",
                "run_dir": str(self.run_dir),
                "source_repo": str(self.repo.resolve()),
                "mirror": "tester/private-project",
                "mirror_private": True,
                "review_branch": "main",
                "review_commit": "a" * 40,
                "binding": "source-chip",
                "binding_assurance": "source-chip-pending-v1",
                "prompt_sha256": MODULE.sha256_bytes(b"exact prompt\n"),
                "prompt_bytes": len(b"exact prompt\n"),
                "github_cli_auth": {"status": "verified", "owner": "tester"},
                "github_app_auth": {"status": "unverified"},
            },
        )
        self.tab("register", "chat-1", kind="chatgpt-draft")
        self.tab("activate", "chat-1")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def event(self, event: str, url: str | None = None, **overrides: object) -> None:
        values: dict[str, object | None] = {
            "run_dir": str(self.run_dir),
            "event": event,
            "conversation_url": url,
            "message": None,
            "capability_label": None,
            "deep_research": None,
            "app_grant": None,
            "binding": None,
            "repository": None,
            "default_branch": None,
            "commit": None,
            "tab_id": None,
            "prompt_sha256": None,
            "fill_method": None,
            "submission_method": None,
            "generation_sentinel": None,
            "completion_proof": None,
            "final_container": None,
        }
        values.update(overrides)
        with redirect_stdout(io.StringIO()):
            MODULE.command_event(SimpleNamespace(**values))

    def tab(
        self,
        action: str,
        tab_id: str,
        *,
        kind: str = "chatgpt-draft",
        url: str | None = None,
        reason: str | None = None,
    ) -> None:
        with redirect_stdout(io.StringIO()):
            MODULE.command_tab(
                SimpleNamespace(
                    run_dir=str(self.run_dir),
                    action=action,
                    tab_id=tab_id,
                    kind=kind,
                    url=url,
                    reason=reason,
                )
            )

    def bind_source(self, **overrides: object) -> None:
        values: dict[str, object] = {
            "capability_label": "Pro",
            "deep_research": "active",
            "app_grant": "verified",
            "binding": "source-chip",
            "repository": "tester/private-project",
            "default_branch": "main",
            "commit": "a" * 40,
            "tab_id": "chat-1",
        }
        values.update(overrides)
        evidence = {
            "mirror": "tester/private-project",
            "default_branch": "main",
            "review_commit": "a" * 40,
            "github_cli_owner": "tester",
            "verified_at": "2026-08-23T00:00:00+00:00",
            "evidence_sha256": "f" * 64,
        }
        with mock.patch.object(
            MODULE, "verify_remote_review_commit", return_value=evidence
        ):
            self.event("source-bound", **values)

    def ready_composer(self, **overrides: object) -> None:
        values: dict[str, object] = {
            "prompt_sha256": MODULE.sha256_bytes(b"exact prompt\n"),
            "fill_method": "single-operation",
            "tab_id": "chat-1",
        }
        values.update(overrides)
        self.event("composer-ready", **values)

    def submit(self, method: str = "send-button") -> None:
        self.event(
            "submitted",
            "https://chatgpt.com/c/review-run",
            submission_method=method,
            tab_id="chat-1",
        )

    def test_one_submit_two_waits_one_reconnect_and_one_collect(self) -> None:
        self.bind_source()
        self.ready_composer()
        self.submit()
        with self.assertRaisesRegex(MODULE.ReviewError, "requires composer-ready"):
            self.event(
                "submitted",
                "https://chatgpt.com/c/duplicate",
                submission_method="send-button",
                tab_id="chat-1",
            )
        self.event(
            "wait-start", tab_id="chat-1", generation_sentinel="generation-1"
        )
        self.event("pending")
        self.event("reconnect", tab_id="chat-1")
        self.event(
            "wait-start", tab_id="chat-1", generation_sentinel="generation-2"
        )
        self.event(
            "wait-complete",
            tab_id="chat-1",
            generation_sentinel="generation-2",
            completion_proof="generation-sentinel-absent-and-final-container-present",
            final_container="deep-research-report",
        )
        answer = self.root / "answer.md"
        private_answer(answer)
        answer_sha = MODULE.sha256_bytes(answer.read_bytes())
        with redirect_stdout(io.StringIO()):
            MODULE.command_collect(
                SimpleNamespace(
                    run_dir=str(self.run_dir),
                    answer_file=str(answer),
                    answer_sha256=answer_sha,
                    source_kind="deep-research-report",
                    source_conversation_url="https://chatgpt.com/c/review-run",
                    source_tab_id="chat-1",
                )
            )
        state = MODULE.load_run(self.run_dir)
        self.assertEqual(state["status"], "collected")
        self.assertEqual(state["wait_count"], 2)
        self.assertEqual(state["reconnect_count"], 1)
        self.assertEqual(state["answer_source"]["observed_sha256"], answer_sha)
        self.assertEqual(state["answer_source"]["source_kind"], "deep-research-report")
        with self.assertRaisesRegex(MODULE.ReviewError, "requires completed"):
            MODULE.command_collect(
                SimpleNamespace(
                    run_dir=str(self.run_dir),
                    answer_file=str(answer),
                    answer_sha256=answer_sha,
                    source_kind="deep-research-report",
                    source_conversation_url="https://chatgpt.com/c/review-run",
                    source_tab_id="chat-1",
                )
            )

    def test_wait_complete_requires_matching_generation_and_final_container(self) -> None:
        self.bind_source()
        self.ready_composer()
        self.submit()
        with self.assertRaisesRegex(MODULE.ReviewError, "generation sentinel"):
            self.event("wait-start", tab_id="chat-1")
        self.event(
            "wait-start", tab_id="chat-1", generation_sentinel="generation-1"
        )
        with self.assertRaisesRegex(MODULE.ReviewError, "completion proof"):
            self.event("wait-complete", tab_id="chat-1")
        with self.assertRaisesRegex(MODULE.ReviewError, "sentinel mismatch"):
            self.event(
                "wait-complete",
                tab_id="chat-1",
                generation_sentinel="generation-other",
                completion_proof="generation-sentinel-absent-and-final-container-present",
                final_container="deep-research-report",
            )
        with self.assertRaisesRegex(MODULE.ReviewError, "final container"):
            self.event(
                "wait-complete",
                tab_id="chat-1",
                generation_sentinel="generation-1",
                completion_proof="generation-sentinel-absent-and-final-container-present",
                final_container="assistant-turn",
            )
        self.event(
            "wait-complete",
            tab_id="chat-1",
            generation_sentinel="generation-1",
            completion_proof="generation-sentinel-absent-and-final-container-present",
            final_container="deep-research-report",
        )
        evidence = MODULE.load_run(self.run_dir)["completion_evidence"]
        self.assertEqual(evidence["generation_sentinel"], "generation-1")
        self.assertEqual(evidence["wait_sequence"], 1)

    def test_prompt_snapshot_is_byte_frozen_for_lifecycle_transitions(self) -> None:
        (self.run_dir / "prompt.txt").write_bytes(b"changed prompt\n")
        with self.assertRaisesRegex(MODULE.ReviewError, "frozen prompt"):
            self.bind_source()

    def test_published_identity_and_remote_commit_drift_fail_closed(self) -> None:
        published = MODULE.read_json(self.run_dir / "publish-result.json")
        published["review_commit"] = "b" * 40
        MODULE.write_json(self.run_dir / "publish-result.json", published)
        with self.assertRaisesRegex(MODULE.ReviewError, "published identity drift"):
            self.bind_source()

        published["review_commit"] = "a" * 40
        MODULE.write_json(self.run_dir / "publish-result.json", published)
        with mock.patch.object(MODULE, "active_github_owner", return_value="tester"):
            with mock.patch.object(
                MODULE,
                "github_repo_info",
                return_value=mirror_metadata(
                    "tester/private-project",
                    MODULE.DESCRIPTION_PREFIX + MODULE.project_key(self.repo.resolve()),
                ),
            ):
                matching = subprocess.CompletedProcess(
                    ["gh", "api"], 0, "a" * 40 + "\n", ""
                )
                with mock.patch.object(MODULE, "run", return_value=matching):
                    evidence = MODULE.verify_remote_review_commit(
                        self.run_dir, MODULE.load_run(self.run_dir)
                    )
                self.assertEqual(evidence["review_commit"], "a" * 40)
                self.assertRegex(evidence["evidence_sha256"], r"^[0-9a-f]{64}$")

                drifted = subprocess.CompletedProcess(
                    ["gh", "api"], 0, "b" * 40 + "\n", ""
                )
                with mock.patch.object(MODULE, "run", return_value=drifted):
                    with self.assertRaisesRegex(MODULE.ReviewError, "remote review commit drift"):
                        MODULE.verify_remote_review_commit(
                            self.run_dir, MODULE.load_run(self.run_dir)
                        )
            with mock.patch.object(
                MODULE,
                "github_repo_info",
                return_value=mirror_metadata("tester/private-project", "different manager"),
            ):
                with self.assertRaisesRegex(MODULE.ReviewError, "management marker drift"):
                    MODULE.verify_remote_review_commit(
                        self.run_dir, MODULE.load_run(self.run_dir)
                    )

    def test_cli_and_github_app_evidence_are_separate_with_binding_assurance(self) -> None:
        before = MODULE.load_run(self.run_dir)
        self.assertEqual(before["github_cli_auth"]["status"], "verified")
        self.assertEqual(before["github_app_auth"]["status"], "unverified")
        self.assertEqual(before["binding_assurance"], "source-chip-pending-v1")
        self.bind_source()
        after = MODULE.load_run(self.run_dir)
        self.assertEqual(after["github_app_auth"]["status"], "verified")
        self.assertEqual(
            after["binding_assurance"], "github-app-source-chip-exact-commit-v1"
        )

    def test_raw_url_binding_remains_reference_only_after_app_grant(self) -> None:
        prompt = b"https://github.com/tester/private-project\n\nexact prompt\n"
        MODULE.atomic_write(self.run_dir / "prompt.txt", prompt)
        prompt_evidence = {"prompt_sha256": MODULE.sha256_bytes(prompt), "prompt_bytes": len(prompt)}
        state = MODULE.load_run(self.run_dir)
        state.update(prompt_evidence)
        state["binding"] = "raw-url"
        state["binding_assurance"] = "raw-url-reference-only-v1"
        MODULE.save_run(self.run_dir, state)
        manifest = MODULE.read_json(self.run_dir / "source-manifest.json")
        manifest.update(prompt_evidence)
        manifest["binding"] = "raw-url"
        MODULE.write_json(self.run_dir / "source-manifest.json", manifest)
        published = MODULE.read_json(self.run_dir / "publish-result.json")
        published.update(prompt_evidence)
        published["binding"] = "raw-url"
        published["binding_assurance"] = "raw-url-reference-only-v1"
        published["raw_repository_url"] = "https://github.com/tester/private-project"
        MODULE.write_json(self.run_dir / "publish-result.json", published)

        self.bind_source(binding="raw-url")
        after = MODULE.load_run(self.run_dir)
        self.assertEqual(after["source_index"], "not-applicable")
        self.assertEqual(after["binding_assurance"], "raw-url-reference-only-v1")
        self.assertEqual(after["github_app_auth"]["status"], "verified")

    def test_legacy_combined_raw_prompt_is_rechecked_before_browser_use(self) -> None:
        state = MODULE.load_run(self.run_dir)
        state["binding"] = "raw-url"
        # Old v3 combined-command receipts may be internally consistent while
        # containing a URL accepted by the earlier substring check.
        self.assertNotIn("review_input_version", state)
        url = "https://github.com/tester/private-project"
        for reference in (url + "-old", "https://example.invalid/?repo=" + url,
                          "[ " + url + " ](https://example.invalid/)", url):
            prompt = ("Review " + reference + "\n").encode()
            MODULE.atomic_write(self.run_dir / "prompt.txt", prompt)
            state.update(prompt_sha256=MODULE.sha256_bytes(prompt), prompt_bytes=len(prompt))
            with self.subTest(reference=reference), self.assertRaisesRegex(
                MODULE.ReviewError, "exact private repository URL"
            ):
                MODULE.verify_prompt_snapshot(self.run_dir, state)

    def test_collect_requires_browser_source_and_exact_input_hash(self) -> None:
        self.bind_source()
        self.ready_composer()
        self.submit()
        self.event(
            "wait-start", tab_id="chat-1", generation_sentinel="generation-1"
        )
        self.event(
            "wait-complete",
            tab_id="chat-1",
            generation_sentinel="generation-1",
            completion_proof="generation-sentinel-absent-and-final-container-present",
            final_container="deep-research-report",
        )
        answer = self.root / "browser-extract.md"
        private_answer(answer)
        good = {
            "run_dir": str(self.run_dir),
            "answer_file": str(answer),
            "answer_sha256": MODULE.sha256_bytes(answer.read_bytes()),
            "source_kind": "deep-research-report",
            "source_conversation_url": "https://chatgpt.com/c/review-run",
            "source_tab_id": "chat-1",
        }
        with self.assertRaisesRegex(MODULE.ReviewError, "answer SHA-256 mismatch"):
            MODULE.command_collect(SimpleNamespace(**{**good, "answer_sha256": "0" * 64}))
        with self.assertRaisesRegex(MODULE.ReviewError, "conversation URL mismatch"):
            MODULE.command_collect(
                SimpleNamespace(
                    **{
                        **good,
                        "source_conversation_url": "https://chatgpt.com/c/other",
                    }
                )
            )
        link = self.root / "answer-link.md"
        link.symlink_to(answer)
        with self.assertRaisesRegex(MODULE.ReviewError, "symlink"):
            MODULE.command_collect(SimpleNamespace(**{**good, "answer_file": str(link)}))

    def test_warning_is_terminal(self) -> None:
        self.bind_source()
        self.event("warning", message="frequent access warning")
        self.assertEqual(MODULE.load_run(self.run_dir)["status"], "blocked")
        with self.assertRaisesRegex(MODULE.ReviewError, "requires composer-ready"):
            self.event(
                "submitted",
                "https://chatgpt.com/c/forbidden",
                submission_method="send-button",
                tab_id="chat-1",
            )

    def test_source_binding_rejects_model_mode_and_source_mismatches(self) -> None:
        cases = (
            ("capability_label", "xhigh", "exactly Pro"),
            ("deep_research", "inactive", "requires Deep Research active"),
            ("repository", "tester/wrong", "repository mismatch"),
            ("default_branch", "topic", "default_branch mismatch"),
            ("commit", "b" * 40, "commit mismatch"),
            ("binding", "raw-url", "binding mismatch"),
        )
        for key, value, message in cases:
            with self.subTest(key=key):
                with self.assertRaisesRegex(MODULE.ReviewError, message):
                    self.bind_source(**{key: value})

    def test_pro_mode_requires_deep_research_inactive(self) -> None:
        state = MODULE.load_run(self.run_dir)
        state["mode"] = "pro"
        MODULE.save_run(self.run_dir, state)
        with self.assertRaisesRegex(MODULE.ReviewError, "requires Deep Research inactive"):
            self.bind_source(deep_research="active")
        self.bind_source(deep_research="inactive")
        self.assertEqual(MODULE.load_run(self.run_dir)["status"], "source-bound")
        self.ready_composer()
        self.submit()
        self.event(
            "wait-start", tab_id="chat-1", generation_sentinel="generation-pro"
        )
        with self.assertRaisesRegex(MODULE.ReviewError, "final container"):
            self.event(
                "wait-complete",
                tab_id="chat-1",
                generation_sentinel="generation-pro",
                completion_proof="generation-sentinel-absent-and-final-container-present",
                final_container="deep-research-report",
            )
        self.event(
            "wait-complete",
            tab_id="chat-1",
            generation_sentinel="generation-pro",
            completion_proof="generation-sentinel-absent-and-final-container-present",
            final_container="assistant-turn",
        )

    def test_composer_and_submission_are_fail_closed(self) -> None:
        self.bind_source()
        with self.assertRaisesRegex(MODULE.ReviewError, "prompt SHA-256 mismatch"):
            self.ready_composer(prompt_sha256="0" * 64)
        with self.assertRaisesRegex(MODULE.ReviewError, "single-operation"):
            self.ready_composer(fill_method="sequential-typing")
        self.ready_composer()
        with self.assertRaisesRegex(MODULE.ReviewError, "send-button"):
            self.submit("enter")
        with self.assertRaisesRegex(MODULE.ReviewError, "durable"):
            self.event(
                "submitted",
                "https://chatgpt.com/",
                submission_method="send-button",
                tab_id="chat-1",
            )

    def test_index_pending_can_resume_without_polling(self) -> None:
        with mock.patch.object(
            MODULE,
            "verify_remote_review_commit",
            return_value={
                "mirror": "tester/private-project",
                "default_branch": "main",
                "review_commit": "a" * 40,
                "github_cli_owner": "tester",
                "verified_at": "2026-08-23T00:00:00+00:00",
                "evidence_sha256": "f" * 64,
            },
        ):
            self.event(
            "source-index-pending",
            app_grant="verified",
            binding="source-chip",
            repository="tester/private-project",
            default_branch="main",
            commit="a" * 40,
            tab_id="chat-1",
            )
        self.assertEqual(MODULE.load_run(self.run_dir)["status"], "source-index-pending")
        self.bind_source()
        self.assertEqual(MODULE.load_run(self.run_dir)["source_index"], "ready")

    def test_owned_tab_ledger_never_accepts_unrelated_tabs(self) -> None:
        with self.assertRaisesRegex(MODULE.ReviewError, "not owned"):
            self.tab("activate", "user-tab")
        self.tab("register", "github-1", kind="github-temporary")
        self.tab("close", "github-1")
        with self.assertRaisesRegex(MODULE.ReviewError, "already closed"):
            self.tab("activate", "github-1")
        self.bind_source()
        self.ready_composer()
        self.submit()
        with self.assertRaisesRegex(MODULE.ReviewError, "must remain open"):
            self.tab("close", "chat-1")

    def test_disconnected_saved_tab_can_be_replaced_once(self) -> None:
        self.bind_source()
        self.ready_composer()
        self.submit()
        self.event(
            "wait-start", tab_id="chat-1", generation_sentinel="generation-1"
        )
        self.event("pending")
        self.tab("close", "chat-1", reason="disconnected")
        self.tab(
            "register",
            "chat-2",
            kind="chatgpt-conversation",
            url="https://chatgpt.com/c/review-run",
        )
        self.tab("activate", "chat-2")
        self.event("reconnect", tab_id="chat-2")
        self.event(
            "wait-start", tab_id="chat-2", generation_sentinel="generation-2"
        )
        self.assertEqual(MODULE.load_run(self.run_dir)["wait_count"], 2)

    def test_supersede_reuses_snapshot_without_git_or_github_calls(self) -> None:
        with self.assertRaisesRegex(MODULE.ReviewError, "would not change"):
            MODULE.command_supersede(
                SimpleNamespace(
                    run_dir=str(self.run_dir),
                    mode="review",
                    prompt_file=str(self.run_dir / "prompt.txt"),
                    binding="source-chip",
                    reason="no change",
                )
            )
        self.tab("close", "chat-1")
        replacement_prompt = self.root / "replacement.txt"
        replacement_prompt.write_text("corrected prompt\n", encoding="utf-8")
        with mock.patch.object(MODULE, "run", side_effect=AssertionError("external call")):
            with redirect_stdout(io.StringIO()):
                MODULE.command_supersede(
                    SimpleNamespace(
                        run_dir=str(self.run_dir),
                        mode="pro",
                        prompt_file=str(replacement_prompt),
                        binding="source-chip",
                        reason="correct mode",
                    )
                )
        self.assertEqual(MODULE.load_run(self.run_dir)["status"], "superseded")
        runs = list((self.root / "state" / "runs").iterdir())
        replacement = next(path for path in runs if path != self.run_dir)
        replacement_state = MODULE.load_run(replacement)
        self.assertEqual(replacement_state["status"], "published")
        self.assertTrue(replacement_state["snapshot_reused"])
        self.assertEqual(replacement_state["review_commit"], "a" * 40)

    def test_list_archive_and_legacy_v1_visibility(self) -> None:
        legacy_dir = MODULE.create_run(
            self.root / "state",
            self.repo,
            "pro",
            b"legacy\n",
            "legacy-run",
        )
        legacy = MODULE.load_run(legacy_dir)
        legacy["version"] = 1
        legacy["status"] = "waiting"
        MODULE.save_run(legacy_dir, legacy)

        output = io.StringIO()
        with redirect_stdout(output):
            MODULE.command_list(
                SimpleNamespace(state_root=str(self.root / "state"), all=False)
            )
        listed = MODULE.json.loads(output.getvalue())["runs"]
        legacy_item = next(item for item in listed if item["run_id"] == "legacy-run")
        self.assertTrue(legacy_item["legacy_unverified"])

        self.event("warning", message="manual stop")
        with self.assertRaisesRegex(MODULE.ReviewError, "end first"):
            MODULE.command_archive(SimpleNamespace(run_dir=str(self.run_dir)))
        with redirect_stdout(io.StringIO()):
            MODULE.command_end(SimpleNamespace(run_dir=str(self.run_dir), observed="not-submitted",
                                              conversation_url=None, reason="draft was never sent"))
            MODULE.command_archive(SimpleNamespace(run_dir=str(self.run_dir)))
        self.assertEqual(MODULE.load_run(self.run_dir)["status"], "archived")
        with self.assertRaisesRegex(MODULE.ReviewError, "requires prepared"):
            MODULE.command_archive(SimpleNamespace(run_dir=str(legacy_dir)))

    def test_legacy_v1_run_is_read_only_and_can_be_blocked_for_archive(self) -> None:
        legacy_dir = MODULE.create_run(
            self.root / "state",
            self.repo,
            "pro",
            b"legacy prompt\n",
            "legacy-resume",
        )
        legacy = MODULE.load_run(legacy_dir)
        legacy["version"] = 1
        legacy["status"] = "published"
        MODULE.save_run(legacy_dir, legacy)

        def legacy_event(event: str, url: str | None = None) -> None:
            with redirect_stdout(io.StringIO()):
                MODULE.command_event(
                    SimpleNamespace(
                        run_dir=str(legacy_dir),
                        event=event,
                        conversation_url=url,
                        message=None,
                        capability_label=None,
                        deep_research=None,
                        app_grant=None,
                        binding=None,
                        repository=None,
                        default_branch=None,
                        commit=None,
                        tab_id=None,
                        prompt_sha256=None,
                        fill_method=None,
                        submission_method=None,
                        generation_sentinel=None,
                        completion_proof=None,
                        final_container=None,
                    )
                )

        with self.assertRaisesRegex(MODULE.ReviewError, "legacy runs are read-only"):
            legacy_event("source-bound")
        final = MODULE.load_run(legacy_dir)
        self.assertEqual(final["status"], "published")
        self.assertTrue(MODULE.displayed_run(final)["legacy_unverified"])
        with self.assertRaisesRegex(MODULE.ReviewError, "unavailable for legacy"):
            MODULE.command_tab(
                SimpleNamespace(
                    run_dir=str(legacy_dir),
                    action="register",
                    tab_id="legacy-tab",
                    kind="chatgpt-draft",
                    url=None,
                    reason=None,
                )
            )

    def test_pending_completion_and_collection_keep_strict_evidence(self) -> None:
        self.bind_source()
        self.ready_composer()
        self.submit()
        self.event("wait-start", tab_id="chat-1", generation_sentinel="generation-1")
        self.event("pending")
        # No more browser waits are needed to recognize an already-finished answer.
        state = MODULE.load_run(self.run_dir)
        state["wait_count"] = 2
        state["reconnect_count"] = 1
        MODULE.save_run(self.run_dir, state)
        complete = dict(tab_id="chat-1", generation_sentinel="generation-1",
                        completion_proof=MODULE.COMPLETION_PROOF,
                        final_container="deep-research-report")
        for changes in ({"generation_sentinel": "wrong"}, {"tab_id": "unrelated"},
                        {"final_container": "assistant-turn"}, {"completion_proof": None}):
            with self.subTest(changes=changes), self.assertRaises(MODULE.ReviewError):
                self.event("wait-complete", **{**complete, **changes})
        self.assertEqual(MODULE.load_run(self.run_dir)["status"], "pending")
        self.event("wait-complete", **complete)
        answer = private_answer(self.root / "pending-answer.md")
        with redirect_stdout(io.StringIO()):
            MODULE.command_collect(SimpleNamespace(
                run_dir=str(self.run_dir), answer_file=str(answer),
                answer_sha256=MODULE.sha256_bytes(answer.read_bytes()),
                source_kind="deep-research-report", source_tab_id="chat-1",
                source_conversation_url="https://chatgpt.com/c/review-run"))
        state = MODULE.load_run(self.run_dir)
        self.assertEqual((state["status"], state["wait_count"], state["reconnect_count"]),
                         ("collected", 2, 1))

    def test_pending_accepts_only_a_recorded_disconnected_replacement(self) -> None:
        self.bind_source()
        self.ready_composer()
        self.submit()
        self.event("wait-start", tab_id="chat-1", generation_sentinel="generation-1")
        self.event("pending")
        self.tab("register", "replacement", kind="chatgpt-conversation",
                 url="https://chatgpt.com/c/review-run")
        self.tab("activate", "replacement")
        complete = dict(tab_id="replacement", generation_sentinel="generation-1",
                        completion_proof=MODULE.COMPLETION_PROOF,
                        final_container="deep-research-report")
        with self.assertRaisesRegex(MODULE.ReviewError, "same active saved"):
            self.event("wait-complete", **complete)
        self.tab("close", "chat-1", reason="disconnected")
        self.tab("register", "wrong", kind="chatgpt-conversation", url="https://chatgpt.com/c/wrong")
        self.tab("activate", "wrong")
        with self.assertRaisesRegex(MODULE.ReviewError, "same active saved"):
            self.event("wait-complete", **{**complete, "tab_id": "wrong"})
        self.tab("activate", "replacement")
        self.event("wait-complete", **complete)
        proof = MODULE.load_run(self.run_dir)["completion_evidence"]
        self.assertEqual((proof["tab_id"], proof["wait_tab_id"]), ("replacement", "chat-1"))

    def test_submitted_warning_holds_source_until_observed_end(self) -> None:
        self.bind_source()
        self.ready_composer()
        self.submit()
        self.event("warning", message="rate limit")
        state_root = self.run_dir.parent.parent
        self.assertTrue(MODULE.active_runs_for_source(state_root, self.repo))
        with self.assertRaisesRegex(MODULE.ReviewError, "end first"):
            MODULE.command_archive(SimpleNamespace(run_dir=str(self.run_dir)))
        args = dict(run_dir=str(self.run_dir), observed="cancelled",
                    conversation_url="https://chatgpt.com/c/review-run", reason="cancelled on page")
        for changes in ({"conversation_url": "https://chatgpt.com/c/wrong"},
                        {"observed": "not-submitted"}):
            with self.assertRaises(MODULE.ReviewError):
                MODULE.command_end(SimpleNamespace(**{**args, **changes}))
        with redirect_stdout(io.StringIO()):
            MODULE.command_end(SimpleNamespace(**args))
        self.assertFalse(MODULE.active_runs_for_source(state_root, self.repo))
        self.assertEqual(MODULE.load_run(self.run_dir)["ended_from_status"], "blocked")
        self.assertTrue((self.run_dir / "prompt.txt").is_file())
        self.tab("close", "chat-1", reason="ended")

    def test_warning_in_send_acknowledgement_gap_never_releases_the_source(self) -> None:
        self.bind_source()
        self.ready_composer()
        # The page sent, but the local submitted acknowledgement was interrupted.
        self.event("warning", message="warning after clicking Send")
        self.assertTrue(MODULE.active_runs_for_source(self.run_dir.parent.parent, self.repo))
        with self.assertRaisesRegex(MODULE.ReviewError, "end first"):
            MODULE.command_archive(SimpleNamespace(run_dir=str(self.run_dir)))
        args = dict(run_dir=str(self.run_dir), observed="finished", reason="observed stopped after interrupted send",
                    conversation_url="https://chatgpt.com/c/already-sent")
        with self.assertRaisesRegex(MODULE.ReviewError, "active owned saved"):
            MODULE.command_end(SimpleNamespace(**args))
        self.tab("register", "saved-after-send", kind="chatgpt-conversation", url=args["conversation_url"])
        self.tab("activate", "saved-after-send")
        with self.assertRaisesRegex(MODULE.ReviewError, "active owned saved"):
            MODULE.command_end(SimpleNamespace(**{**args, "conversation_url": "https://chatgpt.com/c/other"}))
        with redirect_stdout(io.StringIO()):
            MODULE.command_end(SimpleNamespace(**args))
        state = MODULE.load_run(self.run_dir)
        self.assertEqual((state["status"], state["conversation_url"]), ("ended", args["conversation_url"]))
        self.assertTrue(state["submission_recovered_for_end_only"])
        self.assertNotIn("completion_evidence", state)
        self.assertFalse(MODULE.active_runs_for_source(self.run_dir.parent.parent, self.repo))

    def test_supersede_serializes_against_a_concurrent_browser_write(self) -> None:
        self.bind_source()
        self.tab("close", "chat-1", reason="correcting draft")
        prompt = self.root / "corrected.txt"
        prompt.write_text("corrected request\n")
        attempted = self.root / "attempted-write"
        completed = self.root / "completed-write"
        child_code = "\n".join((
            "import importlib.util,pathlib,sys", "spec=importlib.util.spec_from_file_location('pgpr',sys.argv[1])",
            "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)",
            "pathlib.Path(sys.argv[3]).touch()",
            "args=m.build_parser().parse_args(['event','--run-dir',sys.argv[2],'--event','warning','--message','concurrent warning'])",
            "try: args.func(args)",
            "except m.ReviewError: pathlib.Path(sys.argv[4]).write_text('rejected')",
            "else: pathlib.Path(sys.argv[4]).write_text('accepted')"))
        children = []
        original = MODULE.read_prompt
        def while_correcting(value):
            data = original(value)
            child = subprocess.Popen([sys.executable, "-c", child_code, str(SCRIPT), str(self.run_dir), str(attempted), str(completed)],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            children.append(child)
            deadline = time.monotonic() + 5
            while not attempted.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(attempted.exists())
            # Try the lock in this process too: it must be held for the entire
            # correction, not just while allocating the new run directory.
            fd = os.open(self.run_dir.parent.parent / ".state.lock", os.O_RDWR)
            try:
                with self.assertRaises(BlockingIOError):
                    MODULE.fcntl.flock(fd, MODULE.fcntl.LOCK_EX | MODULE.fcntl.LOCK_NB)
            finally:
                os.close(fd)
            self.assertFalse(completed.exists())
            return data
        try:
            with mock.patch.object(MODULE, "read_prompt", side_effect=while_correcting), redirect_stdout(io.StringIO()):
                MODULE.command_supersede(SimpleNamespace(run_dir=str(self.run_dir), mode="pro", binding="source-chip",
                                                         prompt_file=str(prompt), reason="mode correction"))
            children[0].wait(timeout=5)
            self.assertEqual(completed.read_text(), "rejected")
            state = MODULE.load_run(self.run_dir)
            self.assertEqual(state["status"], "superseded")
            self.assertIsNone(state["conversation_url"])
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                child.wait(timeout=5)

    def test_ready_or_blocked_run_cannot_supersede_unknown_submission(self) -> None:
        self.bind_source()
        self.ready_composer()
        self.tab("close", "chat-1", reason="draft abandoned")
        corrected = self.root / "corrected-unknown-send.txt"
        corrected.write_text("different review request\n")
        args = SimpleNamespace(run_dir=str(self.run_dir), mode="pro", binding="source-chip",
                               prompt_file=str(corrected), reason="change request")
        for status in ("composer-ready", "blocked"):
            if status == "blocked":
                self.event("warning", message="unknown Send acknowledgement")
            with self.subTest(status=status), self.assertRaisesRegex(MODULE.ReviewError, "use end"):
                MODULE.command_supersede(args)
            self.assertEqual(MODULE.load_run(self.run_dir)["status"], status)
            active = MODULE.active_runs_for_source(self.run_dir.parent.parent, self.repo)
            self.assertEqual(len(active), 1)
            self.assertEqual(len(list(self.run_dir.parent.iterdir())), 1)

class SecurityBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def repository(self, name: str = 'repo') -> Path:
        repo = self.root / name
        init_repo(repo)
        command('git', 'branch', '-M', 'main', cwd=repo)
        return repo

    def validate(self, repo: Path, allowed: set[str] | None = None) -> dict:
        return MODULE.validate_backup_payload(repo, command('git', 'rev-parse', 'HEAD', cwd=repo), allowed or set())

    def test_shared_blob_keeps_every_sensitive_filename(self) -> None:
        repo = self.repository()
        commit_file(repo, 'a.txt', '{"password":"synthetic fixture"}', 'ordinary alias')
        commit_file(repo, 'credentials.json', '{"password":"synthetic fixture"}', 'sensitive alias')
        with self.assertRaisesRegex(MODULE.ReviewError, 'credentials.json'):
            self.validate(repo)
        self.assertEqual(self.validate(repo, {'credentials.json'})['file_count'], 2)

    def test_all_historical_renames_branches_and_tags_are_checked(self) -> None:
        repo = self.repository()
        first = commit_file(repo, 'a.txt', 'synthetic fixture', 'base')
        for ref_kind in ('history', 'branch', 'tag'):
            command('git', 'checkout', '-q', '-B', 'fixture', first, cwd=repo)
            name = f'{ref_kind}.key'
            command('git', 'mv', 'a.txt', name, cwd=repo)
            command('git', 'commit', '-qm', 'sensitive historical name', cwd=repo)
            if ref_kind == 'history':
                command('git', 'mv', name, 'a.txt', cwd=repo)
                command('git', 'commit', '-qm', 'renamed back', cwd=repo)
                command('git', 'branch', '-f', 'main', 'HEAD', cwd=repo)
            elif ref_kind == 'branch':
                command('git', 'branch', 'other', cwd=repo)
            else:
                command('git', 'tag', '-a', 'only-tag', '-m', 'tag-only commit', cwd=repo)
        command('git', 'checkout', '-q', 'main', cwd=repo)
        command('git', 'branch', '-D', 'fixture', cwd=repo)
        paths = {'history.key', 'branch.key', 'tag.key'}
        for omitted in paths:
            with self.subTest(omitted=omitted), self.assertRaisesRegex(MODULE.ReviewError, omitted):
                self.validate(repo, paths - {omitted})
        self.validate(repo, paths)

    def test_unicode_space_newline_paths_and_exact_path_overrides(self) -> None:
        repo = self.repository()
        paths = {'中文 目录/credentials.json', '换行\n目录/credentials.json', '普通 名字.txt'}
        for name in paths:
            (repo / name).parent.mkdir(parents=True, exist_ok=True)
            commit_file(repo, name, 'identical synthetic fixture', 'path fixture')
        sensitive = paths - {'普通 名字.txt'}
        for omitted in sensitive:
            with self.subTest(omitted=repr(omitted)), self.assertRaises(MODULE.ReviewError) as caught:
                self.validate(repo, sensitive - {omitted})
            self.assertIn(omitted, str(caught.exception))
        result = self.validate(repo, sensitive)
        self.assertEqual({entry['path'] for entry in result['files']}, paths)

    def test_content_override_does_not_authorize_another_alias(self) -> None:
        repo = self.repository()
        for name in ('a.txt', 'b.txt'):
            commit_file(repo, name, '-----BEGIN PRIVATE KEY-----\nsynthetic invalid key', 'alias')
        with self.assertRaisesRegex(MODULE.ReviewError, 'b.txt'):
            self.validate(repo, {'a.txt'})
        self.validate(repo, {'a.txt', 'b.txt'})

    def test_tree_tags_and_unnamed_blob_tags_cannot_bypass_scanning(self) -> None:
        repo = self.repository()
        base = commit_file(repo, 'a.txt', 'safe fixture', 'base')
        commit_file(repo, 'credentials.json', 'synthetic fixture', 'tree-only credential path')
        tree = command('git', 'rev-parse', 'HEAD^{tree}', cwd=repo)
        command('git', 'tag', '-a', 'tree-tag', tree, '-m', 'tree', cwd=repo)
        command('git', 'reset', '--hard', base, cwd=repo)
        with self.assertRaisesRegex(MODULE.ReviewError, 'credentials.json'):
            self.validate(repo)
        self.validate(repo, {'credentials.json'})
        blob = MODULE.git(repo, 'hash-object', '-w', '--stdin', input_text='-----BEGIN PRIVATE KEY-----\nsynthetic')
        command('git', 'tag', 'blob-tag', blob, cwd=repo)
        with self.assertRaisesRegex(MODULE.ReviewError, 'unnamed Git blob'):
            self.validate(repo, {'credentials.json'})

    def test_historical_submodule_paths_still_stop_publication(self) -> None:
        repo = self.repository()
        head = commit_file(repo, "a.txt", "safe fixture", "base")
        path = "历史\n子模块"
        command("git", "update-index", "--add", "--cacheinfo", f"160000,{head},{path}", cwd=repo)
        command("git", "commit", "-qm", "historical submodule", cwd=repo)
        command("git", "update-index", "--force-remove", "--", path, cwd=repo)
        command("git", "commit", "-qm", "removed submodule", cwd=repo)
        with self.assertRaisesRegex(MODULE.ReviewError, "submodule content") as caught:
            self.validate(repo)
        self.assertIn(path, str(caught.exception))

    def test_truncated_blob_read_is_rejected(self) -> None:
        process = mock.Mock(
            stdin=io.BytesIO(), stdout=io.BytesIO(b"abcd blob 100\nshort\n"),
            stderr=io.BytesIO(),
        )
        process.poll.return_value = 0
        with mock.patch.object(MODULE.subprocess, "Popen", return_value=process):
            with self.assertRaisesRegex(MODULE.ReviewError, "truncated git cat-file"):
                list(MODULE.iter_blob_contents(self.root, ["abcd"]))

    def test_large_blobs_are_scanned_on_both_sides_of_old_limit(self) -> None:
        repo = self.repository()
        markers = ('-----BEGIN PRIVATE KEY-----', 'ghp_' + 'T' * 36)
        base = commit_file(repo, 'a.txt', 'safe fixture', 'base')
        for size in (1_999_999, 2_000_000, 2_000_001, 3_000_000):
            for marker in markers:
                with self.subTest(size=size, marker=marker[:5]):
                    command('git', 'reset', '--hard', base, cwd=repo)
                    prefix = 'x' * (size - len(marker) - 2) + '\n'
                    commit_file(repo, 'payload.txt', prefix + marker + '\n', 'synthetic large credential')
                    self.assertEqual((repo / 'payload.txt').stat().st_size, size)
                    with self.assertRaisesRegex(MODULE.ReviewError, 'credential-like content'):
                        self.validate(repo)
        command('git', 'reset', '--hard', base, cwd=repo)
        commit_file(repo, 'payload.txt', 'x' * 3_000_000, 'normal large file')
        self.assertEqual(self.validate(repo)['file_count'], 2)

    def test_large_secret_in_history_is_still_scanned(self) -> None:
        repo = self.repository()
        commit_file(repo, 'payload.txt', 'x' * 2_100_000 + '\n-----BEGIN PRIVATE KEY-----\nfixture', 'historical secret')
        commit_file(repo, 'payload.txt', 'current safe fixture', 'removed marker')
        with self.assertRaisesRegex(MODULE.ReviewError, 'credential-like content'):
            self.validate(repo)

    def test_scan_read_failure_prevents_any_github_call(self) -> None:
        repo = self.repository()
        commit_file(repo, 'a.txt', 'safe fixture', 'base')
        prompt = self.root / 'prompt.txt'
        prompt.write_text('synthetic prompt')
        args = SimpleNamespace(repo=str(repo), prompt_file=str(prompt), state_root=str(self.root/'state'),
                               mode='review', binding='source-chip', include_working_tree=False,
                               mirror='tester/private-project', allow_sensitive_path=[], dry_run=False)
        with mock.patch.object(MODULE, 'iter_blob_contents', side_effect=MODULE.ReviewError('synthetic read failure')):
            with mock.patch.object(MODULE, 'github') as github:
                with self.assertRaisesRegex(MODULE.ReviewError, 'read failure'):
                    MODULE.command_publish(args)
                github.assert_not_called()
        state = MODULE.load_run(next((self.root/'state/runs').iterdir()))
        self.assertEqual(state['status'], 'failed')

    def read_answer(self, path: Path) -> tuple[Path, bytes]:
        return MODULE.read_regular_file_bytes(str(path), label='answer file', allowed_roots=(self.root,))

    def test_private_answer_is_read_without_changing_source_permissions(self) -> None:
        answer = private_answer(self.root / 'answer.md')
        self.assertEqual(self.read_answer(answer)[1], b'final answer\n')
        self.assertEqual(stat.S_IMODE(answer.stat().st_mode), 0o600)

    def test_answer_broad_permissions_are_rejected_without_chmod(self) -> None:
        answer = private_answer(self.root / 'answer.md')
        for mode in (0o644, 0o640, 0o666):
            answer.chmod(mode)
            with self.subTest(mode=oct(mode)), self.assertRaisesRegex(MODULE.ReviewError, '0600'):
                self.read_answer(answer)
            self.assertEqual(stat.S_IMODE(answer.stat().st_mode), mode)

    def test_shared_answer_directory_is_rejected(self) -> None:
        parent = self.root / 'shared'
        parent.mkdir(mode=0o700)
        answer = private_answer(parent / 'answer.md')
        for mode in (0o755, 0o770, 0o1777):
            parent.chmod(mode)
            with self.subTest(mode=oct(mode)), self.assertRaisesRegex(MODULE.ReviewError, '0700'):
                self.read_answer(answer)
            self.assertEqual(stat.S_IMODE(parent.stat().st_mode), mode)

    def test_wrong_file_or_directory_owner_is_rejected(self) -> None:
        answer = private_answer(self.root / 'answer.md')
        original = os.fstat
        for kind in ('file', 'directory'):
            def foreign_owner(fd: int) -> os.stat_result:
                info = original(fd)
                if stat.S_ISDIR(info.st_mode) == (kind == 'directory'):
                    values = list(info)
                    values[4] = os.geteuid() + 1
                    return os.stat_result(values)
                return info
            with self.subTest(kind=kind), mock.patch.object(MODULE.os, 'fstat', side_effect=foreign_owner):
                with self.assertRaisesRegex(MODULE.ReviewError, 'owned by the current user'):
                    self.read_answer(answer)

    def test_answer_symlinks_directories_and_fifos_are_rejected(self) -> None:
        answer = private_answer(self.root / 'answer.md')
        link = self.root / 'link.md'
        link.symlink_to(answer)
        with self.assertRaisesRegex(MODULE.ReviewError, 'symlink'):
            self.read_answer(link)
        directory = self.root / 'directory'
        directory.mkdir(mode=0o700)
        with self.assertRaisesRegex(MODULE.ReviewError, 'regular file'):
            self.read_answer(directory)
        fifo = self.root / 'fifo'
        os.mkfifo(fifo, mode=0o600)
        with self.assertRaisesRegex(MODULE.ReviewError, 'regular file'):
            self.read_answer(fifo)
        parent_link = self.root / 'linked-directory'
        parent_link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(MODULE.ReviewError, 'symlink'):
            self.read_answer(parent_link / answer.name)

    def simulate_publish(self, changes: dict | None = None, *, create: bool = False,
                         expected_error: str | None = None) -> list:
        repo = self.repository()
        head = commit_file(repo, 'a.txt', 'safe fixture', 'base')
        prompt = self.root / 'prompt.txt'
        prompt.write_text('synthetic review prompt')
        marker = MODULE.DESCRIPTION_PREFIX + MODULE.project_key(repo.resolve())
        mirror = 'tester/private-project'
        metadata = mirror_metadata(mirror, marker, **(changes or {}))
        calls = []
        exists = not create
        original = subprocess.run
        def service(command_args: list, **kwargs: object) -> subprocess.CompletedProcess:
            nonlocal exists
            if command_args[0] == 'gh':
                calls.append(command_args)
                self.assertEqual(kwargs['env']['GH_HOST'], 'github.com')
                if command_args[1] == 'api':
                    self.assertEqual(command_args[2:4], ['--hostname', 'github.com'])
                    args = command_args[4:]
                    if args == ['user', '--jq', '.login']:
                        return subprocess.CompletedProcess(command_args, 0, 'tester\n', '')
                    if args[0] == '--method':
                        self.assertEqual(args[:3], ['--method', 'PATCH', f'repos/{mirror}'])
                        return subprocess.CompletedProcess(command_args, 0, '{}', '')
                    if args[0] == f'repos/{mirror}/git/ref/heads/main':
                        return subprocess.CompletedProcess(command_args, 0, head+'\n', '')
                    self.assertEqual(args, [f'repos/{mirror}'])
                    return subprocess.CompletedProcess(command_args, 0 if exists else 1,
                                                       json.dumps(metadata) if exists else '', '' if exists else '404 Not Found')
                if command_args[1:3] == ['repo', 'create']:
                    self.assertEqual(command_args[3], mirror)
                    self.assertIn('--private', command_args)
                    exists = True
                    return subprocess.CompletedProcess(command_args, 0, '', '')
                self.assertEqual(command_args[1:], ['auth', 'status', '--hostname', 'github.com'])
                return subprocess.CompletedProcess(command_args, 0, '', '')
            if command_args[0] == 'git' and command_args[1] in {'ls-remote', 'push'}:
                calls.append(command_args)
                remote = command_args[2] if command_args[1] == 'ls-remote' else command_args[3]
                self.assertTrue(remote.startswith(f'{MODULE.MANAGER}-upload-'))
                options = ['--push'] if command_args[1] == 'push' else []
                resolved = original(['git', 'remote', 'get-url', *options, '--all', remote],
                                    cwd=kwargs['cwd'], check=True, capture_output=True, text=True)
                self.assertEqual(resolved.stdout, f'https://github.com/{mirror}.git\n')
                return subprocess.CompletedProcess(command_args, 0, '', '')
            if command_args[:3] != ['git', 'remote', 'add'] and command_args[0] == 'git' and any(str(a).startswith(('https://', 'git@')) for a in command_args[1:]):
                raise AssertionError(f'unexpected network command: {command_args}')
            return original(command_args, **kwargs)
        args = SimpleNamespace(repo=str(repo), prompt_file=str(prompt), state_root=str(self.root/'state'),
                               mode='review', binding='source-chip', include_working_tree=False,
                               mirror=mirror, allow_sensitive_path=[], dry_run=False)
        with mock.patch.dict(os.environ, {'GH_HOST': 'enterprise.example.invalid'}):
            with mock.patch.object(MODULE.subprocess, 'run', side_effect=service), redirect_stdout(io.StringIO()):
                if expected_error:
                    with self.assertRaisesRegex(MODULE.ReviewError, expected_error):
                        MODULE.command_publish(args)
                else:
                    MODULE.command_publish(args)
                    run_dir = next((self.root/'state/runs').iterdir())
                    evidence = MODULE.verify_remote_review_commit(run_dir, MODULE.load_run(run_dir))
                    self.assertEqual(evidence['review_commit'], head)
            self.assertEqual(os.environ['GH_HOST'], 'enterprise.example.invalid')
        pushes = [c for c in calls if c[:2] == ['git', 'push']]
        if expected_error:
            self.assertFalse(pushes)
        else:
            self.assertTrue(pushes)
            self.assertLess(next(i for i,c in enumerate(calls) if c[0]=='gh' and f'repos/{mirror}' in c),
                            next(i for i,c in enumerate(calls) if c[:2]==['git','push']))
        return calls

    def test_git_rewrites_cannot_upload_to_an_unverified_repository(self) -> None:
        for rewrite in ('insteadOf', 'pushInsteadOf'):
            with self.subTest(rewrite=rewrite):
                repo = self.repository(rewrite)
                head = commit_file(repo, 'repository.txt', 'synthetic private payload', 'base')
                before = command('git', 'status', '--porcelain=v1', cwd=repo)
                destination = self.root / f'{rewrite}-unverified.git'
                init_repo(destination, bare=True)
                config = self.root / f'{rewrite}.gitconfig'
                mirror = 'tester/private-project'
                command('git', 'config', '--file', str(config),
                        f'url.{destination.as_uri()}.{rewrite}',
                        f'https://github.com/{mirror}.git', cwd=self.root)
                prompt = self.root / f'{rewrite}-prompt.txt'
                prompt.write_text('synthetic review prompt')
                state_root = self.root / f'{rewrite}-state'
                marker = MODULE.DESCRIPTION_PREFIX + MODULE.project_key(repo.resolve())
                args = SimpleNamespace(repo=str(repo), prompt_file=str(prompt), state_root=str(state_root),
                                       mode='review', binding='source-chip', include_working_tree=False,
                                       mirror=mirror, allow_sensitive_path=[], dry_run=False)
                with mock.patch.dict(os.environ, {
                    'GIT_CONFIG_GLOBAL': str(config), 'GIT_CONFIG_NOSYSTEM': '1',
                    'GIT_ALLOW_PROTOCOL': 'file', 'GIT_TERMINAL_PROMPT': '0',
                }), mock.patch.object(MODULE, 'active_github_owner', return_value='tester'), \
                    mock.patch.object(MODULE, 'github_repo_info', return_value=mirror_metadata(mirror, marker)), \
                    mock.patch.object(MODULE, 'github', side_effect=AssertionError('unexpected service call')), \
                    mock.patch.object(MODULE, 'remote_refs', return_value={}) as remote_read, \
                    redirect_stdout(io.StringIO()):
                    # Git push is real and allowed to write the local bare repo.
                    # The target guard must fail before remote read or any push.
                    with self.assertRaisesRegex(MODULE.ReviewError, 'effective Git .* URL'):
                        MODULE.command_publish(args)
                    remote_read.assert_not_called()
                self.assertEqual(command('git', 'for-each-ref', cwd=destination), '')
                self.assertEqual(command('git', 'rev-parse', 'HEAD', cwd=repo), head)
                self.assertEqual(command('git', 'status', '--porcelain=v1', cwd=repo), before)
                self.assertEqual(command('git', 'remote', cwd=repo), '')
                run_dir = next((state_root / 'runs').iterdir())
                self.assertEqual(MODULE.load_run(run_dir)['status'], 'failed')

    def test_same_github_repository_transport_rewrites_remain_supported(self) -> None:
        mirror = 'tester/private-project'
        for index, target in enumerate((
            'https://github.com/tester/private-project.git',
            'https://github.com:443/Tester/Private-Project',
            'git@github.com:tester/private-project.git',
            'ssh://git@github.com/tester/private-project',
            'ssh://git@github.com:22/tester/private-project.git',
        )):
            for rewrite in ('insteadOf', 'pushInsteadOf'):
                with self.subTest(target=target, rewrite=rewrite):
                    repo = self.repository(f'transport-{index}-{rewrite}')
                    command('git', 'config', f'url.{target}.{rewrite}',
                            f'https://github.com/{mirror}.git', cwd=repo)
                    remote = MODULE.verified_upload_remote(repo, mirror, 'fixture')
                    self.assertEqual(command('git', 'remote', 'get-url', '--push', '--all', remote, cwd=repo), target)

    def test_git_destination_identity_and_single_url_are_required(self) -> None:
        mirror = 'tester/private-project'
        for index, target in enumerate((
            'https://example.invalid/tester/private-project.git',
            'https://github.com/other/private-project.git',
            'https://github.com/tester/other.git',
            'http://github.com/tester/private-project.git',
            'https://user:synthetic-password@github.com/tester/private-project.git',
            'ssh://other@github.com/tester/private-project.git',
            'https://github.com/tester/private-project.git?other',
            'https://github.com/tester/private-project.git\n',
            'https://github.com/tester/private-project.git\r',
        )):
            with self.subTest(target=target):
                repo = self.repository(f'bad-target-{index}')
                original_git = MODULE.git
                def add_pushurl(*args, **kwargs):
                    result = original_git(*args, **kwargs)
                    if args[1:3] == ('remote', 'add'):
                        # Git permits control characters in URL values even
                        # when a URL rewrite subsection cannot contain them.
                        command('git', 'config', f'remote.{args[3]}.pushurl', target, cwd=repo)
                    return result
                with mock.patch.object(MODULE, 'git', side_effect=add_pushurl):
                    with self.assertRaisesRegex(MODULE.ReviewError, 'effective Git push URL') as raised:
                        MODULE.verified_upload_remote(repo, mirror, 'fixture')
                self.assertNotIn(target, str(raised.exception))
                self.assertNotIn('synthetic-password', str(raised.exception))
        for direction in ('url', 'pushurl'):
            with self.subTest(direction=direction):
                repo = self.repository(f'multiple-{direction}')
                original_git = MODULE.git
                def add_duplicate(*args, **kwargs):
                    result = original_git(*args, **kwargs)
                    if args[1:3] == ('remote', 'add'):
                        command('git', 'config', '--add', f'remote.{args[3]}.{direction}',
                                f'https://github.com/{mirror}.git', cwd=repo)
                        if direction == 'pushurl':
                            command('git', 'config', '--add', f'remote.{args[3]}.{direction}',
                                    'https://github.com/other/unverified.git', cwd=repo)
                    return result
                with mock.patch.object(MODULE, 'git', side_effect=add_duplicate):
                    with self.assertRaisesRegex(MODULE.ReviewError, 'effective Git .* URL'):
                        MODULE.verified_upload_remote(repo, mirror, 'fixture')

    def test_abnormal_gh_host_still_publishes_and_reads_back_only_github_com(self) -> None:
        self.simulate_publish()

    def test_repository_creation_pins_host_without_changing_user_environment(self) -> None:
        calls = self.simulate_publish(create=True)
        self.assertEqual(sum(c[1:3] == ['repo', 'create'] for c in calls), 1)

    def test_same_name_public_repository_is_rejected_before_push(self) -> None:
        self.simulate_publish({'private': False}, expected_error='non-private')

    def test_wrong_repository_owner_is_rejected_before_push(self) -> None:
        self.simulate_publish({'owner': {'login': 'other'}}, expected_error='identity mismatch')

    def test_wrong_repository_name_is_rejected_before_push(self) -> None:
        self.simulate_publish({'name': 'other'}, expected_error='identity mismatch')

    def test_wrong_management_marker_is_rejected_before_push(self) -> None:
        self.simulate_publish({'description': 'another project'}, expected_error='management marker')

    def test_canonical_repository_fields_and_identifier_are_fail_closed(self) -> None:
        mirror = 'tester/private-project'
        for change in ({'full_name': 'tester/other'}, {'html_url': 'https://enterprise.example.invalid/tester/private-project'},
                       {'owner': None}, {'private': 'true'}):
            with self.subTest(change=change), self.assertRaises(MODULE.ReviewError):
                MODULE.validate_mirror_info(mirror, 'fixture', mirror_metadata(mirror, 'fixture', **change))
        for invalid in ('tester/../other', 'tester/repo?redirect=elsewhere', 'tester/..', 'tester/repo\n'):
            with self.subTest(invalid=invalid), mock.patch.object(MODULE, 'github') as github:
                with self.assertRaises(MODULE.ReviewError):
                    MODULE.github_repo_info(invalid)
                github.assert_not_called()




class UploadFirstTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "project"
        self.remote = self.root / "remote.git"
        init_repo(self.repo)
        init_repo(self.remote, bare=True)
        command("git", "branch", "-M", "main", cwd=self.repo)
        self.first = commit_file(self.repo, "value.txt", "one\n", "one")
        self.state_root = self.root / "state"
        self.mirror = "tester/project-private-backup"
        self.info = None
        self.creations = 0
        self.transfers = 0
        self.request = self.root / "request.txt"
        self.request.write_bytes("检查边界，不要改写。\r\n  exact trailing spaces  \n".encode())
        for name, target in (
            ("active_github_owner", lambda: "tester"),
            ("github_repo_info", lambda mirror: self.info),
            ("github", self.fake_github),
            ("verified_upload_remote", self.upload_remote),
        ):
            patch = mock.patch.object(MODULE, name, side_effect=target)
            patch.start()
            self.addCleanup(patch.stop)

    def fake_github(self, *args: str, **kwargs: object):
        if args[:2] == ("repo", "create"):
            self.creations += 1
            marker = MODULE.DESCRIPTION_PREFIX + MODULE.project_key(self.repo.resolve())
            self.info = mirror_metadata(self.mirror, marker)
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:3] == ("api", "--method", "PATCH"):
            self.info["default_branch"] = args[-1].split("=", 1)[1]
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:1] == ("api",) and "/git/ref/heads/" in args[1]:
            branch = args[1].split("/git/ref/heads/", 1)[1]
            sha = command("git", "--git-dir", str(self.remote), "rev-parse", "refs/heads/" + branch, cwd=self.root)
            return subprocess.CompletedProcess(args, 0, sha + "\n", "")
        self.fail(f"unexpected mocked GitHub call: {args}")

    def upload_remote(self, *args, **kwargs):
        self.transfers += 1
        return str(self.remote)

    def cli(self, *args: str) -> dict:
        parsed = MODULE.build_parser().parse_args(args)
        output = io.StringIO()
        with redirect_stdout(output):
            parsed.func(parsed)
        return json.loads(output.getvalue())

    def publish(self, *extra: str) -> dict:
        return self.cli("publish", "--repo", str(self.repo), "--state-root", str(self.state_root),
                        "--mirror", self.mirror, *extra)

    def prepare(self, run: dict, mode: str = "pro", *extra: str) -> dict:
        return self.cli("prepare-review", "--run-dir", run["run_dir"], "--mode", mode,
                        "--prompt-file", str(self.request), *extra)

    def test_upload_then_freeze_link_preserves_request_and_upload_receipts(self) -> None:
        uploaded = self.publish()
        run_dir = Path(uploaded["run_dir"])
        self.assertEqual(uploaded["status"], "uploaded")
        self.assertFalse((run_dir / "prompt.txt").exists())
        self.assertIsNone(MODULE.load_run(run_dir)["mode"])
        receipts = {p: (run_dir / p).read_bytes() for p in ("source-manifest.json", "publish-result.json")}
        prepared = self.prepare(uploaded)
        self.assertEqual((prepared["status"], prepared["mode"], prepared["binding"]),
                         ("published", "pro", "raw-url"))
        original = self.request.read_bytes()
        self.assertEqual((run_dir / "request.txt").read_bytes(), original)
        self.assertEqual((run_dir / "prompt.txt").read_bytes(),
                         f"https://github.com/{self.mirror}\n\n".encode() + original)
        for name, content in receipts.items():
            self.assertEqual((run_dir / name).read_bytes(), content)
        MODULE.verify_published_identity(run_dir, MODULE.load_run(run_dir))
        with self.assertRaisesRegex(MODULE.ReviewError, "requires uploaded"):
            self.prepare(uploaded)
        self.assertEqual(self.creations, 1)

    def test_prepare_rejects_live_drift_and_changed_original_bytes(self) -> None:
        uploaded = self.publish()
        self.info["private"] = False
        with self.assertRaises(MODULE.ReviewError):
            self.prepare(uploaded)
        self.info["private"] = True
        self.info["default_branch"] = "other"
        with self.assertRaisesRegex(MODULE.ReviewError, "branch drift"):
            self.prepare(uploaded)
        self.info["default_branch"] = "main"
        prepared = self.prepare(uploaded)
        run_dir = Path(uploaded["run_dir"])
        (run_dir / "request.txt").write_bytes(b"changed request")
        with self.assertRaisesRegex(MODULE.ReviewError, "request byte drift"):
            MODULE.verify_prompt_snapshot(run_dir, prepared)

    def test_ambiguous_request_gets_verified_url_before_composer_ready(self) -> None:
        url = f"https://github.com/{self.mirror}"
        for reference in (url + "-old", "https://example.invalid/?repo=" + url,
                          "[ " + url + " ](https://example.invalid/)",
                          "[\n" + url + "\n](https://example.invalid/)", url):
            with self.subTest(reference=reference):
                original = ("Review " + reference + "\r\n原文不改。  \n").encode()
                self.request.write_bytes(original)
                uploaded = self.publish()
                run_dir = Path(uploaded["run_dir"])
                receipts = {name: (run_dir / name).read_bytes()
                            for name in ("source-manifest.json", "publish-result.json")}
                state = self.prepare(uploaded)
                self.assertEqual((run_dir / "request.txt").read_bytes(), original)
                self.assertEqual((run_dir / "prompt.txt").read_bytes(), url.encode() + b"\n\n" + original)
                for name, content in receipts.items():
                    self.assertEqual((run_dir / name).read_bytes(), content)
                base = ("--run-dir", str(run_dir))
                self.cli("tab", *base, "--action", "register", "--tab-id", "chat", "--url", "https://chatgpt.com/")
                self.cli("tab", *base, "--action", "activate", "--tab-id", "chat")
                self.cli("event", *base, "--event", "source-bound", "--capability-label", "Pro",
                         "--deep-research", "inactive", "--app-grant", "verified", "--binding", "raw-url",
                         "--repository", self.mirror, "--default-branch", state["review_branch"],
                         "--commit", state["review_commit"], "--tab-id", "chat")
                ready = self.cli("event", *base, "--event", "composer-ready", "--prompt-sha256", state["prompt_sha256"],
                                 "--fill-method", "single-operation", "--tab-id", "chat")
                self.assertEqual(ready["status"], "composer-ready")
                MODULE.verify_published_identity(run_dir, MODULE.load_run(run_dir))
                self.cli("end", *base, "--observed", "not-submitted", "--reason", "synthetic test completed")

    def test_both_modes_complete_without_a_second_send_or_wait(self) -> None:
        for mode, research, container in (("pro", "inactive", "assistant-turn"),
                                           ("review", "active", "deep-research-report")):
            with self.subTest(mode=mode):
                state = self.prepare(self.publish(), mode)
                run_dir = state["run_dir"]
                base = ("--run-dir", run_dir)
                self.cli("tab", *base, "--action", "register", "--tab-id", "chat", "--url", "https://chatgpt.com/")
                self.cli("tab", *base, "--action", "activate", "--tab-id", "chat")
                self.cli("event", *base, "--event", "source-bound", "--capability-label", "Pro",
                         "--deep-research", research, "--app-grant", "verified", "--binding", "raw-url",
                         "--repository", self.mirror, "--default-branch", state["review_branch"],
                         "--commit", state["review_commit"], "--tab-id", "chat")
                self.cli("event", *base, "--event", "composer-ready", "--prompt-sha256", state["prompt_sha256"],
                         "--fill-method", "single-operation", "--tab-id", "chat")
                conversation = "https://chatgpt.com/c/" + mode
                self.cli("event", *base, "--event", "submitted", "--conversation-url", conversation,
                         "--submission-method", "send-button", "--tab-id", "chat")
                self.cli("event", *base, "--event", "wait-start", "--generation-sentinel", "stop", "--tab-id", "chat")
                self.cli("event", *base, "--event", "pending")
                self.cli("event", *base, "--event", "wait-complete", "--generation-sentinel", "stop",
                         "--completion-proof", MODULE.COMPLETION_PROOF, "--final-container", container, "--tab-id", "chat")
                answer = private_answer(self.root / f"answer-{mode}.md")
                result = self.cli("collect", *base, "--answer-file", str(answer),
                                  "--answer-sha256", MODULE.sha256_bytes(answer.read_bytes()),
                                  "--source-kind", container, "--source-conversation-url", conversation, "--source-tab-id", "chat")
                self.assertEqual((result["status"], result["wait_count"], result["reconnect_count"]),
                                 ("collected", 1, 0))
                commit_file(self.repo, "value.txt", mode + "\n", "after review " + mode)
        self.assertEqual(self.creations, 1)
        self.assertEqual(self.transfers, 2)

    def test_next_review_reuses_mirror_and_new_commit_after_end(self) -> None:
        uploaded = self.publish()
        before_map = (self.state_root / "projects.json").read_bytes()
        self.cli("end", "--run-dir", uploaded["run_dir"], "--observed", "not-submitted", "--reason", "new scope")
        self.assertEqual((self.state_root / "projects.json").read_bytes(), before_map)
        second = commit_file(self.repo, "value.txt", "two\n", "two")
        result = self.publish()
        self.assertEqual(result["mirror"], uploaded["mirror"])
        self.assertEqual(result["review_commit"], second)
        self.assertEqual(self.creations, 1)
        self.assertNotEqual(result["run_id"], uploaded["run_id"])
        self.assertEqual(command("git", "--git-dir", str(self.remote), "rev-parse", "main", cwd=self.root), second)

    def test_active_upload_entrypoint_returns_resume_without_touching_remote(self) -> None:
        uploaded = self.publish()
        self.request.unlink()  # No new Prompt is necessary for routing back.
        with mock.patch.object(MODULE, "active_github_owner", side_effect=AssertionError("no auth call")), \
             mock.patch.object(MODULE, "prepare_staging_repository", side_effect=AssertionError("no staging")):
            resumed = self.publish()
        self.assertEqual((resumed["status"], resumed["upload_performed"]), ("resume-required", False))
        self.assertEqual(resumed["runs"][0]["run_id"], uploaded["run_id"])
        self.assertEqual(resumed["runs"][0]["next_action"], "prepare-review")
        self.assertEqual(self.transfers, 1)

    def test_explicit_wip_and_committed_only_have_different_payloads(self) -> None:
        (self.repo / "value.txt").write_text("working tree\n")
        (self.repo / "extra.txt").write_text("untracked\n")
        with self.assertRaisesRegex(MODULE.ReviewError, "choose --include-working-tree or --committed-only"):
            self.publish()
        committed = self.publish("--committed-only")
        self.assertEqual(committed["review_commit"], self.first)
        self.cli("end", "--run-dir", committed["run_dir"], "--observed", "not-submitted", "--reason", "include WIP now")
        wip = self.publish("--include-working-tree")
        self.assertNotEqual(wip["review_commit"], self.first)
        value = command("git", "--git-dir", str(self.remote), "show", wip["review_commit"] + ":extra.txt", cwd=self.root)
        self.assertEqual(value, "untracked")
        self.assertEqual(command("git", "rev-parse", "HEAD", cwd=self.repo), self.first)
        self.assertEqual((self.repo / "value.txt").read_text(), "working tree\n")

    def test_raw_link_not_duplicated_and_source_chip_remains_available(self) -> None:
        url = f"https://github.com/{self.mirror}".encode()
        for original in (url, url + b"\nexact words", url + b"\r\nexact words"):
            with self.subTest(original=original):
                self.assertEqual(MODULE.compose_review_prompt(original, self.mirror, "raw-url"), original)
        inline = b"Review " + url + b"\nexact words"
        self.assertEqual(MODULE.compose_review_prompt(inline, self.mirror, "raw-url"),
                         url + b"\n\n" + inline)
        uploaded = self.publish()
        state = self.prepare(uploaded, "review", "--binding", "source-chip")
        self.assertEqual((Path(uploaded["run_dir"]) / "prompt.txt").read_bytes(), self.request.read_bytes())
        self.assertEqual(state["binding"], "source-chip")

    def test_legacy_pair_and_dry_run_cannot_silently_prepare(self) -> None:
        for extra in (("--mode", "pro"), ("--prompt-file", str(self.request))):
            with self.assertRaisesRegex(MODULE.ReviewError, "both"):
                self.publish(*extra)
        result = self.publish("--dry-run")
        with self.assertRaisesRegex(MODULE.ReviewError, "requires uploaded"):
            self.prepare(result)
        self.assertEqual(self.creations, 0)

    def test_interrupted_upload_reserves_mirror_and_requires_end(self) -> None:
        with mock.patch.object(MODULE, "publish_backup", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.publish()
        run_dir = next((self.state_root / "runs").iterdir())
        state = MODULE.load_run(run_dir)
        self.assertEqual((state["status"], state["mirror"]), ("preparing", self.mirror))
        self.assertEqual(MODULE.load_project_map(self.state_root)["projects"][str(self.repo.resolve())]["mirror"], self.mirror)
        self.assertEqual(self.publish()["status"], "resume-required")
        self.cli("end", "--run-dir", str(run_dir), "--observed", "not-submitted", "--reason", "publisher interrupted")
        self.publish()
        self.assertEqual(self.creations, 1)

    def test_end_rejects_live_upload_and_legacy_requires_observed_stopped(self) -> None:
        run_dir = MODULE.create_run(self.state_root, self.repo, None, None, "lock-test", None)
        state = MODULE.load_run(run_dir)
        state["publisher_lock"] = "flock-v1"
        MODULE.save_run(run_dir, state)
        args = ("end", "--run-dir", str(run_dir), "--observed", "not-submitted", "--reason", "interrupted")
        with MODULE.upload_execution(run_dir):
            with self.assertRaisesRegex(MODULE.ReviewError, "still running"):
                self.cli(*args)
        state["publisher_lock"] = None
        MODULE.save_run(run_dir, state)
        with self.assertRaisesRegex(MODULE.ReviewError, "--publisher-stopped"):
            self.cli(*args)
        self.cli(*args, "--publisher-stopped")
        self.assertEqual(MODULE.load_run(run_dir)["status"], "ended")

    def test_warning_cannot_release_a_publisher_or_an_upload_only_run(self) -> None:
        run_dir = MODULE.create_run(self.state_root, self.repo, None, None, "warning-upload", None)
        with MODULE.upload_execution(run_dir):
            with self.assertRaisesRegex(MODULE.ReviewError, "browser phase"):
                self.cli("event", "--run-dir", str(run_dir), "--event", "warning", "--message", "interrupted")
            result = self.publish()
            self.assertEqual(result["status"], "resume-required")
            self.assertEqual(self.transfers, 0)
            self.assertTrue(MODULE.active_runs_for_source(self.state_root, self.repo))
        state = MODULE.load_run(run_dir)
        for status in ("uploaded", "prepared"):
            state["status"] = status
            MODULE.save_run(run_dir, state)
            with self.assertRaisesRegex(MODULE.ReviewError, "browser phase"):
                self.cli("event", "--run-dir", str(run_dir), "--event", "warning")

    def test_transfer_child_retains_lease_after_publisher_is_killed(self) -> None:
        run_dir = MODULE.create_run(self.state_root, self.repo, None, None, "killed-publisher", None)
        state = MODULE.load_run(run_dir)
        state["publisher_lock"] = "flock-v1"
        MODULE.save_run(run_dir, state)
        child_ready = self.root / "child-ready"
        child_release = self.root / "child-release"
        child_done = self.root / "child-done"
        child_code = "\n".join((
            "import pathlib,sys,time", "ready,release,done=map(pathlib.Path,sys.argv[1:])",
            "ready.write_text('ready')", "deadline=time.monotonic()+15",
            "while not release.exists() and time.monotonic()<deadline: time.sleep(0.02)",
            "done.write_text('done')"))
        parent_code = "\n".join((
            "import importlib.util,pathlib,sys", "spec=importlib.util.spec_from_file_location('pgpr',sys.argv[1])",
            "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)",
            "with m.upload_execution(pathlib.Path(sys.argv[2])):",
            "    m.run([sys.executable,'-c',sys.argv[3],*sys.argv[4:]])"))
        parent = subprocess.Popen([sys.executable, "-c", parent_code, str(SCRIPT), str(run_dir),
                                   child_code, str(child_ready), str(child_release), str(child_done)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        args = ("end", "--run-dir", str(run_dir), "--observed", "not-submitted", "--reason", "publisher killed")
        try:
            deadline = time.monotonic() + 5
            while not child_ready.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(child_ready.exists())
            parent.kill()
            parent.wait(timeout=3)
            with self.assertRaisesRegex(MODULE.ReviewError, "still running"):
                self.cli(*args)
            child_release.touch()
            deadline = time.monotonic() + 5
            while not child_done.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(child_done.exists())
            # done is written just before exit; retry the nonblocking lock only.
            while True:
                try:
                    result = self.cli(*args)
                    break
                except MODULE.ReviewError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.02)
            self.assertEqual(result["status"], "ended")
        finally:
            child_release.touch()
            if parent.poll() is None:
                parent.kill()
            parent.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()
