"""Guards against the assignment's 'credentials committed at any point' failure."""

from __future__ import annotations

import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_env_example_has_no_values_for_secrets() -> None:
    for line in (ROOT / ".env.example").read_text().splitlines():
        match = re.match(r"^\s*(?:export\s+)?([A-Z0-9_]*(?:KEY|TOKEN|SECRET)[A-Z0-9_]*)\s*=\s*(.*)$", line)
        if match:
            # Compute a bool first: a failing assert must never echo the secret value into logs.
            is_empty = match.group(2).strip() == ""
            name = match.group(1)
            assert is_empty, f"{name} must be empty in .env.example (value not shown)"


def test_dotenv_is_ignored_and_untracked() -> None:
    tracked = subprocess.run(["git", "ls-files", ".env"], cwd=ROOT, capture_output=True, text=True).stdout
    ignored = subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=ROOT).returncode == 0
    assert tracked.strip() == "" and ignored
