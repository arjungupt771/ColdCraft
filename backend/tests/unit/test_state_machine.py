import pytest

from app.core.errors import InvalidTransitionError
from app.domain.state_machine import ALLOWED_TRANSITIONS, ApplicationStatus as S, can_transition, coerce, transition


class Obj:
    def __init__(self, status):
        self.status = status


def test_every_state_has_a_transition_entry():
    assert set(ALLOWED_TRANSITIONS) == set(S)


def test_happy_path():
    app = Obj("DRAFT")
    for nxt in (S.RESEARCHING, S.READY, S.SENDING, S.SENT, S.FOLLOW_UP_DUE, S.FOLLOW_UP_SENT, S.REPLIED, S.INTERVIEW):
        transition(app, nxt)
        assert app.status == nxt.value


@pytest.mark.parametrize("cur,new", [
    (S.DRAFT, S.SENT), (S.READY, S.SENT), (S.READY, S.REPLIED), (S.SENDING, S.REPLIED), (S.SENT, S.READY), (S.REPLIED, S.SENT),
    (S.REJECTED, S.READY), (S.WITHDRAWN, S.DRAFT), (S.INTERVIEW, S.REPLIED),
])
def test_illegal_transitions_raise(cur, new):
    app = Obj(cur.value)
    with pytest.raises(InvalidTransitionError):
        transition(app, new)
    assert app.status == cur.value        # unchanged on failure


def test_terminal_states_have_no_exits():
    assert not ALLOWED_TRANSITIONS[S.REJECTED] and not ALLOWED_TRANSITIONS[S.WITHDRAWN]


def test_unknown_status_rejected():
    with pytest.raises(InvalidTransitionError):
        coerce("sent")           # legacy lowercase values are not valid any more
    assert can_transition("READY", "SENDING") and not can_transition("READY", "SENT")
