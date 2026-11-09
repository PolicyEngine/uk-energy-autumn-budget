"""policyengine-uk 2.174.1 carries the Budget measures the dashboard assumes.

Household calculations (no dataset): the Household Energy Payment's
eligibility, amount, timing and income treatment, and the model's own
electricity VAT timing, which the dashboard's quarterly tariffs must match.
"""

from __future__ import annotations

import pytest

pe = pytest.importorskip("policyengine")

from energy_budget.config import HEP_PARAMETER

VARS = [
    "household_energy_payment",
    "household_net_income",
    "hbai_household_net_income",
    "domestic_energy_vat",
    "vat_change",
]


def _household(region, band, year, reform=None, elec=1_050.0, gas=1_050.0):
    r = pe.uk.calculate_household(
        people=[{"age": 40, "employment_income": 20_000}],
        household={
            "region": region,
            "council_tax_band": band,
            "electricity_consumption": elec,
            "gas_consumption": gas,
        },
        year=year,
        reform=reform,
        extra_variables=VARS,
    )
    return {v: float(getattr(r.household, v)) for v in VARS}


@pytest.mark.parametrize(
    "region,band,paid",
    [
        ("NORTH_WEST", "A", 100),
        ("LONDON", "D", 100),
        ("NORTH_WEST", "E", 0),
        ("WALES", "B", 0),
        ("SCOTLAND", "A", 0),
        ("NORTHERN_IRELAND", "B", 0),
    ],
)
def test_household_energy_payment_eligibility(region, band, paid):
    assert _household(region, band, 2026)["household_energy_payment"] == paid
    # One-off: nothing in 2027-28.
    assert _household(region, band, 2027)["household_energy_payment"] == 0


def test_payment_counts_once_in_household_and_hbai_income():
    law = _household("NORTH_WEST", "B", 2026)
    without = _household("NORTH_WEST", "B", 2026, {HEP_PARAMETER: 0})
    assert without["household_energy_payment"] == 0
    assert law["household_net_income"] - without[
        "household_net_income"
    ] == pytest.approx(100)
    assert law["hbai_household_net_income"] - without[
        "hbai_household_net_income"
    ] == pytest.approx(100)


def test_model_vat_timing_matches_the_dashboard_law():
    """£1,050 of each fuel (5% VAT basis): £1,000 VAT-exclusive."""
    # FY 2026-27, GB: 0% from 1 Oct 2026 (187 of 365 days to 5 Apr 2027).
    gb26 = _household("NORTH_WEST", "B", 2026)["domestic_energy_vat"]
    assert gb26 == pytest.approx(1_000 * 0.05 * 178 / 365 + 50, abs=0.01)
    # FY 2027-28: 0% to 30 June 2027 (86 days), UK-wide.
    gb27 = _household("NORTH_WEST", "B", 2027)["domestic_energy_vat"]
    ni27 = _household("NORTHERN_IRELAND", "B", 2027)["domestic_energy_vat"]
    assert gb27 == pytest.approx(1_000 * 0.05 * 280 / 366 + 50, abs=0.01)
    assert ni27 == pytest.approx(gb27)
    # NI keeps 5% until 1 April 2027 (5 days of FY 2026-27 at 0%).
    ni26 = _household("NORTHERN_IRELAND", "B", 2026)["domestic_energy_vat"]
    assert ni26 == pytest.approx(1_000 * 0.05 * 360 / 365 + 50, abs=0.01)


def test_model_energy_vat_never_reaches_income_without_a_vat_reform():
    for year in (2026, 2027):
        assert _household("NORTH_WEST", "B", year)["vat_change"] == 0
        # Changing only the payment leaves VAT alone too.
        assert (
            _household("NORTH_WEST", "B", year, {HEP_PARAMETER: 0})["vat_change"] == 0
        )
