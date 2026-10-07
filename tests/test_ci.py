from __future__ import annotations

from pathlib import Path

import yaml
from mayortracker.util.config import find_repo_root


def test_ci_workflow_valid_yaml() -> None:
    repo_root = find_repo_root(Path(__file__).parent)
    ci_path = repo_root / ".github" / "workflows" / "ci.yml"
    assert ci_path.is_file(), f"Missing CI workflow file: {ci_path}"

    with ci_path.open(encoding="utf-8") as fh:
        workflow = yaml.safe_load(fh)

    assert isinstance(workflow, dict)
    assert "jobs" in workflow
    assert "test" in workflow["jobs"]
    job = workflow["jobs"]["test"]
    assert "steps" in job
    step_runs = [step.get("run", "") for step in job["steps"] if "run" in step]
    assert any("uv sync" in cmd for cmd in step_runs)
    assert any("uv run ruff check" in cmd for cmd in step_runs)
    assert any("uv run pytest" in cmd for cmd in step_runs)
