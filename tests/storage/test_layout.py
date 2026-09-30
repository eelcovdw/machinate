from pathlib import PurePosixPath

import pytest

from machinate.models.documents import DocumentMembership
from machinate.storage import Layout


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("plans/auth/plan.md", ("plan", "auth", "auth")),
        ("plans/auth/tasks/login.md", ("task", "auth", "login")),
        ("plans/auth/tasks/abcd/efg/h.md", ("task", "auth", "abcd/efg/h")),
        ("plans/auth/context/notes.md", ("context", "auth", "notes")),
        ("plans/auth/context/deep/nested/x.md", ("context", "auth", "deep/nested/x")),
        ("docs/spec.md", ("doc", None, "spec")),
        ("docs/topic/spec.md", ("doc", None, "topic/spec")),
        ("docs/spec.txt", ("unknown", None, None)),
        ("docs", ("unknown", None, None)),
        ("docs/topic", ("unknown", None, None)),
        ("machinate.toml", ("unknown", None, None)),
        ("project.md", ("unknown", None, None)),
        ("plans", ("unknown", None, None)),
        ("plans/auth/tasks", ("unknown", None, None)),
        ("plans/auth/tasks/readme.txt", ("unknown", None, None)),
        ("plans/auth/other/x.md", ("unknown", None, None)),
        ("plans/auth/plan.md/extra.md", ("unknown", None, None)),
    ],
)
def test_resolve(path: str, expected: tuple[str, str | None, str | None]) -> None:
    membership = Layout().resolve(PurePosixPath(path))
    assert (membership.kind, membership.plan_name, membership.name) == expected


def test_resolve_matches_forward_conventions() -> None:
    layout = Layout()
    assert layout.resolve(layout.plan("auth")) == DocumentMembership(
        kind="plan", plan_name="auth", name="auth"
    )
    assert layout.resolve(layout.task("auth", "abcd/efg/h")) == DocumentMembership(
        kind="task", plan_name="auth", name="abcd/efg/h"
    )
    assert layout.resolve(layout.context("auth", "deep/nested/x")) == DocumentMembership(
        kind="context", plan_name="auth", name="deep/nested/x"
    )
    assert layout.resolve(layout.doc("topic/spec")) == DocumentMembership(
        kind="doc", name="topic/spec"
    )
