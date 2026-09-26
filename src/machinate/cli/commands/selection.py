from machinate.models.plan import Plan
from machinate.services.plan import PlanService
from machinate.storage.models import NameInput


class PlanSelectionError(Exception):
    """Raised when a command needs a plan but none was given or selected."""


def select_plan(plans: PlanService, name: str | None, *, interactive: bool) -> Plan:
    """Resolve the explicit or current plan, enforcing non-interactive targeting."""
    if name is None and not interactive:
        msg = "Non-interactive mode requires an explicit plan; use -p NAME."
        raise PlanSelectionError(msg)
    selected = plans.get_current() if name is None else plans.get(name)
    if selected is None:
        msg = "No current plan is selected; use -p NAME."
        raise PlanSelectionError(msg)
    return selected


def explicit_plan_name(name: str | None) -> str:
    """Validate a required explicit plan selector."""
    if name is None:
        msg = "An explicit plan is required; use -p NAME."
        raise PlanSelectionError(msg)
    return NameInput(name=name).name
