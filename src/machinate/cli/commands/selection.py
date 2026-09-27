"""Resolution of the plan a command should act on."""

from machinate.models.plan import Plan
from machinate.services.plan import PlanService


class PlanSelectionError(Exception):
    """Raised when a command needs a plan but none was given or selected."""


def resolve_plan_name(plans: PlanService, name: str | None, *, automation: bool) -> str:
    """Resolve the name of the explicit or current plan.

    Resolving the selection does not read the plan document; the service that needs
    it reads it once, so a command never parses the same plan twice.
    """
    if name is not None:
        return name
    if automation:
        msg = "Automation mode requires an explicit plan; use -p NAME."
        raise PlanSelectionError(msg)
    current = plans.current_name()
    if current is None:
        msg = "No current plan is selected; use -p NAME."
        raise PlanSelectionError(msg)
    return current


def select_plan(plans: PlanService, name: str | None, *, automation: bool) -> Plan:
    """Resolve the selected plan and load its document."""
    return plans.get(resolve_plan_name(plans, name, automation=automation))
