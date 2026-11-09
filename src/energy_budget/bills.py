"""Household bills from kWh: unit rates and standing charges kept separate.

Pure numpy, no PolicyEngine import, so the tests can exercise it directly.

Each household's annual electricity and gas kWh come straight from the
dataset export (see ``config``). ``annual_bill`` costs them over the four
quarters of a financial year: each quarter's unit rate applies to that
quarter's share of annual use, and each quarter's standing charge to a
quarter of the year's days. Households not connected to a fuel pay no
standing charge for it.
"""

from __future__ import annotations

import numpy as np

from .config import QEP_CY2024, quarter_shares

FUELS = ("elec", "gas")


def connections(elec_spend, gas_spend):
    """Connection flags per fuel from the dataset's spending columns.

    Gas: no spend means no mains gas. Electricity: GB households all spend at
    least their region's fixed cost; in Northern Ireland, where the fixed
    cost is zero, zero spend is treated as no connection.
    """
    return {
        "elec": np.asarray(elec_spend, dtype=float) > 0,
        "gas": np.asarray(gas_spend, dtype=float) > 0,
    }


def price_basis_residual(spend, kwh, region, fuel):
    """Spend minus (fixed cost + unit rate x kWh) at QEP CY2024, connected only.

    The dataset prices its kWh on this basis, so the residual is zero to
    rounding; a non-zero residual means the export is on another basis.
    """
    spend = np.asarray(spend, dtype=float)
    kwh = np.asarray(kwh, dtype=float)
    region = np.asarray(region).astype(str)
    unit = np.array([QEP_CY2024[r][fuel][0] for r in region]) / 100
    fixed = np.array([QEP_CY2024[r][fuel][1] for r in region])
    return np.where(spend > 0, spend - fixed - unit * kwh, 0.0)


def annual_bill(kwh, connected, quarters, shares):
    """Annual £ bill for one fuel over four quarters.

    ``quarters`` is four (unit p/kWh, standing p/day) tuples in financial-
    year order; ``shares`` the share of annual kWh used in each. Each
    quarter carries 365/4 days of standing charge.
    """
    if len(quarters) != 4 or len(shares) != 4:
        raise ValueError("annual_bill needs four quarters and four shares")
    if abs(sum(shares) - 1) > 1e-9:
        raise ValueError("quarter shares must sum to 1")
    unit = sum(s * q[0] for s, q in zip(shares, quarters))
    standing = sum(q[1] for q in quarters) / 4
    kwh = np.asarray(kwh, dtype=float)
    return np.where(connected, (unit * kwh + standing * 365) / 100, 0.0)


def fuel_bill_for_profile(kwh, connected, quarters, fuel, profile):
    return annual_bill(kwh, connected, quarters, quarter_shares(fuel, profile))


def typical_bill(quarters_by_fuel, profile, elec_kwh=2_700, gas_kwh=11_500):
    """Typical dual-fuel bill: ``quarters_by_fuel`` maps fuel -> four tariffs."""
    return float(
        fuel_bill_for_profile(elec_kwh, True, quarters_by_fuel["elec"], "elec", profile)
        + fuel_bill_for_profile(gas_kwh, True, quarters_by_fuel["gas"], "gas", profile)
    )
