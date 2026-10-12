"""Bills from kWh with unit rates and standing charges kept separate (C1, A7, A1).

The worked examples are those in PolicyEngine/uk-energy-autumn-budget#1.
"""

from __future__ import annotations

import numpy as np
import pytest

from energy_budget.bills import (
    annual_bill,
    fuel_bill_for_profile,
    household_kwh,
    kwh_from_spend,
    reference_tariff,
    typical_bill,
)
from energy_budget.budget_options import (
    HELD_QUARTERS,
    cap_freeze_support,
    held_bills,
    household_bills,
    year_quarters,
)
from energy_budget.config import QEP_FY2024_25, TARIFFS, quarter_shares

GAS_2026 = year_quarters(2026)["gas"]
GAS_HELD = HELD_QUARTERS["gas"]


def _gas(kwh, quarters, profile="equal"):
    return float(fuel_bill_for_profile(kwh, True, quarters, "gas", profile))


def _multiplier_increase(kwh):
    """The old method: scale the whole bill by the typical-bill ratio."""
    ratio = _gas(11_500, GAS_2026) / _gas(11_500, GAS_HELD)
    return _gas(kwh, GAS_HELD) * (ratio - 1)


def test_low_use_gas_worked_example():
    # 3,000 kWh of gas: £278.38 at April-June 2026 tariffs, £339.41 at the
    # four 2026-27 quarterly tariffs with equal quarterly use.
    assert _gas(3_000, GAS_HELD) == pytest.approx(278.38, abs=0.005)
    assert _gas(3_000, GAS_2026) == pytest.approx(339.41, abs=0.005)
    increase = _gas(3_000, GAS_2026) - _gas(3_000, GAS_HELD)
    assert increase == pytest.approx(61.04, abs=0.01)
    # The whole-bill multiplier overstated it by £21.66 (35.5%).
    assert _multiplier_increase(3_000) == pytest.approx(82.70, abs=0.01)
    assert _multiplier_increase(3_000) - increase == pytest.approx(21.66, abs=0.01)


def test_high_use_gas_error_is_opposite():
    increase = _gas(20_000, GAS_2026) - _gas(20_000, GAS_HELD)
    assert increase - _multiplier_increase(20_000) == pytest.approx(21.66, abs=0.01)


def test_typical_bill_equal_and_seasonal():
    q = year_quarters(2026)
    assert typical_bill(q, "equal") == pytest.approx(1_923.34, abs=0.005)
    assert typical_bill(q, "seasonal") == pytest.approx(1_995.83, abs=0.005)
    # A constant tariff is unaffected by the profile.
    assert typical_bill(HELD_QUARTERS, "seasonal") == pytest.approx(1_641.19, abs=0.01)


def test_seasonal_shares():
    assert quarter_shares("gas") == pytest.approx((0.125, 0.125, 0.375, 0.375))
    assert quarter_shares("elec") == pytest.approx((0.215, 0.215, 0.285, 0.285))
    assert sum(quarter_shares("elec")) == pytest.approx(1)


def test_kwh_round_trip_at_reference_tariff():
    unit, fixed = QEP_FY2024_25["LONDON"]["gas"]
    spend = fixed + unit / 100 * np.array([3_000.0, 20_000.0])
    kwh, connected = household_kwh(spend, ["LONDON", "LONDON"], "gas")
    assert kwh == pytest.approx([3_000, 20_000])
    assert connected.all()


def test_unconnected_households_pay_no_standing_charge():
    kwh, connected = household_kwh(np.array([0.0]), ["LONDON"], "gas")
    assert kwh[0] == 0 and not connected[0]
    bill = annual_bill(kwh, connected, GAS_2026, quarter_shares("gas"))
    assert bill[0] == 0


def test_spend_below_fixed_cost_pays_standing_only():
    assert kwh_from_spend(np.array([50.0]), 6.0, 113.0)[0] == 0
    bill = annual_bill(np.array([0.0]), np.array([True]), GAS_HELD, (0.25,) * 4)
    assert bill[0] == pytest.approx(TARIFFS["apr_jun_2026"]["gas"][1] * 365 / 100)


def test_northern_ireland_keeps_electricity_vat():
    gb = year_quarters(2026)["elec"]
    ni = year_quarters(2026, ni=True)["elec"]
    assert ni[:2] == gb[:2]
    assert ni[2][0] == pytest.approx(gb[2][0] * 1.05)
    assert ni[3][1] == pytest.approx(gb[3][1] * 1.05)
    assert year_quarters(2026, ni=True)["gas"] == year_quarters(2026)["gas"]


def test_cap_freeze_restores_april_tariffs():
    kwh = {"elec": np.array([0.0, 2_700.0]), "gas": np.array([3_000.0, 0.0])}
    connected = {"elec": np.array([False, True]), "gas": np.array([True, False])}
    is_ni = np.array([False, False])
    fc = household_bills(2026, kwh, connected, is_ni, "equal")
    held = held_bills(kwh, connected)
    support = cap_freeze_support(fc, held)
    # Gas-only household at 3,000 kWh: exactly the £61.04 increase.
    assert support[0] == pytest.approx(61.04, abs=0.01)
    # Never negative; after the subsidy the bill is the April-June bill.
    assert (support >= 0).all()
    after = fc["elec"] + fc["gas"] - support
    assert after == pytest.approx(
        np.minimum(fc["elec"] + fc["gas"], held["elec"] + held["gas"])
    )


def test_reference_tariff_bases():
    unit, fixed = reference_tariff(["SCOTLAND", "NOWHERE"], "elec")
    assert unit[0] == pytest.approx(QEP_FY2024_25["SCOTLAND"]["elec"][0])
    assert fixed[1] > 0  # missing region falls back to the UK average
    unit, fixed = reference_tariff(["LONDON"], "gas", "ofgem_cy2025_national")
    assert 6 < unit[0] < 7 and 110 < fixed[0] < 125
    with pytest.raises(ValueError):
        reference_tariff(["LONDON"], "gas", "nonsense")
