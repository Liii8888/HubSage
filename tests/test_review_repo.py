from __future__ import annotations

import importlib.util
import io
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
            if command_args[:3] == ["gh", "api", "user"]:
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
        self.assertEqual(
            MODULE.require_raw_repository_url(
                f"请审查 {expected}\n".encode("utf-8"), mirror
            ),
            expected,
        )
        with self.assertRaisesRegex(MODULE.ReviewError, "exact private repository URL"):
            MODULE.require_raw_repository_url(b"review this repository\n", mirror)


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
        answer.write_text("final answer\n", encoding="utf-8")
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
                return_value={
                    "private": True,
                    "default_branch": "main",
                    "description": MODULE.DESCRIPTION_PREFIX
                    + MODULE.project_key(self.repo.resolve()),
                },
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
                return_value={
                    "private": True,
                    "default_branch": "main",
                    "description": "different manager",
                },
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
        state = MODULE.load_run(self.run_dir)
        state["binding"] = "raw-url"
        state["binding_assurance"] = "raw-url-reference-only-v1"
        MODULE.save_run(self.run_dir, state)
        manifest = MODULE.read_json(self.run_dir / "source-manifest.json")
        manifest["binding"] = "raw-url"
        MODULE.write_json(self.run_dir / "source-manifest.json", manifest)
        published = MODULE.read_json(self.run_dir / "publish-result.json")
        published["binding"] = "raw-url"
        published["binding_assurance"] = "raw-url-reference-only-v1"
        published["raw_repository_url"] = "https://github.com/tester/private-project"
        MODULE.write_json(self.run_dir / "publish-result.json", published)

        self.bind_source(binding="raw-url")
        after = MODULE.load_run(self.run_dir)
        self.assertEqual(after["source_index"], "not-applicable")
        self.assertEqual(after["binding_assurance"], "raw-url-reference-only-v1")
        self.assertEqual(after["github_app_auth"]["status"], "verified")

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
        answer.write_text("final answer\n", encoding="utf-8")
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
        with redirect_stdout(io.StringIO()):
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


if __name__ == "__main__":
    os.umask(0o077)
    unittest.main()
