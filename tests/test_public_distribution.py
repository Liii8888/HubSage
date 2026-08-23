from __future__ import annotations

import importlib.util
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "review_repo.py"
SPEC = importlib.util.spec_from_file_location("public_review_repo", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class PublicDistributionTests(unittest.TestCase):
    def test_state_root_precedence_is_portable(self) -> None:
        home = Path("/tmp/public-home")
        self.assertEqual(
            MODULE.default_state_root(
                {"PRIVATE_GITHUB_PRO_REVIEW_HOME": "/tmp/explicit"}, home
            ),
            Path("/tmp/explicit"),
        )
        self.assertEqual(
            MODULE.default_state_root({"XDG_STATE_HOME": "/tmp/state"}, home),
            Path("/tmp/state/private-github-pro-review"),
        )
        self.assertEqual(
            MODULE.default_state_root({}, home),
            Path("/tmp/public-home/.local/state/private-github-pro-review"),
        )

    def test_skill_core_has_no_machine_specific_home_path(self) -> None:
        paths = [
            ROOT / "SKILL.md",
            ROOT / "KNOWN-ISSUES.md",
            ROOT / "agents" / "openai.yaml",
            ROOT / "references" / "browser-protocol.md",
            SCRIPT,
        ]
        home_path = re.compile(r"/(?:Users|home)/[^/\s]+/")
        violations = []
        for path in paths:
            text = path.read_text(encoding="utf-8")
            if home_path.search(text):
                violations.append(str(path.relative_to(ROOT)))
        self.assertEqual(violations, [])

    def test_field_notes_do_not_name_a_repository(self) -> None:
        text = (ROOT / "KNOWN-ISSUES.md").read_text(encoding="utf-8")
        repository_reference = re.compile(
            r"(?:https://github\.com/|`)[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
        )
        self.assertIsNone(repository_reference.search(text))


if __name__ == "__main__":
    unittest.main()
