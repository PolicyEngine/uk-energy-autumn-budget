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
# The zero rate covers supplies "in England, Wales or Scotland" made from
# 1 Oct 2026 to 31 Mar 2027; Northern Ireland keeps the reduced rate (The
# Value Added Tax (Supplies of Domestic Electricity) Order 2026, SI 2026/987,
# art. 1(2), new Group 24 of Sch. 8 and art. 4). Northern Ireland households,
# costed on these GB rates as a proxy, therefore have 5% VAT put back on
# electricity in those two quarters (``NI_VAT_RESTORED`` in budget_options).
#   https://www.legislation.gov.uk/uksi/2026/987/made
# Sources:
#   Apr-Jun 2026, Jul-Sep 2026, Oct-Dec 2026: Ofgem, "Energy price cap unit
#     rates and standing charges"
#     https://www.ofgem.gov.uk/your-energy-supply/your-energy-bill/energy-price-cap-unit-rates-and-standing-charges
#     https://www.ofgem.gov.uk/press-release/energy-price-cap-will-rise-4-october-2026
#   Jan-Mar 2027: Cornwall Insight forecast, 30 Sep 2026 (close of 28 Sep),
#     Figure 2 (£1,999.28 on the new TDCVs: £959.44 elec + £1,039.84 gas)
#     https://www.cornwall-insight.com/predictions-and-insights-into-the-default-tariff-cap/
TARIFFS = {
    # Calendar 2025, used only for the KWH_BASIS="ofgem_cy2025_national" sensitivity.
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


CY2025_PERIODS = ["jan_mar_2025", "apr_jun_2025", "jul_sep_2025", "oct_dec_2025"]

# Financial-year quarters, in order: Apr-Jun, Jul-Sep, Oct-Dec, Jan-Mar.
FY_2026_27_PERIODS = [
    "apr_jun_2026",
    "jul_sep_2026",
    "oct_dec_2026",
    "jan_mar_2027_cornwall",
]

# ── Seasonal consumption profile ────────────────────────────────────────
#
# Central estimate: Ofgem's published winter shares of annual consumption,
# 75% of gas and 57% of electricity in October-March (Ofgem, "Appendix 4 -
# Wholesale costs", November 2018, physical page 6):
#   https://www.ofgem.gov.uk/sites/default/files/docs/2018/11/appendix_4_-_wholesale_costs.pdf#page=6
# Each half-year's share is split equally between its two quarters. Standing
# charges are paid per day, so each quarter carries a quarter of the year's
# days (365/4, not the calendar count, so that the published illustrations
# reproduce to the penny). The equal-weight profile (25% of use in every
# quarter) is reported as a sensitivity.
WINTER_SHARE = {"elec": 0.57, "gas": 0.75}
CONSUMPTION_PROFILE = "seasonal"  # or "equal"


def quarter_shares(fuel, profile=CONSUMPTION_PROFILE):
    """Share of a fuel's annual kWh used in each financial-year quarter."""
    if profile == "equal":
        return (0.25, 0.25, 0.25, 0.25)
    if profile != "seasonal":
        raise ValueError(f"Unknown consumption profile {profile!r}")
    winter = WINTER_SHARE[fuel]
    return ((1 - winter) / 2, (1 - winter) / 2, winter / 2, winter / 2)


# ── Dataset price basis ─────────────────────────────────────────────────
#
# Microcosm UK builds each household's electricity and gas spending as
# annual kWh (DESNZ Energy Trends domestic volumes for the four FY2024-25
# quarters, raked to NEED margins) priced at DESNZ Quarterly Energy Prices
# (QEP) FY2024-25 regional average unit costs plus the regional fixed cost,
# including VAT, all payment methods (stage ``price_domestic_energy`` in the
# build record of release microcosm-uk-2024-25-national-20261002T230158Z-
# 5c6b3f68, policyengine/populace-uk-private@f9d1922c, files
# staged/uk-frs-calibration-attempt-20261002T230158Z-5c6b3f68/build_record.json
# and releases/microcosm-uk-2024-25-national/spine_gates.json). Calibration
# then reweights households so weighted spending matches ONS Consumer
# Trends CY2025 (COICOP 04.5.1 / 04.5.2); it changes weights, not each
# household's spend. So each household's spend is on the QEP FY2024-25
# regional basis: in every GB region the lowest electricity spend equals
# that region's QEP fixed cost. See PolicyEngine/microcosm#1113.
#
# Each household's annual kWh is therefore recovered exactly as
#   kWh = max(0, spend - fixed cost) / unit rate
# and every scenario is costed from those kWh. Households with zero spend on
# a fuel have no connection for it and pay no standing charge. A connected
# household whose spend is below the fixed cost is kept as connected with
# zero kWh (it pays the standing charge only); on the QEP basis this binds
# only through floating-point rounding.
#
# KWH_BASIS switches the reference tariff:
#   "qep_fy2024_25_regional" (default; what the build used), or
#   "ofgem_cy2025_national": the four CY2025 Ofgem cap quarters (GB average,
#     direct debit), unit rates weighted by the seasonal profile. Kept as a
#     sensitivity; it was this repository's original (incorrect) assumption.
KWH_BASIS = "qep_fy2024_25_regional"

# QEP FY2024-25 regional prices, as used by the build: unit rate (p/kWh) and
# fixed cost (£/yr), VAT included. FRS regions map to QEP regions as in the
# build (Scotland -> south_scotland, Wales -> south_wales, East of England ->
# eastern). Northern Ireland: QEP publishes no electricity fixed cost (0),
# and gas is priced at the UK average.
QEP_FY2024_25 = {
    "EAST_MIDLANDS": {"elec": (23.975425353649914, 206.19892348861137), "gas": (6.121185915305579, 114.63475437474918)},
    "EAST_OF_ENGLAND": {"elec": (25.433401818323404, 184.75570497558127), "gas": (6.189902929736283, 114.66524644556283)},
    "LONDON": {"elec": (25.695029958424957, 153.84198551021262), "gas": (6.319403551432788, 118.04131810499113)},
    "NORTHERN_IRELAND": {"elec": (30.69783821469067, 0.0), "gas": (6.2310725604795225, 113.12698361893374)},
    "NORTH_EAST": {"elec": (23.387452050534694, 259.99949391627337), "gas": (6.201645024344041, 115.68085068413619)},
    "NORTH_WEST": {"elec": (24.958336465763903, 189.69303157506977), "gas": (6.143483988396162, 115.54964406237428)},
    "SCOTLAND": {"elec": (24.07873330442262, 232.97332300802108), "gas": (6.172288897645929, 115.54058124854232)},
    "SOUTH_EAST": {"elec": (25.362880086372137, 205.8995779598325), "gas": (6.167387887020088, 113.51623692620075)},
    "SOUTH_WEST": {"elec": (24.246541563525536, 242.83158453310014), "gas": (6.407245693067759, 110.40783503988152)},
    "WALES": {"elec": (24.436750400826238, 228.7377582586279), "gas": (6.317265828101576, 113.12600630737884)},
    "WEST_MIDLANDS": {"elec": (24.04622652441871, 229.98795369188866), "gas": (6.12714395248696, 113.02514947990299)},
    "YORKSHIRE": {"elec": (23.59230294674964, 246.22442968964552), "gas": (6.109505359504377, 113.10595798118004)},
}  # fmt: skip
# UK average, for any household whose region is missing.
QEP_FY2024_25_UK = {"elec": (24.809458249743663, 209.38599214492953), "gas": (6.2310725604795225, 113.12698361893374)}  # fmt: skip


def _ofgem_cy2025_reference():
    """CY2025 Ofgem cap reference tariff: (unit p/kWh, fixed £/yr) per fuel.

    CY2025 runs Jan-Mar (winter), Apr-Jun, Jul-Sep, Oct-Dec (winter); unit
    rates are weighted by the seasonal profile, standing charges by time.
    """
    out = {}
    for fuel in ("elec", "gas"):
        s = quarter_shares(fuel)  # Apr, Jul, Oct, Jan
        shares = (s[3], s[0], s[1], s[2])  # CY order: Jan, Apr, Jul, Oct
        unit = sum(w * TARIFFS[p][fuel][0] for w, p in zip(shares, CY2025_PERIODS))
        standing = sum(TARIFFS[p][fuel][1] for p in CY2025_PERIODS) / 4
        out[fuel] = (unit, standing * 365 / 100)
    return out


OFGEM_CY2025_REFERENCE = _ofgem_cy2025_reference()

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
# allow_unmanaged=True: the pinned policyengine release certifies only
# enhanced_frs_2024_25 and populace_uk_2023 for the UK, not this build.
# The file is pinned by repository revision and content hash instead.
DATASET_REPO = "policyengine/populace-uk-private"
DATASET_FILE = "microcosm_uk_2024_25.h5"
# Release tag microcosm-uk-2024-25-national-20261002T230158Z-5c6b3f68,
# published 4 Oct 2026 as the latest national line (non-default release).
DATASET_RELEASE = "microcosm-uk-2024-25-national-20261002T230158Z-5c6b3f68"
DATASET_REVISION = "f9d1922cddab6b54a0dd37794a9bac74e3780c88"
DATASET_SHA256 = "aa31bdf67c977927ea2b325567d1cf7a79d94381239bc79918a0a0fc9c9588af"
