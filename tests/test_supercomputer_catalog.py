"""No-network tests for read-only SKU discovery."""
import json

import pytest

from gpu_broker.supercomputer_catalog import CATALOG_URL, TIMEOUT_S, discover_skus


class FakeTransport:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.calls: list[tuple[str, str, float]] = []

    def get(self, url: str, *, token: str, timeout_s: float) -> bytes:
        self.calls.append((url, token, timeout_s))
        return json.dumps(self.payload).encode()


def test_discovery_uses_only_fixed_catalog_endpoint() -> None:
    transport = FakeTransport({"skus": [{"name": "h100", "vram_gb": 80, "cost_per_hr": 3.16, "availability": "live"}]})
    test_credential = "fixture-" + "credential"
    quotes = discover_skus(token=test_credential, observed_at_s=100, transport=transport)
    assert quotes[0].sku == "h100"
    assert transport.calls == [(CATALOG_URL, test_credential, TIMEOUT_S)]


@pytest.mark.parametrize("token", ["", "bad\r\nHeader: injected"])
def test_rejects_invalid_token_before_transport(token: str) -> None:
    transport = FakeTransport({"skus": []})
    with pytest.raises(ValueError):
        discover_skus(token=token, observed_at_s=100, transport=transport)
    assert not transport.calls


def test_rejects_invalid_json_shape() -> None:
    with pytest.raises(ValueError):
        test_credential = "fixture-" + "credential"
        discover_skus(token=test_credential, observed_at_s=100, transport=FakeTransport([]))
