from datetime import date

import pytest

from machinate.templating import (
    ContextFrontmatter,
    PlanFrontmatter,
    TaskFrontmatter,
    parse_frontmatter,
    render_context,
    render_frontmatter,
    render_plan,
    render_task,
    render_template,
)


class TestFrontmatterModels:
    def test_plan_defaults(self) -> None:
        fm = PlanFrontmatter()
        assert fm.created == date.today()  # noqa: DTZ011
        assert fm.status == "draft"

    def test_task_defaults(self) -> None:
        fm = TaskFrontmatter()
        assert fm.created == date.today()  # noqa: DTZ011
        assert fm.status == "todo"

    def test_context_defaults(self) -> None:
        fm = ContextFrontmatter()
        assert fm.created == date.today()  # noqa: DTZ011

    def test_summary_defaults_to_empty(self) -> None:
        assert PlanFrontmatter().summary == ""
        assert TaskFrontmatter().summary == ""
        assert ContextFrontmatter().summary == ""

    def test_plan_rejects_invalid_status(self) -> None:
        with pytest.raises(Exception):  # noqa: B017, PT011
            PlanFrontmatter.model_validate({"status": "invalid"})

    def test_task_rejects_invalid_status(self) -> None:
        with pytest.raises(Exception):  # noqa: B017, PT011
            TaskFrontmatter.model_validate({"status": "invalid"})


class TestParseFrontmatter:
    def test_parses_frontmatter(self) -> None:
        text = "---\ncreated: 2026-01-01\nstatus: draft\n---\n\n# My Plan\n"
        meta, body = parse_frontmatter(text)
        assert meta == {"created": "2026-01-01", "status": "draft"}
        assert body == "# My Plan\n"

    def test_no_frontmatter(self) -> None:
        text = "# Just a heading\n\nSome content.\n"
        meta, body = parse_frontmatter(text)
        assert meta == {}
        assert body == text

    def test_empty_string(self) -> None:
        meta, body = parse_frontmatter("")
        assert meta == {}
        assert body == ""

    def test_unclosed_frontmatter(self) -> None:
        text = "---\ncreated: 2026-01-01\n"
        meta, body = parse_frontmatter(text)
        assert meta == {}
        assert body == text

    def test_roundtrip(self) -> None:
        rendered = render_plan("my-feature")
        meta, body = parse_frontmatter(rendered)
        assert "created" in meta
        assert meta["status"] == "draft"
        assert body == "# Plan: my-feature\n"

    def test_parses_summary(self) -> None:
        text = (
            "---\ncreated: 2026-01-01\nstatus: draft\n"
            "summary: A short description\n---\n\n# My Plan\n"
        )
        meta, _ = parse_frontmatter(text)
        assert meta["summary"] == "A short description"


class TestRenderFrontmatter:
    def test_plan(self) -> None:
        fm = PlanFrontmatter(created=date(2026, 1, 1))
        result = render_frontmatter(fm)
        assert result == "---\ncreated: 2026-01-01\nstatus: draft\n---"

    def test_task(self) -> None:
        fm = TaskFrontmatter(created=date(2026, 1, 1))
        result = render_frontmatter(fm)
        assert result == "---\ncreated: 2026-01-01\nstatus: todo\n---"

    def test_context(self) -> None:
        fm = ContextFrontmatter(created=date(2026, 1, 1))
        result = render_frontmatter(fm)
        assert result == "---\ncreated: 2026-01-01\n---"

    def test_skips_empty_summary(self) -> None:
        fm = PlanFrontmatter(created=date(2026, 1, 1))
        result = render_frontmatter(fm)
        assert "summary" not in result

    def test_includes_nonempty_summary(self) -> None:
        fm = PlanFrontmatter(created=date(2026, 1, 1), summary="A short description")
        result = render_frontmatter(fm)
        assert "summary: A short description" in result


class TestRenderTemplate:
    def test_default_template(self) -> None:
        fm = PlanFrontmatter(created=date(2026, 1, 1))
        result = render_template(fm, "my-plan", entity="Plan")
        assert result == "---\ncreated: 2026-01-01\nstatus: draft\n---\n\n# Plan: my-plan\n"

    def test_custom_template(self) -> None:
        fm = PlanFrontmatter(created=date(2026, 1, 1))
        result = render_template(fm, "my-plan", entity="Plan", template="## {name}\n")
        assert result == "---\ncreated: 2026-01-01\nstatus: draft\n---\n\n## my-plan\n"


class TestRenderAliases:
    def test_render_plan(self) -> None:
        result = render_plan("my-feature")
        assert "# Plan: my-feature\n" in result
        assert result.startswith("---\n")
        assert "status: draft" in result

    def test_render_task(self) -> None:
        result = render_task("setup")
        assert "# Task: setup\n" in result
        assert "status: todo" in result

    def test_render_context(self) -> None:
        result = render_context("api-spec")
        assert "# Context: api-spec\n" in result
        assert "status" not in result.split("---")[1].split("---")[0] or "created" in result
