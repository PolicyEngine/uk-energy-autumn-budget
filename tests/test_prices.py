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


def test_neg_saving_on_block_and_gas_porting():
    import numpy as np

    from energy_budget.budget_options import neg_support, year_quarters
    from energy_budget.config import quarter_shares

    kwh = {
        "elec": np.array([5_000.0, 5_000.0, 1_000.0]),
        "gas": np.array([20_000.0, 0, 0]),
    }
    connected = {"elec": np.array([True] * 3), "gas": np.array([True, False, False])}
    saving = neg_support(2026, kwh, connected, np.zeros(3, dtype=bool))

    def rate(f):
        q = year_quarters(2026)[f]
        return sum(s * u for s, (u, _) in zip(quarter_shares(f), q)) / 100

    # Gas home above both blocks: the whole of each block is discounted.
    assert saving[0] == pytest.approx(
        1_800 * rate("elec") * 0.25 + 6_100 * rate("gas") * 0.4
    )
    # No gas: electricity block is 1,800 + 6,100 / 2 = 4,850 kWh.
    assert saving[1] == pytest.approx(4_850 * rate("elec") * 0.25)
    # Below the block: only the kWh used are discounted.
    assert saving[2] == pytest.approx(1_000 * rate("elec") * 0.25)
