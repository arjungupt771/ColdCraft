"""Application lifecycle: explicit states and the only transitions allowed between them."""
from enum import Enum

from app.core.errors import InvalidTransitionError


class ApplicationStatus(str, Enum):
    DRAFT = "DRAFT"                    # JD captured, nothing else done yet
    RESEARCHING = "RESEARCHING"        # company/recruiter lookup in progress
    READY = "READY"                    # research done; email can be generated/edited/sent
    SENDING = "SENDING"                # claimed by exactly one in-flight send (duplicate-send guard)
    SENT = "SENT"
    FOLLOW_UP_DUE = "FOLLOW_UP_DUE"    # a scheduled follow-up has come due
    FOLLOW_UP_SENT = "FOLLOW_UP_SENT"
    REPLIED = "REPLIED"
    INTERVIEW = "INTERVIEW"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


S = ApplicationStatus

ALLOWED_TRANSITIONS: dict[ApplicationStatus, frozenset[ApplicationStatus]] = {
    S.DRAFT: frozenset({S.RESEARCHING, S.WITHDRAWN}),
    S.RESEARCHING: frozenset({S.READY, S.DRAFT}),               # DRAFT = research failed
    S.READY: frozenset({S.READY, S.RESEARCHING, S.SENDING, S.WITHDRAWN}),
    S.SENDING: frozenset({S.SENT, S.READY}),                  # READY = send failed, safe to retry
    S.SENT: frozenset({S.FOLLOW_UP_DUE, S.REPLIED, S.REJECTED, S.WITHDRAWN}),
    S.FOLLOW_UP_DUE: frozenset({S.FOLLOW_UP_SENT, S.REPLIED, S.REJECTED, S.WITHDRAWN}),
    S.FOLLOW_UP_SENT: frozenset({S.FOLLOW_UP_DUE, S.REPLIED, S.REJECTED, S.WITHDRAWN}),
    S.REPLIED: frozenset({S.INTERVIEW, S.REJECTED, S.WITHDRAWN}),
    S.INTERVIEW: frozenset({S.REJECTED, S.WITHDRAWN}),
    S.REJECTED: frozenset(),
    S.WITHDRAWN: frozenset(),
}

# States in which a follow-up can be scheduled / is still relevant
AWAITING_REPLY = frozenset({S.SENT, S.FOLLOW_UP_DUE, S.FOLLOW_UP_SENT})
TERMINAL = frozenset({S.REJECTED, S.WITHDRAWN})


def coerce(value: "str | ApplicationStatus") -> ApplicationStatus:
    try:
        return ApplicationStatus(value)
    except ValueError:
        raise InvalidTransitionError(f"Unknown status '{value}'")


def can_transition(current: "str | ApplicationStatus", new: "str | ApplicationStatus") -> bool:
    return coerce(new) in ALLOWED_TRANSITIONS[coerce(current)]


def transition(app, new: "str | ApplicationStatus") -> ApplicationStatus:
    """Apply a transition to an ORM object, or raise InvalidTransitionError."""
    cur, nxt = coerce(app.status), coerce(new)
    if nxt not in ALLOWED_TRANSITIONS[cur]:
        raise InvalidTransitionError(f"Cannot move application from {cur.value} to {nxt.value}")
    app.status = nxt.value
    return nxt
