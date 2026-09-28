"""Pure validation logic for department handover ("핑퐁") tracking.

Persistence (the handovers table) lives in src/storage/repository.py;
this module only knows the domain rules for what makes one handover step
valid -- it doesn't touch the database.
"""
from typing import Optional

# YI(수율개선)/MFG(제조)/M-ENG(설비기술)/P-ENG(공정기술) -- the four departments
# named in this project's background as the ones that hand an event back
# and forth ("핑퐁") while its root cause is unclear.
VALID_DEPTS = ("YI", "MFG", "M-ENG", "P-ENG")


def validate_handover(current_dept: Optional[str], to_dept: str, reason: str) -> None:
    """Raises ValueError if this handover step doesn't make sense.

    `current_dept` is the event's dept before this step (None if nobody
    owns it yet, e.g. an R0 "normal close-out" event being reopened).
    """
    if to_dept not in VALID_DEPTS:
        raise ValueError(f"Unknown department: {to_dept!r} (valid: {VALID_DEPTS})")
    if not reason or not reason.strip():
        raise ValueError("reason must be a non-empty string -- a handover without a stated reason defeats the point")
    if to_dept == current_dept:
        raise ValueError(f"Event is already assigned to {to_dept!r}; a no-op handover is rejected")
