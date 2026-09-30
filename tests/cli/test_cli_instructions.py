import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from harness import cli, filtered_environment, seed_doc, seed_plan, seed_task

from machinate.cli.models import InstructionsResult


def test_instructions_json() -> None:
    payload = cli.json(InstructionsResult, ["instructions", "--format", "json"])
    assert payload.command == "instructions"


def test_agents_md_machinate_section_matches_instructions() -> None:
    payload = cli.json(InstructionsResult, ["instructions", "--format", "json"])
    agents = (Path(__file__).resolve().parents[2] / "AGENTS.md").read_text()
    section = agents[agents.index("## Machinate") :]
    assert section.strip() == payload.text.strip()


def test_instructions_examples_run(project: Path) -> None:
    """Run the literal `machi … | jq …` examples against a seeded project."""
    if shutil.which("jq") is None:
        pytest.skip("jq is not installed")
    bash = shutil.which("bash")
    assert bash is not None
    payload = cli.json(InstructionsResult, ["instructions", "--format", "json"])
    examples = [
        line.strip()
        for line in payload.text.splitlines()
        if line.strip().startswith("machi ") and "| jq" in line
    ]
    assert examples

    seed_plan(project, "v2")
    seed_task(project, "v2", "01-todo")
    seed_doc(project, "guide")
    launcher = Path(sys.executable).with_name("machi")
    environment = filtered_environment() | {
        "MACHI_AI_AGENT": "test",
        "PATH": f"{launcher.parent}{os.pathsep}{os.environ.get('PATH', '')}",
    }
    for example in examples:
        result = subprocess.run(  # noqa: S603 - bash resolved above
            [bash, "-o", "pipefail", "-c", example],
            cwd=project,
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )
        assert result.returncode == 0, (example, result.stderr)
        assert all(line.strip() != "null" for line in result.stdout.splitlines()), example
