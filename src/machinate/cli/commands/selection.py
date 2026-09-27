from machinate.models.plan import Plan
from machinate.services.plan import PlanService


class PlanSelectionError(Exception):
    """Raised when a command needs a plan but none was given or selected."""


def select_plan(plans: PlanService, name: str | None, *, automation: bool) -> Plan:
    """Resolve the explicit or current plan, enforcing automation targeting."""
    if name is None and automation:
        msg = "Automation mode requires an explicit plan; use -p NAME."
        raise PlanSelectionError(msg)
    selected = plans.get_current() if name is None else plans.get(name)
    if selected is None:
        msg = "No current plan is selected; use -p NAME."
        raise PlanSelectionError(msg)
    return selected
