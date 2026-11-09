"""Electricity VAT by quarter and nation, checked by hand (issue #10).

The Budget extends the zero rate to 30 June 2027 and expects it to apply in
Northern Ireland from April 2027. These tests pin when each rate applies and
that every VAT change enters a bill once, through the quarter's tariff.
"""

from __future__ import annotations

import numpy as np
import pytest

from energy_budget.budget_options import (
    analytic_supports,
    held_bills,
    household_bills,
    typical,
    vat_saving,
)
from energy_budget.config import ELEC_VAT, FY_QUARTERS
from energy_budget.prices import published_rates, quarter_rates

SEASONAL_ELEC_APR_JUN = (1 - 0.57) / 2


def test_post_budget_rates_by_quarter():
    gb, ni = ELEC_VAT["post_budget"]["GB"], ELEC_VAT["post_budget"]["NI"]
    assert [gb[k] for k in FY_QUARTERS[2026]] == [0.05, 0.05, 0.0, 0.0]
    assert [gb[k] for k in FY_QUARTERS[2027]] == [0.0, 0.05, 0.05, 0.05]
    assert [ni[k] for k in FY_QUARTERS[2026]] == [0.05] * 4
    assert [ni[k] for k in FY_QUARTERS[2027]] == [0.0, 0.05, 0.05, 0.05]


def test_pre_budget_counterfactual_rates():
    gb, ni = ELEC_VAT["pre_budget"]["GB"], ELEC_VAT["pre_budget"]["NI"]
    assert [gb[k] for k in FY_QUARTERS[2026]] == [0.05, 0.05, 0.0, 0.0]
    assert [gb[k] for k in FY_QUARTERS[2027]] == [0.05] * 4
    assert set(ni.values()) == {0.05}


def test_vat_applied_once_to_published_rates():
    # Supplier average for April-June 2027 was quoted at 5%: post-Budget it
    # is that rate divided by 1.05, and pre-Budget it is unchanged.
    pub = published_rates("apr_jun_2027")["elec"]
    assert quarter_rates("apr_jun_2027", "GB", "pre_budget")["elec"] == pytest.approx(
        pub
    )
    assert quarter_rates("apr_jun_2027", "GB")["elec"] == pytest.approx(
        tuple(x / 1.05 for x in pub)
    )
    # Oct-Dec 2026 was published VAT-free: GB unchanged, NI gets 5% back.
    pub = published_rates("oct_dec_2026")["elec"]
    assert quarter_rates("oct_dec_2026", "GB")["elec"] == pytest.approx(pub)
    assert quarter_rates("oct_dec_2026", "NI")["elec"] == pytest.approx(
        tuple(x * 1.05 for x in pub)
    )
    # Gas never changes.
    for k in FY_QUARTERS[2026] + FY_QUARTERS[2027]:
        assert quarter_rates(k, "NI", "pre_budget")["gas"] == quarter_rates(k)["gas"]


def test_typical_household_saving_by_hand():
    """2,700 kWh, GB, seasonal: the extension takes 5% off April-June 2027 only."""
    unit, standing = (x / 1.05 for x in published_rates("apr_jun_2027")["elec"])
    by_hand = (SEASONAL_ELEC_APR_JUN * 2_700 * unit + 365 / 4 * standing) * 0.05 / 100
    model = typical(2027, law="pre_budget")["bill"] - typical(2027)["bill"]
    assert model == pytest.approx(by_hand, abs=0.005)
    assert by_hand == pytest.approx(11.45, abs=0.01)
    # No change in 2026-27 in Great Britain.
    assert typical(2026, law="pre_budget")["bill"] == pytest.approx(
        typical(2026)["bill"]
    )


def _households():
    kwh = {
        "elec": np.array([2_700.0, 2_700.0, 0.0]),
        "gas": np.array([11_500.0, 0.0, 0.0]),
    }
    connected = {
        "elec": np.array([True, True, True]),
        "gas": np.array([True, False, False]),
    }
    is_ni = np.array([False, True, False])
    return kwh, connected, is_ni


def test_budget_vat_saving_by_household():
    kwh, connected, is_ni = _households()
    s26 = vat_saving(
        2026, kwh, connected, is_ni, "seasonal", "pre_budget", "post_budget"
    )
    s27 = vat_saving(
        2027, kwh, connected, is_ni, "seasonal", "pre_budget", "post_budget"
    )
    # 2026-27: nobody (GB already at 0% from October; NI keeps 5% to March).
    assert s26 == pytest.approx([0, 0, 0])
    # 2027-28: GB and NI households with the same use save the same; a
    # zero-use household saves 5% of one quarter's standing charge.
    assert s27[0] == pytest.approx(11.45, abs=0.01)
    assert s27[1] == pytest.approx(s27[0])
    standing = published_rates("apr_jun_2027")["elec"][1] / 1.05
    assert s27[2] == pytest.approx(365 / 4 * standing * 0.05 / 100)


def test_extend_option_is_additional_to_the_budget():
    kwh, connected, is_ni = _households()
    fc = household_bills(2027, kwh, connected, is_ni)
    held = held_bills(kwh, connected)
    extra = analytic_supports(2027, fc, held, kwh, connected, is_ni)["extend_vat_cut"]
    whole_year = vat_saving(
        2027, kwh, connected, is_ni, "seasonal", "pre_budget", "extend_2027_28"
    )
    budget = vat_saving(
        2027, kwh, connected, is_ni, "seasonal", "pre_budget", "post_budget"
    )
    # The option plus the Budget's extension is the whole year at 0%.
    assert extra + budget == pytest.approx(whole_year)
    # By hand for the GB household: 5% of July-March electricity.
    shares = (0.215, 0.285, 0.285)
    by_hand = 0.0
    for k, s in zip(FY_QUARTERS[2027][1:], shares, strict=True):
        unit, standing = (x / 1.05 for x in quarter_rates(k)["elec"])
        by_hand += (s * 2_700 * unit + 365 / 4 * standing) * 0.05 / 100
    assert extra[0] == pytest.approx(by_hand)
    # UK-wide: Northern Ireland's household gains the same.
    assert extra[1] == pytest.approx(extra[0])
