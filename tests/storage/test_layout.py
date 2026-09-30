from pathlib import PurePosixPath

import pytest

from machinate.models.documents import DocumentIdentity
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
def test_identify(path: str, expected: tuple[str, str | None, str | None]) -> None:
    membership = Layout().identify(PurePosixPath(path))
    assert (membership.kind, membership.plan_name, membership.name) == expected


def test_identify_matches_forward_conventions() -> None:
    layout = Layout()
    assert layout.identify(layout.plan_path("auth")) == DocumentIdentity(
        kind="plan", plan_name="auth", name="auth"
    )
    assert layout.identify(layout.task_path("auth", "abcd/efg/h")) == DocumentIdentity(
        kind="task", plan_name="auth", name="abcd/efg/h"
    )
    assert layout.identify(layout.context_path("auth", "deep/nested/x")) == DocumentIdentity(
        kind="context", plan_name="auth", name="deep/nested/x"
    )
    assert layout.identify(layout.doc_path("topic/spec")) == DocumentIdentity(
        kind="doc", name="topic/spec"
    )
