"""Checks the price path against figures Ofgem and the forecasters publish.

Every scenario is built from unit rates and standing charges, so a typo in
``TARIFFS`` or ``PRICE_PATH`` would silently move every result. These tests
also hold the price-update workflow together: each quarter's rates, status,
source and published figure must agree before a new forecast goes in.
"""

from __future__ import annotations

import pytest

from energy_budget import config
from energy_budget.config import (
    FY_QUARTERS,
    PRICE_PATH,
    TARIFFS,
    fuel_bill,
)
from energy_budget.prices import published_rates, quarter_rates


def _typical(rates, elec_kwh=2_700, gas_kwh=11_500):
    e_unit, e_sc = rates["elec"]
    g_unit, g_sc = rates["gas"]
    return (e_unit * elec_kwh + e_sc * 365 + g_unit * gas_kwh + g_sc * 365) / 100


def test_baseline_recosts_to_published_cap():
    # £1,641 on the pre-July TDCVs; the Bank of England quotes £1,477 on
    # the post-July ones.
    assert (
        abs(
            fuel_bill("apr_jun_2026", "elec") + fuel_bill("apr_jun_2026", "gas") - 1_641
        )
        < 1
    )
    assert abs(_typical(TARIFFS["apr_jun_2026"], 2_500, 9_500) - 1_477) < 1


@pytest.mark.parametrize("q", PRICE_PATH, ids=lambda q: q["key"])
def test_published_figure_matches_rates(q):
    """Each quarter's rates re-cost to the figure its source published."""
    if q["published_cap"] is None:
        assert q["kind"] == "Assumed"
        return
    tdcv = (2_700, 11_500) if q["published_tdcv"] == "old" else (2_500, 9_500)
    assert abs(_typical(published_rates(q["key"]), *tdcv) - q["published_cap"]) < 3


@pytest.mark.parametrize("q", PRICE_PATH, ids=lambda q: q["key"])
def test_price_path_metadata_is_consistent(q):
    assert q["kind"] in {"Announced", "Forecast", "Assumed"}
    assert q["published_tdcv"] in {"old", "new"}
    assert q["embedded_elec_vat"] in {0.0, 0.05}
    if q["kind"] == "Forecast":
        assert q["source_date"] and q["link"]
    if q["kind"] == "Announced":
        assert q["link"] and q["key"] in TARIFFS
    # A quarter is either published rates or a scaled total, never both.
    assert ("target" in q) != (q["key"] in TARIFFS)


def test_quarters_in_order():
    assert [q["key"] for q in PRICE_PATH] == FY_QUARTERS[2026] + FY_QUARTERS[2027]
    assert all(len(v) == 4 for v in FY_QUARTERS.values())


@pytest.mark.parametrize(
    "q", [q for q in PRICE_PATH if "target" in q], ids=lambda q: q["key"]
)
def test_2027_28_rates_hit_forecasts(q):
    # At the VAT rate the forecaster assumed, the rates reproduce its total.
    assert abs(_typical(published_rates(q["key"]), 2_500, 9_500) - q["target"]) < 0.5


def test_later_quarters_do_not_read_january_tariffs(monkeypatch):
    """Replacing January 2027 with Ofgem's cap must not move 2027-28."""
    before = {k: quarter_rates(k) for k in FY_QUARTERS[2027]}
    monkeypatch.setitem(
        TARIFFS, "jan_mar_2027", {"elec": (40.0, 70.0), "gas": (12.0, 40.0)}
    )
    assert quarter_rates("jan_mar_2027")["gas"] == (12.0, 40.0)
    for k in FY_QUARTERS[2027]:
        assert quarter_rates(k) == before[k]


def test_forecast_totals_unchanged():
    # The pre-Budget forecasts this dashboard has used since October 2026.
    targets = {q["key"]: q.get("target") for q in PRICE_PATH}
    assert targets["apr_jun_2027"] == 2_074
    assert targets["jul_sep_2027"] == 1_912
    assert targets["oct_dec_2027"] == 1_846
    assert targets["jan_mar_2028"] == 1_846
    assert config.FUEL_SPLIT_REFERENCE["elec"] == (30.28, 55.0)
    assert config.FUEL_SPLIT_REFERENCE["gas"] == (9.76, 31.0)
