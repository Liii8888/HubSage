from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("export_skill", ROOT / "scripts/export_skill.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class DistributionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "source"
        self.repo.mkdir()
        for relative in MODULE.PAYLOAD:
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        self.git("init", "-q")
        self.git("config", "user.name", "Distribution Test")
        self.git("config", "user.email", "distribution@example.invalid")
        self.git("add", ".")
        self.git("commit", "-qm", "reviewed snapshot")
        self.ref = self.git("rev-parse", "HEAD")

    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.repo, check=True, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()

    def export(self, name: str = "snapshot", local: str | None = None) -> Path:
        destination = self.root / name
        MODULE.export_snapshot(self.repo, self.ref, destination, local)
        MODULE.verify_snapshot(self.repo, self.ref, destination, local)
        return destination

    def test_export_is_reproducible_and_pinned_despite_source_head_and_worktree_changes(self) -> None:
        first = self.export("first")
        skill = self.repo / "SKILL.md"
        skill.write_text(skill.read_text() + "\nA later source change.\n")
        self.git("add", "SKILL.md")
        self.git("commit", "-qm", "later source")
        skill.write_text("uncommitted content must not be exported")
        second = self.export("second")
        for relative in [*MODULE.PAYLOAD, "DISTRIBUTION.json", "UPSTREAM.md"]:
            self.assertEqual((first / relative).read_bytes(), (second / relative).read_bytes())
        MODULE.verify_snapshot(self.repo, self.ref, first)

    def test_readme_install_executes_reviewed_exporter_after_default_branch_advances(self) -> None:
        exporter = self.repo / "scripts/export_skill.py"
        # The exporter is part of the pinned distribution payload itself.
        reviewed = self.ref
        marker = self.root / "unreviewed-exporter-executed"
        exporter.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\nraise SystemExit(91)\n")
        self.git("add", "scripts/export_skill.py")
        self.git("commit", "-qm", "later unreviewed exporter")
        default_head = self.git("rev-parse", "HEAD")
        installed = self.root / "installed"
        result = self.install_from_readme(reviewed)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(reviewed, default_head)
        self.assertFalse(marker.exists())
        checkout = self.root / "private-github-pro-review"
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=checkout, text=True).strip()
        self.assertEqual(head, reviewed)
        MODULE.verify_snapshot(self.repo, reviewed, installed)

    def install_from_readme(self, reviewed: str) -> subprocess.CompletedProcess[str]:
        # Run the actual recipe with ordinary shell defaults, not an extra -e
        # that could conceal a missing short-circuit in the documentation.
        installed = self.root / "installed"
        recipe = (ROOT / "README.md").read_text().split("```bash\n", 1)[1].split("```", 1)[0]
        recipe, pins = re.subn(
            r"(?m)^  PGPR_REVIEWED_SHA=[0-9a-f]{40} &&$",
            f"  PGPR_REVIEWED_SHA={reviewed} &&", recipe,
        )
        self.assertEqual(pins, 1, "install recipe must pin one full reviewed SHA")
        recipe = recipe.replace("https://github.com/Liii8888/private-github-pro-review.git", shlex.quote(str(self.repo)))
        recipe = recipe.replace('"$HOME/.agents/skills/private-github-pro-review"', shlex.quote(str(installed)))
        recipe = recipe.replace("python3 scripts/", shlex.quote(sys.executable) + " scripts/")
        return subprocess.run(["bash", "-c", recipe], cwd=self.root, capture_output=True, text=True)

    def test_readme_install_stops_when_stale_checkout_already_exists(self) -> None:
        exporter = self.repo / "scripts/export_skill.py"
        marker = self.root / "stale-exporter-executed"
        exporter.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
        self.git("add", "scripts/export_skill.py")
        self.git("commit", "-qm", "old unreviewed exporter")
        stale_head = self.git("rev-parse", "HEAD")
        stale = self.root / "private-github-pro-review"
        subprocess.run(["git", "clone", "--quiet", str(self.repo), str(stale)], check=True)
        shutil.copyfile(ROOT / "scripts/export_skill.py", exporter)
        self.git("add", "scripts/export_skill.py")
        self.git("commit", "-qm", "new reviewed exporter")
        reviewed = self.git("rev-parse", "HEAD")
        result = self.install_from_readme(reviewed)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(marker.exists())
        self.assertFalse((self.root / "installed").exists())
        self.assertEqual(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=stale, text=True).strip(), stale_head)

    def test_readme_install_stops_when_reviewed_sha_is_unavailable(self) -> None:
        exporter = self.repo / "scripts/export_skill.py"
        marker = self.root / "default-exporter-executed"
        exporter.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
        self.git("add", "scripts/export_skill.py")
        self.git("commit", "-qm", "unreviewed default exporter")
        reviewed_repo = self.root / "reviewed-source"
        subprocess.run(["git", "clone", "--quiet", str(self.repo), str(reviewed_repo)], check=True)
        shutil.copyfile(ROOT / "scripts/export_skill.py", reviewed_repo / "scripts/export_skill.py")
        subprocess.run(["git", "add", "scripts/export_skill.py"], cwd=reviewed_repo, check=True)
        subprocess.run(["git", "-c", "user.name=Distribution Test", "-c", "user.email=distribution@example.invalid",
                        "commit", "-qm", "reviewed but unavailable in origin"], cwd=reviewed_repo, check=True)
        reviewed = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=reviewed_repo, text=True).strip()
        result = self.install_from_readme(reviewed)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unable to read tree", result.stderr)
        self.assertNotIn("can't open file", result.stderr)
        self.assertFalse(marker.exists())
        self.assertFalse((self.root / "installed").exists())

    def test_local_default_is_the_only_adaptation_and_explicit_environment_still_wins(self) -> None:
        local = str(self.root / 'legacy state "quoted"')
        public = self.export("public")
        installed = self.export("installed", local)
        changed = [p for p in MODULE.PAYLOAD if (public/p).read_bytes() != (installed/p).read_bytes()]
        self.assertEqual(changed, ["scripts/review_repo.py"])
        script = installed / "scripts/review_repo.py"
        probe = "import runpy,sys; print(runpy.run_path(sys.argv[1])['DEFAULT_STATE_ROOT'])"
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "XDG_STATE_HOME": str(self.root / "xdg")}
        env.pop("PRIVATE_GITHUB_PRO_REVIEW_HOME", None)
        for configured, expected in [(None, local), (str(self.root / "explicit"), str(self.root / "explicit"))]:
            current = dict(env)
            if configured: current["PRIVATE_GITHUB_PRO_REVIEW_HOME"] = configured
            result = subprocess.run([sys.executable, "-c", probe, str(script)], env=current,
                                    capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout.strip(), expected)
        with self.assertRaises(MODULE.DistributionError):
            MODULE.verify_snapshot(self.repo, self.ref, installed)
        with self.assertRaises(MODULE.DistributionError):
            MODULE.verify_snapshot(self.repo, self.ref, installed, str(self.root / "unapproved"))

    def test_existing_destination_is_preserved(self) -> None:
        snapshot = self.export()
        original = (snapshot / "DISTRIBUTION.json").read_bytes()
        with self.assertRaisesRegex(MODULE.DistributionError, "already exists"):
            MODULE.export_snapshot(self.repo, self.ref, snapshot)
        self.assertEqual((snapshot / "DISTRIBUTION.json").read_bytes(), original)

    def test_forged_file_and_manifest_are_rejected_against_git(self) -> None:
        snapshot = self.export()
        target = snapshot / "scripts/review_repo.py"
        target.write_text(target.read_text() + "\nprint('unreviewed')\n")
        manifest = snapshot / "DISTRIBUTION.json"
        value = json.loads(manifest.read_text())
        value["files"]["scripts/review_repo.py"]["distributed_sha256"] = MODULE.digest(target.read_bytes())
        manifest.write_bytes(MODULE.encoded(value))
        with self.assertRaises(MODULE.DistributionError):
            MODULE.verify_snapshot(self.repo, self.ref, snapshot)

    def test_missing_extra_symlink_and_mode_changed_files_are_rejected(self) -> None:
        for kind in ["missing", "extra", "symlink", "mode"]:
            with self.subTest(kind=kind):
                snapshot = self.export(kind)
                target = snapshot / "LICENSE"
                if kind == "missing": target.unlink()
                elif kind == "extra": (snapshot / "run.json").write_text("{}")
                elif kind == "symlink":
                    target.unlink()
                    target.symlink_to(self.repo / "LICENSE")
                else: target.chmod(0o755)
                with self.assertRaises(MODULE.DistributionError):
                    MODULE.verify_snapshot(self.repo, self.ref, snapshot)

    def test_mutable_refs_and_tracked_symlinks_cannot_be_exported(self) -> None:
        with self.assertRaisesRegex(MODULE.DistributionError, "immutable"):
            MODULE.export_snapshot(self.repo, "HEAD", self.root / "bad")
        license = self.repo / "LICENSE"
        license.unlink()
        license.symlink_to("SKILL.md")
        self.git("add", "LICENSE")
        self.git("commit", "-qm", "invalid payload")
        with self.assertRaisesRegex(MODULE.DistributionError, "regular Git file"):
            MODULE.export_snapshot(self.repo, self.git("rev-parse", "HEAD"), self.root / "bad")

    def test_unknown_adaptation_anchor_fails_before_creating_destination(self) -> None:
        script = self.repo / "scripts/review_repo.py"
        script.write_bytes(script.read_bytes().replace(MODULE.STATE_ASSIGNMENT, b"DEFAULT_STATE_ROOT = None\n"))
        self.git("add", "scripts/review_repo.py")
        self.git("commit", "-qm", "changed state contract")
        destination = self.root / "adapted"
        with self.assertRaisesRegex(MODULE.DistributionError, "assignment changed"):
            MODULE.export_snapshot(self.repo, self.git("rev-parse", "HEAD"), destination, str(self.root / "state"))
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
