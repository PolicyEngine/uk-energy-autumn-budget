"""Household bills from kWh: unit rates and standing charges kept separate.

Pure numpy, no PolicyEngine import, so the tests can exercise it directly.

A bill is costed in two steps:

1. ``kwh_from_spend`` recovers each household's annual kWh from its dataset
   spend at the dataset's reference tariff (unit rate + fixed cost).
2. ``annual_bill`` re-costs those kWh over the four quarters of a financial
   year: each quarter's unit rate applies to that quarter's share of annual
   use, and each quarter's standing charge to a quarter of the year's days.

Households with no spend on a fuel are not connected to it and pay no
standing charge.
"""

from __future__ import annotations

import numpy as np

from .config import (
    KWH_BASIS,
    OFGEM_CY2025_REFERENCE,
    QEP_CY2024,
    QEP_CY2024_UK,
    quarter_shares,
)

FUELS = ("elec", "gas")


def kwh_from_spend(spend, unit_p, fixed_gbp):
    """Annual kWh from annual spend at a unit rate (p/kWh) and fixed cost (£/yr).

    Spend below the fixed cost gives zero kWh (the household pays the
    standing charge only). Zero spend gives zero kWh.
    """
    spend = np.asarray(spend, dtype=float)
    unit = np.asarray(unit_p, dtype=float) / 100
    return np.where(spend > 0, np.maximum(spend - fixed_gbp, 0.0) / unit, 0.0)


def reference_tariff(region, fuel, basis=KWH_BASIS):
    """Per-household reference (unit p/kWh, fixed £/yr) arrays for a fuel."""
    region = np.asarray(region).astype(str)
    if basis == "qep_cy2024_regional":
        unit = np.array([QEP_CY2024.get(r, QEP_CY2024_UK)[fuel][0] for r in region])
        fixed = np.array([QEP_CY2024.get(r, QEP_CY2024_UK)[fuel][1] for r in region])
        return unit, fixed
    if basis == "ofgem_cy2025_national":
        unit, fixed = OFGEM_CY2025_REFERENCE[fuel]
        return np.full(len(region), unit), np.full(len(region), fixed)
    raise ValueError(f"Unknown KWH_BASIS {basis!r}")


def household_kwh(spend, region, fuel, basis=KWH_BASIS):
    """Annual kWh and connection flag from dataset spend."""
    unit, fixed = reference_tariff(region, fuel, basis)
    spend = np.asarray(spend, dtype=float)
    return kwh_from_spend(spend, unit, fixed), spend > 0


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
