YEAR = 2026

# Country / nation filter (default: whole UK)
# Valid values: "UK", "ENGLAND", "SCOTLAND", "WALES", "NORTHERN_IRELAND"
COUNTRY = "UK"

ENGLISH_REGIONS = {
    "EAST_MIDLANDS",
    "EAST_OF_ENGLAND",
    "LONDON",
    "NORTH_EAST",
    "NORTH_WEST",
    "SOUTH_EAST",
    "SOUTH_WEST",
    "WEST_MIDLANDS",
    "YORKSHIRE",
}

REGION_TO_COUNTRY = {r: "ENGLAND" for r in ENGLISH_REGIONS}
REGION_TO_COUNTRY["SCOTLAND"] = "SCOTLAND"
REGION_TO_COUNTRY["WALES"] = "WALES"
REGION_TO_COUNTRY["NORTHERN_IRELAND"] = "NORTHERN_IRELAND"

# ── Price baseline ──────────────────────────────────────────────────────
#
# The baseline is the pre-conflict April-June 2026 Ofgem cap: £1,641 for a
# typical dual-fuel direct-debit household on the pre-July Typical Domestic
# Consumption Values (2,700 kWh electricity, 11,500 kWh gas). PolicyEngine UK
# uprates electricity_consumption and gas_consumption with the pre-conflict
# OBR CPI index, so none of the conflict shock is in the baseline.
#
# Ofgem cut the TDCVs to 2,500 / 9,500 kWh on 1 July 2026, so the published
# cap levels from July onward (£1,663, £1,723) and Cornwall Insight's
# forecasts are on a different basis from £1,641 and cannot be divided by it.
# Every scenario below is therefore built from unit rates and standing
# charges, which do not depend on the TDCV, and re-costed at the OLD TDCVs
# so that it is comparable with the £1,641 baseline. Check: the April-June
# rates below re-cost to £1,641.2 at the old TDCVs and to £1,477 at the new
# ones (the Bank of England's July 2026 MPR quotes £1,477).
CURRENT_CAP = 1_641
TDCV_ELEC_KWH = 2_700
TDCV_GAS_KWH = 11_500

# Direct-debit GB averages: unit rate (p/kWh) and standing charge (p/day).
# Electricity is VAT-free from 1 Oct 2026 to 31 Mar 2027 (Ofgem: without
# that change the October rise would have been ~£45 higher), so the
# October and January electricity rates already include the VAT removal.
# Sources:
#   Apr-Jun 2026, Jul-Sep 2026, Oct-Dec 2026: Ofgem, "Energy price cap unit
#     rates and standing charges"
#     https://www.ofgem.gov.uk/your-energy-supply/your-energy-bill/energy-price-cap-unit-rates-and-standing-charges
#     https://www.ofgem.gov.uk/press-release/energy-price-cap-will-rise-4-october-2026
#   Jan-Mar 2027: Cornwall Insight forecast, 30 Sep 2026 (close of 28 Sep),
#     Figure 2 (£1,999.28 on the new TDCVs: £959.44 elec + £1,039.84 gas)
#     https://www.cornwall-insight.com/predictions-and-insights-into-the-default-tariff-cap/
TARIFFS = {
    # Calendar 2025, used only to rebase the dataset (see PRICE_REBASE).
    # Source: Ofgem quarterly cap announcements; each re-costs to the
    # published cap (£1,738 / £1,849 / £1,720 / £1,755) at the old TDCVs.
    #   https://www.ofgem.gov.uk/news/changes-energy-price-cap-between-1-april-and-30-june-2025
    #   https://www.ofgem.gov.uk/news/changes-energy-price-cap-between-1-july-and-30-september-2025
    #   https://www.ofgem.gov.uk/news/changes-energy-price-cap-between-1-october-and-31-december-2025
    "jan_mar_2025": {"elec": (24.86, 60.97), "gas": (6.34, 31.65)},
    "apr_jun_2025": {"elec": (27.03, 53.80), "gas": (6.99, 32.67)},
    "jul_sep_2025": {"elec": (25.73, 51.37), "gas": (6.33, 29.82)},
    "oct_dec_2025": {"elec": (26.35, 53.68), "gas": (6.29, 34.03)},
    "apr_jun_2026": {"elec": (24.67, 57.21), "gas": (5.74, 29.09)},
    "jul_sep_2026": {"elec": (26.11, 57.19), "gas": (7.33, 29.04)},
    "oct_dec_2026": {"elec": (26.32, 54.83), "gas": (7.97, 29.68)},
    "jan_mar_2027_cornwall": {"elec": (30.28, 55.0), "gas": (9.76, 31.0)},
}


def fuel_bill(period, fuel, kwh=None):
    """Annual £ bill for one fuel at a tariff period's rates."""
    unit_p, standing_p = TARIFFS[period][fuel]
    if kwh is None:
        kwh = TDCV_ELEC_KWH if fuel == "elec" else TDCV_GAS_KWH
    return (unit_p * kwh + standing_p * 365) / 100


def _fuel_pcts(periods):
    """Electricity and gas price changes vs April-June 2026, averaging the
    annual bill over the listed periods (each held for an equal share)."""
    out = {}
    for fuel in ("elec", "gas"):
        base = fuel_bill("apr_jun_2026", fuel)
        new = sum(fuel_bill(p, fuel) for p in periods) / len(periods)
        out[fuel] = new / base - 1
    return out


def _scenario(label, periods, published_cap, source, kind):
    pcts = _fuel_pcts(periods)
    old_basis = sum(
        sum(fuel_bill(p, f) for p in periods) / len(periods) for f in ("elec", "gas")
    )
    return {
        "label": label,
        "elec_pct": pcts["elec"],
        "gas_pct": pcts["gas"],
        # Typical bill re-costed on the pre-July TDCVs (comparable to £1,641).
        "new_cap": round(old_basis),
        # Figure as published on the post-July TDCVs, where one exists.
        "published_cap": published_cap,
        "source": source,
        "kind": kind,
    }


CY2025_PERIODS = ["jan_mar_2025", "apr_jun_2025", "jul_sep_2025", "oct_dec_2025"]

# ── Dataset price basis ─────────────────────────────────────────────────
#
# Microcosm UK binds electricity_consumption and gas_consumption to ONS
# Consumer Trends COICOP 04.5.1 / 04.5.2 for calendar 2025 (£26.52bn /
# £15.34bn) and does not uprate them by year (PolicyEngine/microcosm#1113),
# so the dataset's bills are at CY2025 prices. The analysis baseline is
# April-June 2026 prices, so each fuel is rebased by the ratio of its
# typical bill in April-June 2026 to its CY2025 average.
PRICE_REBASE = {
    fuel: fuel_bill("apr_jun_2026", fuel)
    / (sum(fuel_bill(p, fuel) for p in CY2025_PERIODS) / len(CY2025_PERIODS))
    for fuel in ("elec", "gas")
}

# Price scenarios. Each is held for a full year: the model's period is a
# year, so "Oct-Dec 2026" means "a year at October-December 2026 prices".
# The 2026-27 average weights the four quarters equally; gas use is
# concentrated in October-March, so an equal-weight average understates the
# gas cost of the year.
PRICE_SCENARIOS = {
    "Jul-Sep 2026 (Ofgem)": _scenario(
        "Jul-Sep 2026 (Ofgem)",
        ["jul_sep_2026"],
        1_663,
        "Ofgem cap, Jul-Sep 2026",
        "outturn",
    ),
    "Oct-Dec 2026 (Ofgem)": _scenario(
        "Oct-Dec 2026 (Ofgem)",
        ["oct_dec_2026"],
        1_723,
        "Ofgem cap, announced 26 Aug 2026",
        "outturn",
    ),
    "2026-27 average": _scenario(
        "2026-27 average",
        ["apr_jun_2026", "jul_sep_2026", "oct_dec_2026", "jan_mar_2027_cornwall"],
        None,
        "Ofgem caps Apr-Dec 2026 + Cornwall Insight Jan-Mar 2027, equal weights",
        "path",
    ),
    "Jan-Mar 2027 (Cornwall Insight)": _scenario(
        "Jan-Mar 2027 (Cornwall Insight)",
        ["jan_mar_2027_cornwall"],
        1_999,
        "Cornwall Insight forecast, 30 Sep 2026",
        "forecast",
    ),
}

# Context only — these do not enter any calculation.
#
# OBR: the March 2026 Economic and fiscal outlook (3 Mar 2026) conditioned
# on market prices to 22 January 2026, before the conflict; the OBR says
# the Middle East escalation came after it closed the forecast. Its gas
# price path is therefore the no-conflict counterfactual, not a forecast of
# the shock. The next EFO (28 Oct 2026) will be the first OBR view after it.
# Gas prices: Table A.3, financial years.
# https://obr.uk/efo/economic-and-fiscal-outlook-march-2026/
OBR_MARCH_2026 = {
    "gas_price_gbp_per_therm": {"2025-26": 0.89, "2026-27": 0.74, "2027-28": 0.64},
    "cpi_pct": {"2026": 2.3, "2027": 2.0},
    "market_data_to": "22 Jan 2026",
}
# Bank of England, September 2026 MPC minutes: staff projection on energy
# futures to 14 Sep has CPI around 3.75% in 2026 Q4 and slightly above 4% in
# early 2027; the Q1 2027 cap "expected to rise substantially further".
# https://www.bankofengland.co.uk/monetary-policy-summary-and-minutes/2026/september-2026
BOE_SEPT_2026 = {"cpi_2026q4_pct": 3.75, "cpi_early_2027_pct": "slightly above 4"}
# Supplier forecasts for Jan-Mar 2027 (British Gas, EDF, E.ON Next average,
# ~£2,074-2,085 on the new TDCVs) publish no electricity/gas split, so they
# are not modelled as a scenario; they sit ~4% above Cornwall Insight.

# Income-differentiated short-run price elasticities of household energy
# demand. The D1 (−0.64) and D10 (−0.11) endpoints are reported by
# Priesmann & Praktiknjo (2025) for German gas; the interior values
# (D2-D9) are our own linear interpolation between those endpoints and
# are not a result of that paper. A flat or smoothly monotone pattern
# between endpoints is consistent with Priesmann's reported trend but
# any specific interior shape is a modelling choice.
#
# The behavioural response for each household is computed from its own
# decile's ε rather than a population-mean value, so the progressivity
# of the shock is captured rather than averaged away. A uniform value
# (e.g. the −0.15 Labandeira et al. 2017 meta-analytic mean) would
# understate how sharply low-income households are forced to cut and
# overstate the bill-saving higher-income households achieve.
#
# For reporting headline aggregate statistics ("average household gives
# up X% of consumption") the weighted mean of these decile-specific
# values is used — computed at output time rather than hardcoded.
#
# CAVEAT: the constant-elasticity form is applied out to +61 % for gas
# (Cornwall Insight Jan-Mar 2027 scenario), well outside the ±10-20 % band over which
# the underlying elasticity studies are validated. Treat the extreme-
# shock scenarios as illustrative rather than predictive.
ELASTICITY_BY_DECILE = {d: -0.64 + (d - 1) * (-0.11 - -0.64) / 9 for d in range(1, 11)}

# Policy response parameters (applied to severe shock)
# The scenario the fixed-amount policy tables are scored against.
POLICY_SCENARIO = "Jan-Mar 2027 (Cornwall Insight)"
FLAT_TRANSFER = 400
CT_REBATE = 300

# Ofgem Q2 2026 unit rates (for kWh ↔ £ threshold conversions)
ELEC_RATE = TARIFFS["apr_jun_2026"]["elec"][0] / 100  # £/kWh
GAS_RATE = TARIFFS["apr_jun_2026"]["gas"][0] / 100  # £/kWh

# NEG electricity threshold per Bangham (2026) Substack proposal: matches
# Austria and the Netherlands' 2022 "first N kWh at the old price" relief
# schemes. 2,900 kWh is close to but not identical to the Ofgem TDCV for
# electricity (≈ 2,700 kWh for the medium-consumption band).
NEG_ELEC_KWH = 2_900
NEG_ELEC_SPEND = NEG_ELEC_KWH * ELEC_RATE

# ── Data ────────────────────────────────────────────────────────────────
#
# Microcosm UK 2024-25, run through policyengine.py's managed surface with
# allow_unmanaged=True: policyengine 6.2.4 certifies only
# enhanced_frs_2024_25 and populace_uk_2023 for the UK, not this build.
# The file is pinned by repository revision and content hash instead.
DATASET_REPO = "policyengine/populace-uk-private"
DATASET_FILE = "microcosm_uk_2024_25.h5"
# Release tag microcosm-uk-2024-25-national-20261002T230158Z-5c6b3f68,
# published 4 Oct 2026 as the latest national line (non-default release).
DATASET_RELEASE = "microcosm-uk-2024-25-national-20261002T230158Z-5c6b3f68"
DATASET_REVISION = "f9d1922cddab6b54a0dd37794a9bac74e3780c88"
DATASET_SHA256 = "aa31bdf67c977927ea2b325567d1cf7a79d94381239bc79918a0a0fc9c9588af"
