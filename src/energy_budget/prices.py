"""Quarterly tariffs by nation and VAT law.

Pure Python, no PolicyEngine import, so the tests can exercise it directly.

Each quarter's published rates carry the electricity VAT rate the publisher
applied (``embedded_elec_vat`` in ``PRICE_PATH``). ``quarter_rates`` takes the
electricity unit rate and standing charge back to their VAT-exclusive level
and applies the rate that the chosen law (``ELEC_VAT``) sets for that quarter
and nation, so a VAT change enters the bills exactly once, through the
tariffs. Gas keeps the 5% reduced rate throughout.

Quarters from April 2027 have only a forecast total. Each is split between
fuels by scaling ``FUEL_SPLIT_REFERENCE`` (Cornwall Insight's January 2027
rates as forecast on 30 Sep 2026) by one factor that hits the total on the
new TDCVs, with the total read at the VAT rate the forecaster assumed.
"""

from __future__ import annotations

from .config import (
    BASELINE_LAW,
    ELEC_VAT,
    FUEL_SPLIT_REFERENCE,
    FY_QUARTERS,
    NEW_TDCV,
    PRICE_PATH,
    TARIFFS,
)

FUELS = ("elec", "gas")
NATIONS = ("GB", "NI")
_BY_KEY = {q["key"]: q for q in PRICE_PATH}


def quarter(key):
    """The ``PRICE_PATH`` entry for a quarter."""
    return _BY_KEY[key]


def scaled_rates(target, embedded_elec_vat):
    """Rates hitting a forecast total, with electricity at ``embedded_elec_vat``.

    The reference split's electricity is first moved to the forecaster's VAT
    rate, then both fuels are scaled by one factor so that the typical bill on
    the new TDCVs equals ``target``.
    """
    ref_vat = FUEL_SPLIT_REFERENCE["embedded_elec_vat"]
    e_unit, e_sc = (
        x / (1 + ref_vat) * (1 + embedded_elec_vat)
        for x in FUEL_SPLIT_REFERENCE["elec"]
    )
    g_unit, g_sc = FUEL_SPLIT_REFERENCE["gas"]
    total = (
        e_unit * NEW_TDCV["elec"] + e_sc * 365 + g_unit * NEW_TDCV["gas"] + g_sc * 365
    ) / 100
    g = target / total
    return {"elec": (e_unit * g, e_sc * g), "gas": (g_unit * g, g_sc * g)}


def published_rates(key):
    """A quarter's rates as published (electricity at its embedded VAT)."""
    q = quarter(key)
    if "target" in q:
        return scaled_rates(q["target"], q["embedded_elec_vat"])
    return {f: tuple(TARIFFS[key][f]) for f in FUELS}


def quarter_rates(key, nation="GB", law=BASELINE_LAW):
    """A quarter's (unit p/kWh, standing p/day) per fuel under a VAT law."""
    q = quarter(key)
    rates = published_rates(key)
    factor = (1 + ELEC_VAT[law][nation][key]) / (1 + q["embedded_elec_vat"])
    rates["elec"] = tuple(x * factor for x in rates["elec"])
    return rates


def year_quarters(year, nation="GB", law=BASELINE_LAW):
    """Four quarterly tariffs per fuel for a financial year, in FY order."""
    if year not in FY_QUARTERS:
        raise ValueError(f"No price path for {year}")
    rates = [quarter_rates(k, nation, law) for k in FY_QUARTERS[year]]
    return {f: [r[f] for r in rates] for f in FUELS}


HELD_QUARTERS = {f: [published_rates("apr_jun_2026")[f]] * 4 for f in FUELS}
