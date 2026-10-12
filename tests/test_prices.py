"""Checks the price path against figures Ofgem and the forecasters publish.

Every scenario is built from unit rates and standing charges, so a typo in
``TARIFFS`` would silently move every result.
"""

from __future__ import annotations

import pytest

from energy_budget.budget_options import FORECAST_2027_28, _quarter_rates_2027_28
from energy_budget.config import CY2025_PERIODS, fuel_bill


def _typical(period, elec_kwh=None, gas_kwh=None):
    return fuel_bill(period, "elec", elec_kwh) + fuel_bill(period, "gas", gas_kwh)


def test_baseline_recosts_to_published_cap():
    # £1,641 on the pre-July TDCVs; the Bank of England quotes £1,477 on
    # the post-July ones.
    assert abs(_typical("apr_jun_2026") - 1_641) < 1
    assert abs(_typical("apr_jun_2026", 2_500, 9_500) - 1_477) < 1


def test_2026_quarters_match_ofgem_and_cornwall():
    assert abs(_typical("jul_sep_2026") - 1_862) < 2
    assert abs(_typical("jul_sep_2026", 2_500, 9_500) - 1_663) < 2
    assert abs(_typical("oct_dec_2026", 2_500, 9_500) - 1_723) < 2
    assert abs(_typical("jan_mar_2027_cornwall", 2_500, 9_500) - 1_999) < 3


@pytest.mark.parametrize(
    "period,cap", list(zip(CY2025_PERIODS, [1_738, 1_849, 1_720, 1_755]))
)
def test_2025_quarters_match_ofgem(period, cap):
    # The KWH_BASIS="ofgem_cy2025_national" sensitivity rests on these.
    assert abs(_typical(period) - cap) < 1


@pytest.mark.parametrize("q", FORECAST_2027_28, ids=lambda q: q["key"])
def test_2027_28_rates_hit_forecasts(q):
    rates = _quarter_rates_2027_28(q["target"], q["elec_vat_in_target"])
    elec = (rates["elec"][0] * 2_500 + rates["elec"][1] * 365) / 100
    gas = (rates["gas"][0] * 9_500 + rates["gas"][1] * 365) / 100
    # The result always carries 5% VAT on electricity; a forecast quoted at
    # the 0% rate matches once that VAT is taken back out.
    if not q["elec_vat_in_target"]:
        elec /= 1.05
    assert abs(elec + gas - q["target"]) < 0.5
