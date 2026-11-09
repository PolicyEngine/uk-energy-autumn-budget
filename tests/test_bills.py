"""Bills from kWh with unit rates and standing charges kept separate (C1, A7, A1).

The worked examples are those in PolicyEngine/uk-energy-autumn-budget#1.
"""

from __future__ import annotations

import numpy as np
import pytest

from energy_budget.bills import (
    annual_bill,
    connections,
    fuel_bill_for_profile,
    price_basis_residual,
    typical_bill,
)
from energy_budget.budget_options import (
    cap_freeze_support,
    held_bills,
    household_bills,
)
from energy_budget.config import QEP_CY2024, TARIFFS, quarter_shares
from energy_budget.prices import HELD_QUARTERS, year_quarters

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


def test_price_basis_residual_is_zero_on_qep_cy2024():
    unit, fixed = QEP_CY2024["LONDON"]["gas"]
    kwh = np.array([3_000.0, 20_000.0, 0.0])
    spend = np.array([fixed + unit / 100 * 3_000, fixed + unit / 100 * 20_000, 0.0])
    assert price_basis_residual(spend, kwh, ["LONDON"] * 3, "gas") == pytest.approx(0)
    # A household priced on another basis shows up.
    assert price_basis_residual([spend[0] + 5], [3_000.0], ["LONDON"], "gas")[
        0
    ] == pytest.approx(5)


def test_connection_keeps_zero_use_separate_from_no_supply():
    # GB: spend equal to the fixed cost is connected with zero use;
    # no gas spend is no mains gas.
    fixed = QEP_CY2024["LONDON"]["elec"][1]
    c = connections([fixed, 600.0], [0.0, 500.0])
    assert c["elec"].tolist() == [True, True]
    assert c["gas"].tolist() == [False, True]
    zero_use = annual_bill(
        np.array([0.0]), c["elec"][:1], HELD_QUARTERS["elec"], (0.25,) * 4
    )
    assert zero_use[0] == pytest.approx(TARIFFS["apr_jun_2026"]["elec"][1] * 365 / 100)
    no_gas = annual_bill(np.array([0.0]), c["gas"][:1], GAS_2026, quarter_shares("gas"))
    assert no_gas[0] == 0


def test_northern_ireland_keeps_electricity_vat_until_april_2027():
    gb = year_quarters(2026)["elec"]
    ni = year_quarters(2026, "NI")["elec"]
    assert ni[:2] == gb[:2]
    assert ni[2][0] == pytest.approx(gb[2][0] * 1.05)
    assert ni[3][1] == pytest.approx(gb[3][1] * 1.05)
    assert year_quarters(2026, "NI")["gas"] == year_quarters(2026)["gas"]
    # From April 2027 the Budget's extension applies UK-wide.
    assert year_quarters(2027, "NI") == year_quarters(2027)


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
