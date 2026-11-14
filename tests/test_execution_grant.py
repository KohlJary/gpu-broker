"""Negative tests for exact execution grant binding."""
from dataclasses import replace

import pytest

from gpu_broker.execution_grant import ExecutionBinding, GrantRefusal, VerifiedGrant, check_grant

BINDING = ExecutionBinding("permit", "attempt", "cone", "impl", "provider", 1000000, 200)


def test_exact_unconsumed_grant() -> None:
    assert check_grant(BINDING, VerifiedGrant(BINDING, True, False), now_epoch_s=100) is None


@pytest.mark.parametrize(
    ("field", "value"),
    [("permit_id", "other"), ("attempt_id", "other"), ("cone_id", "other"),
     ("implementation_id", "other"), ("provider_id", "other"),
     ("max_cost_microusd", 2000000), ("expires_at_epoch_s", 300)],
)
def test_mismatched_binding_refused(field: str, value: str | int) -> None:
    changed = replace(BINDING, **{field: value})
    assert check_grant(BINDING, VerifiedGrant(changed, True, False), now_epoch_s=100) == GrantRefusal.INVALID_BINDING


def test_expired_replayed_and_unverified() -> None:
    assert check_grant(BINDING, VerifiedGrant(BINDING, True, False), now_epoch_s=200) == GrantRefusal.EXPIRED
    assert check_grant(BINDING, VerifiedGrant(BINDING, True, True), now_epoch_s=100) == GrantRefusal.REPLAY
    assert check_grant(BINDING, VerifiedGrant(BINDING, False, False), now_epoch_s=100) == GrantRefusal.UNVERIFIED
    assert check_grant(BINDING, None, now_epoch_s=100) == GrantRefusal.UNVERIFIED
