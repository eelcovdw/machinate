#!/usr/bin/env python3
"""Convert pi session(s) into a normalized eval trace, plus per-run metrics.

Usage: python trace.py <run_dir>

Reads every `<run_dir>/session*/**.jsonl` file and `<run_dir>/machi-calls.jsonl`, writes
one `<run_dir>/trace.jsonl` line per tool call (with the machi calls whose start time fell
inside each bash step), a `<run_dir>/usage.json` with the session's token and cost totals,
and prints a compact step list. `compute_metrics` derives the design metrics from the
trace alone.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from .harness import JsonValue, as_dict, as_int, as_list, as_str, parse_json

EXCERPT_CHARS = 500
BASH_TOOLS = frozenset({"bash"})
FILE_TOOLS = frozenset({"read", "write", "edit"})
DIRECT_VERBS = frozenset(
    {"ls", "cat", "grep", "head", "tail", "wc", "find", "sed", "awk", "less", "more"}
)
MUTATION_WORDS = frozenset({"add", "update", "remove", "delete", "rename", "select", "unselect"})


@dataclass
class MachiCall:
    argv: list[str]
    exit_code: int
    error_code: str | None
    output_chars: int
    start_ms: float


@dataclass
class Step:
    index: int
    session: int
    time: str
    tool: str
    input: JsonValue
    is_error: bool
    output_size: int
    output_excerpt: str
    batch: str
    machi_calls: list[MachiCall] = field(default_factory=list)


@dataclass
class _RawStep:
    step: Step
    start_ms: float | None
    end_ms: float | None


def _load_events(session_path: Path) -> list[JsonValue]:
    lines = session_path.read_text(encoding="utf-8").splitlines()
    return [parse_json(line) for line in lines if line.strip()]


def _text_of(content: JsonValue) -> str:
    if isinstance(content, str):
        return content
    return "".join(
        as_str(as_dict(block).get("text"))
        for block in as_list(content)
        if as_dict(block).get("type") == "text"
    )


def _parse_arguments(raw: JsonValue) -> JsonValue:
    if isinstance(raw, dict | list) or raw is None:
        return raw
    if isinstance(raw, bool | int | float):
        return raw
    try:
        return parse_json(raw)
    except json.JSONDecodeError:
        try:
            return parse_json(json.dumps(ast.literal_eval(raw)))
        except ValueError, SyntaxError:
            return raw


def _timestamp_ms(value: JsonValue) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _iso(timestamp_ms: float | None) -> str:
    if timestamp_ms is None:
        return ""
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).isoformat()


def build_steps(events: list[JsonValue], session: int) -> list[_RawStep]:
    """One entry per tool call, joined to its result by tool-call id."""
    results: dict[str, dict[str, JsonValue]] = {}
    for event in events:
        record = as_dict(event)
        message = as_dict(record.get("message"))
        if record.get("type") != "message" or message.get("role") != "toolResult":
            continue
        call_id = as_str(message.get("toolCallId"))
        if call_id:
            results[call_id] = message

    steps: list[_RawStep] = []
    message_index = 0
    for event in events:
        record = as_dict(event)
        message = as_dict(record.get("message"))
        if record.get("type") != "message" or message.get("role") != "assistant":
            continue
        message_index += 1
        for block in as_list(message.get("content")):
            call = as_dict(block)
            if call.get("type") != "toolCall":
                continue
            call_id = as_str(call.get("id"))
            result = results.get(call_id)
            output = _text_of(as_dict(result).get("content")) if result else ""
            start_ms = _timestamp_ms(message.get("timestamp"))
            end_ms = _timestamp_ms(as_dict(result).get("timestamp")) if result else None
            step = Step(
                index=0,
                session=session,
                time=_iso(start_ms),
                tool=as_str(call.get("name")),
                input=_parse_arguments(call.get("arguments")),
                is_error=bool(as_dict(result).get("isError")) if result else False,
                output_size=len(output),
                output_excerpt=output[:EXCERPT_CHARS],
                batch=f"{session}:{message_index}",
            )
            steps.append(_RawStep(step=step, start_ms=start_ms, end_ms=end_ms))
    return steps


def _load_machi_calls(run_dir: Path) -> list[JsonValue]:
    log_path = run_dir / "machi-calls.jsonl"
    if not log_path.exists():
        return []
    lines = log_path.read_text(encoding="utf-8").splitlines()
    return [parse_json(line) for line in lines if line.strip()]


def _error_code(stderr: JsonValue) -> str | None:
    try:
        parsed = parse_json(as_str(stderr))
    except json.JSONDecodeError:
        return None
    code = as_dict(parsed).get("code")
    if code is None:
        return None
    return str(code)


def _as_call(record: JsonValue) -> MachiCall | None:
    call = as_dict(record)
    started_at = as_str(call.get("started_at"))
    if not started_at:
        return None
    return MachiCall(
        argv=[str(item) for item in as_list(call.get("argv"))],
        exit_code=as_int(call.get("exit_code")),
        error_code=_error_code(call.get("stderr")),
        output_chars=as_int(call.get("stdout_chars")),
        start_ms=datetime.fromisoformat(started_at).timestamp() * 1000,
    )


def _attach_machi_calls(raw: _RawStep, calls: list[MachiCall]) -> None:
    if raw.step.tool not in BASH_TOOLS:
        return
    if raw.start_ms is None or raw.end_ms is None:
        return
    raw.step.machi_calls = [call for call in calls if raw.start_ms <= call.start_ms <= raw.end_ms]


def find_sessions(run_dir: Path) -> list[Path]:
    sessions: list[Path] = []
    for session_dir in sorted(run_dir.glob("session*")):
        if session_dir.is_dir():
            sessions.extend(sorted(session_dir.glob("*.jsonl")))
    if not sessions:
        msg = f"no session JSONL under {run_dir}/session*"
        raise FileNotFoundError(msg)
    return sessions


def build_trace(run_dir: Path) -> list[Step]:
    """Build trace.jsonl and usage.json for a run directory, returning the steps."""
    calls = [call for call in (_as_call(record) for record in _load_machi_calls(run_dir)) if call]
    raws: list[_RawStep] = []
    events_by_session: list[list[JsonValue]] = []
    for session_index, session_path in enumerate(find_sessions(run_dir)):
        events = _load_events(session_path)
        events_by_session.append(events)
        raws.extend(build_steps(events, session_index))
    for raw in raws:
        _attach_machi_calls(raw, calls)

    raws.sort(key=lambda raw: (raw.start_ms or 0.0, raw.step.session))
    steps: list[Step] = []
    for index, raw in enumerate(raws, start=1):
        raw.step.index = index
        steps.append(raw.step)

    with (run_dir / "trace.jsonl").open("w", encoding="utf-8") as handle:
        for step in steps:
            handle.write(json.dumps(asdict(step)) + "\n")

    usage = summarize_usage(events_by_session)
    usage["steps"] = len(steps)
    (run_dir / "usage.json").write_text(json.dumps(usage, indent=2) + "\n", encoding="utf-8")
    return steps


def summarize_usage(events_by_session: list[list[JsonValue]]) -> dict[str, JsonValue]:
    """Sum token and cost fields across assistant messages of all sessions."""
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    cost = 0.0
    model: str | None = None
    provider: str | None = None
    thinking: str | None = None
    for events in events_by_session:
        for event in events:
            record = as_dict(event)
            kind = as_str(record.get("type"))
            if kind == "model_change":
                provider = as_str(record.get("provider")) or provider
                model = as_str(record.get("modelId")) or model
            elif kind == "thinking_level_change":
                thinking = as_str(record.get("thinkingLevel")) or thinking
            message = as_dict(record.get("message"))
            if message.get("role") != "assistant":
                continue
            usage = as_dict(message.get("usage"))
            input_tokens += as_int(usage.get("input"))
            output_tokens += as_int(usage.get("output"))
            total_tokens += as_int(usage.get("totalTokens"))
            total = as_dict(usage.get("cost")).get("total")
            if isinstance(total, int | float) and not isinstance(total, bool):
                cost += float(total)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cost_usd": round(cost, 6),
        "model": model,
        "provider": provider,
        "thinking_level": thinking,
    }


def _step_command(step: Step) -> str:
    arguments = as_dict(step.input)
    for key in ("command", "path", "file_path"):
        value = arguments.get(key)
        if isinstance(value, str):
            return value.replace("\n", " ")[:70]
    return json.dumps(step.input)[:70]


def _is_machi_step(step: Step) -> bool:
    return bool(step.machi_calls)


def _has_machi_error(step: Step) -> bool:
    return any(call.exit_code != 0 for call in step.machi_calls)


def _direct_machi_access(step: Step) -> bool:
    arguments = as_dict(step.input)
    if step.tool in FILE_TOOLS:
        path = as_str(arguments.get("path")) or as_str(arguments.get("file_path"))
        if ".machi" not in path:
            return False
        return not path.endswith(".md")
    if step.tool == "bash":
        command = as_str(arguments.get("command"))
        if ".machi" not in command:
            return False
        return any(re.search(rf"\b{verb}\b", command) for verb in DIRECT_VERBS)
    return False


def _file_document(step: Step) -> str | None:
    if step.tool not in FILE_TOOLS:
        return None
    arguments = as_dict(step.input)
    path = as_str(arguments.get("path")) or as_str(arguments.get("file_path"))
    if ".machi" not in path:
        return None
    return Path(path).stem


def _is_mutation(step: Step) -> bool:
    return any(MUTATION_WORDS & set(call.argv) for call in step.machi_calls)


def _call_signature(step: Step) -> str:
    return json.dumps([step.tool, step.input], sort_keys=True)


def _collect_machi_errors(steps: list[Step]) -> list[JsonValue]:
    errors: list[JsonValue] = []
    for step in steps:
        errors.extend(
            {
                "step": step.index,
                "argv": list(call.argv),
                "exit_code": call.exit_code,
                "error_code": call.error_code,
            }
            for call in step.machi_calls
            if call.exit_code != 0
        )
    return errors


def _recovery(steps: list[Step]) -> tuple[list[JsonValue], int]:
    recovery: list[JsonValue] = []
    recovery_steps = 0
    for position, step in enumerate(steps):
        if not _has_machi_error(step):
            continue
        recovered: int | None = None
        for later in range(position + 1, len(steps)):
            if _is_machi_step(steps[later]) and not _has_machi_error(steps[later]):
                recovered = steps[later].index
                recovery_steps += recovered - step.index
                break
        recovery.append(
            {
                "error_step": step.index,
                "recovered_step": recovered,
                "steps": 0 if recovered is None else recovered - step.index,
            }
        )
    return recovery, recovery_steps


def _count_repeated(steps: list[Step]) -> int:
    seen: set[str] = set()
    repeated = 0
    for step in steps:
        signature = _call_signature(step)
        if signature in seen:
            repeated += 1
        seen.add(signature)
    return repeated


def _concurrent_writes(steps: list[Step]) -> list[JsonValue]:
    concurrent: list[JsonValue] = []
    by_batch: dict[str, list[Step]] = {}
    for step in steps:
        by_batch.setdefault(step.batch, []).append(step)
    for batch_steps in by_batch.values():
        mutations = [step for step in batch_steps if _is_mutation(step)]
        for step in batch_steps:
            document = _file_document(step)
            if document is None:
                continue
            concurrent.extend(
                {
                    "batch": step.batch,
                    "step": step.index,
                    "document": document,
                    "machi_argv": list(mutation.machi_calls[0].argv),
                }
                for mutation in mutations
                if document in " ".join(mutation.machi_calls[0].argv)
            )
    return concurrent


def compute_metrics(steps: list[Step], golden_steps: int) -> dict[str, JsonValue]:
    """Derive the eval's design metrics from the trace."""
    machi_steps = [step for step in steps if _is_machi_step(step)]
    machi_errors = _collect_machi_errors(steps)
    codes: list[JsonValue] = [
        code for error in machi_errors if (code := as_dict(error).get("error_code")) is not None
    ]
    error_codes = sorted(codes, key=str)
    recovery, recovery_steps = _recovery(steps)
    metrics: dict[str, JsonValue] = {
        "steps": len(steps),
        "golden_steps": golden_steps,
        "steps_over_golden": max(0, len(steps) - golden_steps),
        "machi_steps": len(machi_steps),
        "other_tool_steps": len(steps) - len(machi_steps),
        "machi_errors": machi_errors,
        "machi_error_codes": error_codes,
        "recovery": recovery,
        "recovery_steps": recovery_steps,
        "repeated_calls": _count_repeated(steps),
        "direct_machi_access": [step.index for step in steps if _direct_machi_access(step)],
        "output_chars": sum(step.output_size for step in steps),
        "concurrent_writes": _concurrent_writes(steps),
    }
    return metrics


def print_steps(steps: list[Step]) -> None:
    for step in steps:
        marker = "err" if step.is_error else "ok "
        machi = f"machi x{len(step.machi_calls)}" if step.machi_calls else ""
        time_part = step.time[11:19]
        parts = [
            f"{step.index:>3}",
            time_part,
            f"s{step.session}",
            f"{step.tool:<6}",
            marker,
            f"{step.output_size:>6}B",
            _step_command(step),
            machi,
        ]
        print(" ".join(parts))  # noqa: T201 - CLI output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="Run directory containing session*/")
    args = parser.parse_args()
    run_dir = cast("Path", args.run_dir)
    steps = build_trace(run_dir)
    print_steps(steps)
    print(f"{len(steps)} tool calls -> {run_dir / 'trace.jsonl'}")  # noqa: T201 - CLI output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
