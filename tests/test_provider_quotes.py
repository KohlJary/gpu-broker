"""Pure provider snapshot tests: no network, secrets or GPUs."""
import pytest

from gpu_broker.provider_quotes import estimate_compute_usd, parse_quote

QUOTE = {
    "provider": "example-remote",
    "sku": "accelerator-80g",
    "memory_gib": 80,
    "hourly_usd": 2.0,
    "currency": "USD",
    "source": "offline-fixture",
}


def test_snapshot_and_compute_estimate() -> None:
    quote = parse_quote(QUOTE, observed_at_s=100.0)
    assert quote.capability.remote
    assert quote.capability.memory_bytes == 80 * 1024**3
    assert estimate_compute_usd(quote, duration_s=1800) == 1.0


@pytest.mark.parametrize(
    "change",
    [
        {"currency": "EUR"},
        {"hourly_usd": -1},
        {"hourly_usd": float("nan")},
        {"memory_gib": 0},
        {"memory_gib": True},
        {"provider": ""},
        {"source": ""},
    ],
)
def test_invalid_quote_refused(change: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        parse_quote(QUOTE | change, observed_at_s=100.0)


def test_invalid_duration_refused() -> None:
    quote = parse_quote(QUOTE, observed_at_s=100.0)
    with pytest.raises(ValueError):
        estimate_compute_usd(quote, duration_s=float("inf"))
