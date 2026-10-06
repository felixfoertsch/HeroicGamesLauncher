"""Keep inherited CLA automation disabled without failing repeat maintenance."""
import json
import os

from calver import REPOSITORY
from release_cleanup import gh

DISABLED = {"disabled_manually", "disabled_inactivity"}


def workflow_state():
    workflow = json.loads(gh("api", f"repos/{REPOSITORY}/actions/workflows/cla.yml"))
    state = workflow.get("state")
    if state not in DISABLED | {"active"}:
        raise ValueError(f"Unexpected CLA workflow state: {state!r}")
    return state


def ensure_disabled():
    if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
        raise ValueError("CLA maintenance is restricted to Felix's fork")
    state = workflow_state()
    if state in DISABLED:
        print(f"CLA Assistant is already {state}; no change needed.")
        return state

    error = None
    try:
        gh("workflow", "disable", "cla.yml", "--repo", REPOSITORY)
    except RuntimeError as exception:
        error = exception
    # A concurrent maintenance run can disable it after the first read. Only
    # an independently verified disabled state makes that failed write harmless.
    state = workflow_state()
    if state not in DISABLED:
        if error is not None:
            raise error
        raise RuntimeError("CLA Assistant is still active after the disable operation")
    print(f"CLA Assistant is {state}.")
    return state


if __name__ == "__main__":
    ensure_disabled()
