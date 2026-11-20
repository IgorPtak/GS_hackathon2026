"""Unit tests for payload variation and helpers of the event generator."""

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
import generator  # noqa: E402


def test_parse_mix_weights() -> None:
    assert generator.parse_mix("rates:1,pricing:3") == {"rates": 1.0, "pricing": 3.0}
    with pytest.raises(ValueError):
        generator.parse_mix("bogus:1")


def test_percentile() -> None:
    assert generator.percentile([], 50) == 0.0
    assert generator.percentile([float(v) for v in range(1, 101)], 99) == 99.0


def test_rates_items_vary_trade_id() -> None:
    factory = generator.PayloadFactory(random.Random(1))
    ids = set()
    for _ in range(20):
        payload = factory.build("rates").payload
        assert payload is not None
        ids.add(payload["payload"]["tradeId"])
    assert len(ids) == 20


def test_duplicates_are_exact_copies() -> None:
    factory = generator.PayloadFactory(random.Random(1))
    pacer = generator.Pacer(factory, {"rates": 1.0}, 1.0, 0.0, False)
    first = factory.build("rates")
    pacer.history.append(first)
    assert pacer.next_item() is first


def test_pricing_line_matches_log_format() -> None:
    line = generator.PayloadFactory(random.Random(2)).build("pricing").log_line
    assert line is not None and " ERROR pricing-engine instrument=" in line
