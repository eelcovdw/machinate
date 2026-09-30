#!/usr/bin/env python3
"""Run the machinate agent evals: jobs x models x repeats, in parallel.

Usage: python run.py --job pick-up-work --model deepseek/deepseek-v4.1-flash ...

Each run is *built and executed* under
`~/.cache/machinate-evals/<timestamp>/<job>/<model>/<n>/` so pi discovers the project's
own `AGENTS.md` as a normal context file and nothing from this repo or the home
directory. Afterwards the whole directory (seeded `project/`, pi `session*/`,
`session*.html`, `machi-calls.jsonl`, pi stdout/stderr, `trace.jsonl`, `result.json`) is
copied to `evals/runs/<timestamp>/<job>/<model>/<n>/`.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from .harness import snapshot_project
from .jobs import JOBS
from .trace import build_trace, compute_metrics

EVALS_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVALS_DIR.parent
MACHI = REPO_ROOT / ".venv" / "bin" / "machi"
BIN_DIR = EVALS_DIR / "bin"
RUNS_DIR = EVALS_DIR / "runs"
CACHE_BASE = Path.home() / ".cache" / "machinate-evals"
PI = shutil.which("pi") or "pi"


@dataclass
class RunSpec:
    job: str
    model: str
    repeat: int
    run_dir: Path
    work_dir: Path


@dataclass
class _Proc:
    index: int
    popen: subprocess.Popen[str]
    session_dir: Path
    stdout: Path
    stderr: Path
    stdout_handle: TextIO
    stderr_handle: TextIO


def model_slug(model: str) -> str:
    return model.replace("/", "__").replace(":", "_")


def build_runs(args: argparse.Namespace) -> list[RunSpec]:
    timestamp = args.timestamp or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    runs: list[RunSpec] = []
    for model in args.models:
        for repeat in range(1, args.repeats + 1):
            relative = Path(timestamp) / args.job / model_slug(model) / str(repeat)
            runs.append(
                RunSpec(
                    job=args.job,
                    model=model,
                    repeat=repeat,
                    run_dir=args.runs_dir / relative,
                    work_dir=args.work_dir / relative,
                )
            )
    return runs


def _seed(project_dir: Path) -> None:
    subprocess.run(  # noqa: S603 - fixed interpreter and seed module
        [sys.executable, "-m", "evals.seed", str(project_dir)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def _write_instructions(project_dir: Path) -> None:
    instructions = subprocess.run(  # noqa: S603 - fixed working-tree machi
        [str(MACHI), "instructions", "--format", "text"],
        cwd=project_dir,
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    (project_dir / "AGENTS.md").write_text(instructions, encoding="utf-8")


def _pi_command(session_dir: Path, model: str, thinking: str, prompt: str) -> list[str]:
    return [
        PI,
        "-p",
        prompt,
        "--provider",
        "openrouter",
        "--model",
        model,
        "--thinking",
        thinking,
        "--session-dir",
        str(session_dir),
        "--no-extensions",
        "--no-skills",
        "--no-prompt-templates",
    ]


@dataclass
class _LaunchEnv:
    project_dir: Path
    work_dir: Path
    env: dict[str, str]
    model: str
    thinking: str
    single: bool


def _launch(*, index: int, prompt: str, ctx: _LaunchEnv) -> _Proc:
    work_dir = ctx.work_dir
    session_dir = work_dir / ("session" if ctx.single else f"session-{index}")
    session_dir.mkdir(parents=True, exist_ok=True)
    stem = "pi" if ctx.single else f"pi-{index}"
    stdout_path = work_dir / f"{stem}.stdout.log"
    stderr_path = work_dir / f"{stem}.stderr.log"
    stdout_handle = stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    popen = subprocess.Popen(  # noqa: S603 - fixed pi binary
        _pi_command(session_dir, ctx.model, ctx.thinking, prompt),
        cwd=ctx.project_dir,
        env=ctx.env,
        stdout=stdout_handle,
        stderr=stderr_handle,
        text=True,
    )
    return _Proc(
        index=index,
        popen=popen,
        session_dir=session_dir,
        stdout=stdout_path,
        stderr=stderr_path,
        stdout_handle=stdout_handle,
        stderr_handle=stderr_handle,
    )


def _wait_all(procs: list[_Proc], timeout: float) -> set[int]:
    """Wait for every process up to the shared deadline; kill and report stragglers."""
    deadline = time.monotonic() + timeout
    timed_out: set[int] = set()
    for proc in procs:
        remaining = max(0.0, deadline - time.monotonic())
        try:
            proc.popen.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            proc.popen.kill()
            proc.popen.wait()
            timed_out.add(proc.index)
    for proc in procs:
        proc.stdout_handle.close()
        proc.stderr_handle.close()
    return timed_out


def _export_html(work_dir: Path, session_dir: Path) -> None:
    sessions = sorted(session_dir.glob("*.jsonl"))
    if not sessions:
        return
    html_name = f"{session_dir.name}.html"
    subprocess.run(  # noqa: S603 - fixed pi binary and paths
        [PI, "--export", str(sessions[-1]), str(work_dir / html_name)],
        cwd=work_dir,
        capture_output=True,
        check=False,
    )


def execute_run(run: RunSpec, args: argparse.Namespace) -> dict[str, object]:
    job = JOBS[run.job]
    work_dir = run.work_dir
    project_dir = work_dir / "project"
    work_dir.mkdir(parents=True, exist_ok=True)
    _seed(project_dir)
    _write_instructions(project_dir)
    baseline = snapshot_project(project_dir)
    (work_dir / "baseline.json").write_text(json.dumps(asdict(baseline), indent=2) + "\n", "utf-8")

    env = dict(os.environ)
    env["PATH"] = str(BIN_DIR) + os.pathsep + env.get("PATH", "")
    env["MACHI_EVAL_LOG"] = str(work_dir / "machi-calls.jsonl")
    env["AI_AGENT"] = "pi"
    env["MACHI_AI_AGENT"] = "pi"

    single = len(job.prompts) == 1
    ctx = _LaunchEnv(
        project_dir=project_dir,
        work_dir=work_dir,
        env=env,
        model=run.model,
        thinking=args.thinking,
        single=single,
    )
    started = time.monotonic()
    procs: list[_Proc] = []
    for index, prompt in enumerate(job.prompts):
        procs.append(_launch(index=index, prompt=prompt, ctx=ctx))
    timed_out = _wait_all(procs, args.timeout)
    duration = time.monotonic() - started
    exit_codes = [proc.popen.returncode for proc in procs]

    for proc in procs:
        _export_html(work_dir, proc.session_dir)

    steps = build_trace(work_dir)
    metrics = compute_metrics(steps, len(job.golden_path))
    usage = json.loads((work_dir / "usage.json").read_text(encoding="utf-8"))
    outputs = [proc.stdout.read_text(encoding="utf-8", errors="replace") for proc in procs]

    reasons: list[str] = []
    try:
        after = snapshot_project(project_dir)
        checked = job.checker(baseline, after, outputs)
        passed = checked.passed
        reasons.extend(checked.reasons)
    except (RuntimeError, FileNotFoundError, OSError) as error:
        passed = False
        reasons.append(f"checker could not read project state: {error}")
    if timed_out:
        reasons.insert(
            0, f"pi timed out after {args.timeout:.0f}s for session(s) {sorted(timed_out)}"
        )
    errors = [code for code in exit_codes if code != 0]
    if errors:
        reasons.insert(0, f"pi exited with {errors}")

    result: dict[str, object] = {
        "job": run.job,
        "model": run.model,
        "repeat": run.repeat,
        "pass": passed,
        "reasons": reasons,
        "steps": len(steps),
        "duration_seconds": round(duration, 2),
        "pi_exit_codes": exit_codes,
        "timed_out": bool(timed_out),
        "usage": usage,
        "metrics": metrics,
    }
    (work_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    shutil.copytree(work_dir, run.run_dir, dirs_exist_ok=True)
    result["run_dir"] = str(run.run_dir)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True, choices=sorted(JOBS))
    parser.add_argument("--model", action="append", required=True, dest="models")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--thinking", default="low")
    parser.add_argument("--timeout", type=float, default=600.0, help="Per-run seconds")
    parser.add_argument("--parallel", type=int, default=0, help="Workers; 0 runs all at once")
    parser.add_argument("--timestamp", default=None, help="Override the run timestamp")
    parser.add_argument("--runs-dir", type=Path, default=RUNS_DIR)
    parser.add_argument("--work-dir", type=Path, default=CACHE_BASE, help="Build/execution root")
    parser.add_argument("--dry-run", action="store_true", help="List runs without calling a model")
    args = parser.parse_args()

    runs = build_runs(args)
    if args.dry_run:
        for run in runs:
            print(run.run_dir)  # noqa: T201 - CLI output
        return 0

    failures = 0
    workers = args.parallel or len(runs)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(execute_run, run, args): run for run in runs}
        for future in as_completed(futures):
            run = futures[future]
            try:
                result = future.result()
            except (subprocess.SubprocessError, OSError, RuntimeError) as error:
                print(f"ERROR {run.run_dir}: {error}", file=sys.stderr)  # noqa: T201 - CLI output
                failures += 1
                continue
            status = "PASS" if result["pass"] else "FAIL"
            usage = result["usage"]
            cost = usage.get("cost_usd", 0) if isinstance(usage, dict) else 0
            print(  # noqa: T201 - CLI output
                f"{status} {result['model']} #{result['repeat']} {result['job']} "
                f"steps={result['steps']} {result['duration_seconds']:.1f}s cost=${cost:.4f}"
            )
            if not result["pass"]:
                failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
