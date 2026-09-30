import pytest
from pydantic import ValidationError

from machinate.models.operations import DocumentQuery, PlanQuery, TaskQuery


@pytest.mark.parametrize(
    "data",
    [
        {"limit": 0},
        {"limit": -1},
        {"statuses": ["invalid"]},
        {"sort": "invalid"},
    ],
)
def test_query_validation(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PlanQuery.model_validate(data)


def test_last_activity_sort_is_plan_only() -> None:
    with pytest.raises(ValidationError):
        DocumentQuery(sort="last_activity_at")
    with pytest.raises(ValidationError):
        TaskQuery(sort="last_activity_at")


def test_task_query_rejects_invalid_status() -> None:
    with pytest.raises(ValidationError):
        TaskQuery.model_validate({"statuses": ["draft"]})
