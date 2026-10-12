"""Autumn Budget 2026 options, scored against a forecast-price baseline.

Bills. Each household's annual electricity and gas kWh are recovered from
its Microcosm spend at the dataset's reference tariff (``KWH_BASIS``: DESNZ
QEP FY2024-25 regional unit cost + fixed cost) and re-costed quarter by
quarter: kWh x unit rate on that quarter's share of annual use (Ofgem's
seasonal profile, 75% of gas and 57% of electricity in October-March) plus
the quarter's standing charge. Households with no spend on a fuel pay no
standing charge for it. The equal-quarter profile is reported as a
sensitivity, as is the CY2025 Ofgem-cap reference tariff.

Baseline (current law at forecast prices), per financial year:

* **2026-27**: Ofgem caps for April-December 2026 and Cornwall Insight's
  January-March 2027 forecast. Electricity is VAT-free from October in
  England, Wales and Scotland (SI 2026/987); Northern Ireland, costed on
  GB rates as a proxy, keeps 5% VAT.
* **2027-28**: the average of supplier forecasts (EDF, British Gas,
  E.ON Next) for April-June and July-September 2027; OVO's October-December
  2027 forecast, quoted at 0% electricity VAT, with 5% VAT restored; and
  January-March 2028 held at the October-December level. Forecasts give no
  fuel split: each quarter scales Cornwall Insight's January 2027 unit rates
  and standing charges by one factor that hits the forecast total.

Every household is modelled on capped variable tariffs; tariff type,
payment method and contract expiry are not modelled.

Options. The targeted discount (RF, simplified), Warm Home Discount
top-up, Cost of Living Payment and £400 payment are PolicyEngine reforms
against that baseline. The cap freeze, the VAT extension and levy removal
are price cuts costed analytically from each household's bill, outside
HBAI income: PolicyEngine UK has no domestic-electricity VAT parameter
(policyengine-uk#2166), and its Energy Price Guarantee scales the whole
combined bill rather than holding each fuel's unit rate and standing charge.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .baseline import _build_simulation, dataset_path, weighted_mean
from .bills import FUELS, fuel_bill_for_profile, household_kwh, typical_bill
from .config import (
    CONSUMPTION_PROFILE,
    CURRENT_CAP,
    FY_2026_27_PERIODS,
    KWH_BASIS,
    TARIFFS,
    TDCV_ELEC_KWH,
    TDCV_GAS_KWH,
)

VAT = 0.05
WHD_TOP_UP = 100
# Moving the remaining policy levies (the last 25% of the Renewables
# Obligation and Feed-in Tariffs) to taxation: "as much as £120" off a
# typical bill, costing "as much as £3.2bn" (Guardian, 6 Oct 2026; FT,
# 11 Oct 2026). Levies sit on electricity, so each household's electricity
# bill falls by the share that takes £120 off the typical electricity bill.
LEVY_SAVING_TYPICAL = 120
NEW_TDCV = {"elec": 2_500, "gas": 9_500}

# 2027-28 price path, post-July-2026 TDCVs, typical dual-fuel direct debit.
# Forecasts give totals only, so each quarter scales Cornwall Insight's
# January 2027 unit rates to the total. ``elec_vat_in_target`` says whether
# the forecast already carries 5% VAT on electricity (current law from April
# 2027): OVO states its figures keep the 0% rate in force since October 2026,
# so VAT is added back after scaling; the supplier average is taken to
# include it.
MSE = "https://www.moneysavingexpert.com/utilities/energy-price-cap-prediction/"
OVO = "https://www.ovoenergy.com/price-cap"
FORECAST_2027_28 = [
    {
        "key": "apr_jun_2027",
        "period": "Apr–Jun 2027",
        "target": 2_074,
        "elec_vat_in_target": True,
        "kind": "Forecast",
        "source": "Supplier average (EDF, British Gas, E.ON Next), 6–7 Oct 2026",
        "link": MSE,
    },
    {
        "key": "jul_sep_2027",
        "period": "Jul–Sep 2027",
        "target": 1_912,
        "elec_vat_in_target": True,
        "kind": "Forecast",
        "source": "Supplier average (EDF, E.ON Next), 6–7 Oct 2026",
        "link": MSE,
    },
    {
        "key": "oct_dec_2027",
        "period": "Oct–Dec 2027",
        "target": 1_846,
        "elec_vat_in_target": False,
        "kind": "Forecast",
        "source": "OVO, 7 Oct 2026",
        "link": OVO,
    },
    {
        # No published forecast; held at OVO's Oct-Dec 2027 level. The
        # Winter-27 gas forward prices Q4-27 and Q1-28 together, with no
        # Q1 premium (Catalyst, 22 Sep 2026 settlement).
        "key": "jan_mar_2028",
        "period": "Jan–Mar 2028",
        "target": 1_846,
        "elec_vat_in_target": False,
        "kind": "Assumed",
        "source": "Held at OVO's Oct–Dec 2027 forecast (no published forecast)",
        "link": OVO,
    },
]


def _quarter_rates_2027_28(target, elec_vat_in_target=True):
    """Cornwall's Jan 2027 rates scaled to a forecast total on the post-July
    TDCVs, with 5% VAT on electricity in the result."""
    e_unit, e_sc = TARIFFS["jan_mar_2027_cornwall"]["elec"]
    g_unit, g_sc = TARIFFS["jan_mar_2027_cornwall"]["gas"]
    if elec_vat_in_target:
        e_unit, e_sc = e_unit * (1 + VAT), e_sc * (1 + VAT)
    total = (
        e_unit * NEW_TDCV["elec"] + e_sc * 365 + g_unit * NEW_TDCV["gas"] + g_sc * 365
    ) / 100
    g = target / total
    e_unit, e_sc = e_unit * g, e_sc * g
    if not elec_vat_in_target:
        e_unit, e_sc = e_unit * (1 + VAT), e_sc * (1 + VAT)
    return {"elec": (e_unit, e_sc), "gas": (g_unit * g, g_sc * g)}


# Northern Ireland keeps the reduced VAT rate on electricity while GB is
# zero-rated (SI 2026/987, art. 4), so NI's proxy GB rates get 5% back in
# these quarters.
NI_VAT_RESTORED = ("oct_dec_2026", "jan_mar_2027_cornwall")

TARIFF_NOTE = (
    "Every household is modelled on the capped variable tariff (Ofgem GB "
    "direct-debit averages). Around 35% of households are on fixed tariffs "
    "and will not see the October 2026 cap rise (Ofgem); tariff type, payment "
    "method and contract expiry are not modelled, so no correction for fixed "
    "tariffs is applied. Northern Ireland is costed on GB prices as a proxy."
)
TARIFF_NOTE_LINK = (
    "https://www.ofgem.gov.uk/press-release/energy-price-cap-will-rise-4-october-2026"
)

WHD_OFFICIAL_HOUSEHOLDS_M = 6.0
WHD_LINKS = [
    "https://www.gov.uk/the-warm-home-discount-scheme/if-you-live-in-england-and-wales",
    "https://www.gov.uk/the-warm-home-discount-scheme/if-you-live-in-scotland",
]
RF_LINK = "https://www.resolutionfoundation.org/publications/billing-me-softly/"
RF_ASSUMPTIONS = [
    (
        "A flat £175 per eligible household, not RF's discount on gas and electricity "
        "unit rates (£175 is RF's average per eligible household)."
    ),
    "The income test uses annual income, not the previous three months' income.",
    (
        "Full take-up: every eligible household receives it, including those that "
        "would have to self-declare."
    ),
]
NOT_HBAI = "Price cut, costed from bills; not in HBAI income, so no poverty effect."


def year_quarters(year, ni=False):
    """Four quarterly (unit p/kWh, standing p/day) tariffs per fuel for a FY."""
    if year == 2026:
        out = {f: [TARIFFS[p][f] for p in FY_2026_27_PERIODS] for f in FUELS}
        if ni:
            out["elec"] = [
                (u * (1 + VAT), sc * (1 + VAT)) if p in NI_VAT_RESTORED else (u, sc)
                for p, (u, sc) in zip(FY_2026_27_PERIODS, out["elec"])
            ]
        return out
    if year == 2027:
        rates = [
            _quarter_rates_2027_28(q["target"], q["elec_vat_in_target"])
            for q in FORECAST_2027_28
        ]
        return {f: [r[f] for r in rates] for f in FUELS}
    raise ValueError(f"No price path for {year}")


HELD_QUARTERS = {f: [TARIFFS["apr_jun_2026"][f]] * 4 for f in FUELS}


def typical(year, profile=CONSUMPTION_PROFILE):
    """Typical bill (old TDCVs) and each fuel's change vs April-June 2026."""
    q = year_quarters(year)
    out = {"bill": typical_bill(q, profile, TDCV_ELEC_KWH, TDCV_GAS_KWH)}
    for f, kwh in (("elec", TDCV_ELEC_KWH), ("gas", TDCV_GAS_KWH)):
        new = fuel_bill_for_profile(kwh, True, q[f], f, profile)
        old = fuel_bill_for_profile(kwh, True, HELD_QUARTERS[f], f, profile)
        out[f"{f}_pct"] = float(new / old - 1)
    return out


def household_bills(year, kwh, connected, is_ni, profile=CONSUMPTION_PROFILE):
    """Forecast bills per fuel. ``kwh``/``connected`` map fuel -> arrays."""
    gb_q, ni_q = year_quarters(year), year_quarters(year, ni=True)
    out = {}
    for f in FUELS:
        gb = fuel_bill_for_profile(kwh[f], connected[f], gb_q[f], f, profile)
        ni = fuel_bill_for_profile(kwh[f], connected[f], ni_q[f], f, profile)
        out[f] = np.where(is_ni, ni, gb)
    return out


def held_bills(kwh, connected):
    """Bills at April-June 2026 tariffs (the cap-freeze level)."""
    return {
        f: fuel_bill_for_profile(kwh[f], connected[f], HELD_QUARTERS[f], f, "equal")
        for f in FUELS
    }


def cap_freeze_support(forecast, held):
    """Subsidy holding unit rates and standing charges at April-June 2026."""
    return np.maximum(
        forecast["elec"] + forecast["gas"] - held["elec"] - held["gas"], 0.0
    )


def levy_share(profile=CONSUMPTION_PROFILE):
    """Share of the typical 2027-28 electricity bill that £120 of levies is."""
    typical_elec = fuel_bill_for_profile(
        NEW_TDCV["elec"], True, year_quarters(2027)["elec"], "elec", profile
    )
    return LEVY_SAVING_TYPICAL / float(typical_elec)


def analytic_supports(year, forecast, held, gb, profile=CONSUMPTION_PROFILE):
    """Supports for the options costed directly from bills."""
    out = {"cap_freeze": cap_freeze_support(forecast, held)}
    if year == 2027:
        out["extend_vat_cut"] = np.where(gb, forecast["elec"] * VAT / (1 + VAT), 0.0)
        out["remove_levies"] = np.where(gb, forecast["elec"] * levy_share(profile), 0.0)
    return out


YEARS = {
    2026: {"label": "2026-27"},
    2027: {"label": "2027-28"},
}


def _policies(year):
    period = f"{year}-01-01.{year}-12-31"
    from energy_budget.reforms.targeted_energy_discount.presets import PRESETS
    from energy_budget.reforms.targeted_energy_discount.reform import scenario

    tp = "gov.contrib.targeted_energy_discount"
    return {
        "rf_targeted_discount": {
            "label": (
                "Targeted discount (RF, simplified): a flat £175 to GB households on "
                "means-tested benefits or whose highest individual income is under £24,000"
            ),
            "scenario": scenario(PRESETS["rf_flat"]),
            "assumptions": RF_ASSUMPTIONS,
            "note": (
                "Simplified fixed-payment illustration of the Resolution Foundation's "
                "unit-rate discount. Counted as HBAI income by assumption, by analogy "
                "with DWP's treatment of the Warm Home Discount."
            ),
            "links": [RF_LINK],
        },
        "whd_top_up": {
            # Reported Treasury plan: £150 to £250, taxpayer-funded, about
            # £600m for 6m households (FT, 11 Oct 2026; Guardian, 6 Oct 2026).
            "label": (
                "Warm Home Discount top-up (means-tested-household proxy): an extra "
                f"£{WHD_TOP_UP} to GB households where anyone receives a listed "
                "means-tested benefit, paid from taxation"
            ),
            "scenario": scenario(
                {
                    **PRESETS["passport_only"],
                    f"{tp}.amount[0].amount": WHD_TOP_UP,
                    f"{tp}.amount[1].amount": WHD_TOP_UP,
                }
            ),
            "links": WHD_LINKS,
        },
        "cost_of_living_payment": {
            "label": "£300 Cost of Living Payment to households on means-tested benefits",
            "params": {
                "gov.treasury.cost_of_living_support.means_tested_households.amount": {
                    period: 300
                }
            },
        },
        "flat_400": {
            "label": "£400 to every household (2022 EBSS design)",
            "params": {
                "gov.treasury.energy_bills_rebate.energy_bills_credit": {period: 400}
            },
        },
    }


def _whd_note(recipients_m):
    return (
        "Proxy for Warm Home Discount recipients: every GB household where any member "
        "receives Universal Credit, Pension Credit, Housing Benefit, income-related ESA, "
        "income-based JSA or Income Support during the year. The actual scheme also "
        "requires the qualifying date, a participating supplier and the claimant or "
        "partner named on the electricity account (England and Wales), and has "
        "core/broader groups with application conditions in Scotland. Modelled "
        f"caseload {recipients_m:.1f}m households against about "
        f"{WHD_OFFICIAL_HOUSEHOLDS_M:.0f}m in official estimates."
    )


ANALYTIC_OPTIONS = {
    "cap_freeze": {
        "label": (
            "Cap freeze: electricity and gas unit rates and standing charges held at "
            f"April–June 2026 levels (£{CURRENT_CAP:,} typical bill)"
        ),
        "note": (
            "Price restoration, not a payment: each household's forecast bill minus its "
            "bill at April–June 2026 tariffs for the same kWh (seasonal profile), floored "
            "at zero. Outside HBAI income, so no poverty effect. UK-wide, with Northern "
            "Ireland on GB prices as a proxy."
        ),
    },
    "extend_vat_cut": {
        "label": "Extend the 0% VAT on domestic electricity through 2027-28 (GB)",
        "note": NOT_HBAI,
    },
    "remove_levies": {
        "label": (
            f"Move remaining levies to taxation: £{LEVY_SAVING_TYPICAL} off a typical "
            "electricity bill, as a share of each GB electricity bill"
        ),
        "note": NOT_HBAI,
    },
}

OPTION_ORDER = [
    "rf_targeted_discount",
    "whd_top_up",
    "cost_of_living_payment",
    "flat_400",
    "cap_freeze",
    "extend_vat_cut",
    "remove_levies",
]


def _arr(sim, var, year, **kw):
    s = sim.calculate(var, year, **kw)
    return np.asarray(s.values if hasattr(s, "values") else s)


def _sim(year, elec, gas, params=None, extra_scenario=None):
    if extra_scenario is not None:
        import policyengine as pe

        sim = pe.uk.managed_microsimulation(
            dataset=dataset_path(), allow_unmanaged=True, scenario=extra_scenario
        )
    else:
        sim = _build_simulation(params or None)
    sim.set_input("electricity_consumption", year, elec)
    sim.set_input("gas_consumption", year, gas)
    sim.set_input("domestic_energy_consumption", year, elec + gas)
    return sim


def _poverty(sim, year):
    """Person-weighted poverty rates (%).

    The main keys are relative poverty (below 60% of the median, the DWP HBAI
    headline measure, ``in_relative_poverty_*``). ``absolute_*`` keys are
    PolicyEngine UK's ``in_poverty_*``, which is absolute poverty against a
    fixed FYE 2025 line.
    """
    age = sim.calculate("age", year, map_to="person")
    out = {}
    for m in ("bhc", "ahc"):
        for prefix, var in (
            ("", f"in_relative_poverty_{m}"),
            ("absolute_", f"in_poverty_{m}"),
        ):
            pov = sim.calculate(var, year, map_to="person")
            out[f"{prefix}{m}"] = round(float(pov.mean()) * 100, 2)
            out[f"{prefix}child_{m}"] = round(float(pov[age < 18].mean()) * 100, 2)
    return out


def _bn(values, w):
    return round(float(np.sum(values * w)) / 1e9, 2)


def _sensitivity(year, kwh, connected, is_ni, gb, w, profile):
    """Headline bills and analytic option costs under another assumption."""
    fc = household_bills(year, kwh, connected, is_ni, profile)
    held = held_bills(kwh, connected)
    hit = fc["elec"] + fc["gas"] - held["elec"] - held["gas"]
    return {
        "typical_bill_old_tdcv": round(typical(year, profile)["bill"], 2),
        "mean_bill": round(weighted_mean(fc["elec"] + fc["gas"], w)),
        "mean_extra_cost": round(weighted_mean(hit, w)),
        "total_extra_cost_bn": _bn(hit, w),
        "option_cost_bn": {
            k: _bn(v, w)
            for k, v in analytic_supports(year, fc, held, gb, profile).items()
        },
    }


def run_budget_options(data):
    """Score every option against each year's forecast baseline (UK)."""
    kwh = {"elec": data["elec_kwh"], "gas": data["gas_kwh"]}
    connected = {"elec": data["has_elec"], "gas": data["has_gas"]}
    held = {"elec": data["elec"], "gas": data["gas"]}
    region_all = pd.Series(data["region"]).astype(str).to_numpy()
    is_ni = region_all == "NORTHERN_IRELAND"
    gb = ~is_ni

    alt_basis = (
        "ofgem_cy2025_national"
        if KWH_BASIS == "qep_fy2024_25_regional"
        else "qep_fy2024_25_regional"
    )
    alt_kwh, alt_conn = {}, {}
    for f, spend in (("elec", data["elec_spend"]), ("gas", data["gas_spend"])):
        alt_kwh[f], alt_conn[f] = household_kwh(spend, region_all, f, alt_basis)
    alt_profile = "equal" if CONSUMPTION_PROFILE == "seasonal" else "seasonal"

    results = {}
    for year, y in YEARS.items():
        fc = household_bills(year, kwh, connected, is_ni)
        elec, gas = fc["elec"], fc["gas"]
        hit = elec + gas - held["elec"] - held["gas"]
        typ = typical(year)

        base = _sim(year, elec, gas)
        w = _arr(base, "household_weight", year, unweighted=True)
        base_net = _arr(base, "household_net_income", year)
        decile = _arr(base, "household_income_decile", year)
        hh_type = data["hh_type"]
        types = [t for t in sorted(set(hh_type)) if t != "OTHER"]

        def by_type(values, w=w, hh_type=hh_type, types=types):
            return {t: round(weighted_mean(values, w, hh_type == t)) for t in types}

        region_arr = pd.Series(_arr(base, "region", year)).astype(str).to_numpy()
        regions = [r for r in sorted(set(region_arr)) if r not in ("", "UNKNOWN")]

        def by_region(values, w=w, region_arr=region_arr, regions=regions):
            return {
                r: round(weighted_mean(values, w, region_arr == r)) for r in regions
            }

        def summarise(
            label,
            support,
            poverty=None,
            note=None,
            w=w,
            hit=hit,
            decile=decile,
            **extra,
        ):
            pos_hit = np.maximum(hit, 0)
            recipients_m = float(np.sum((support > 0) * w)) / 1e6
            return {
                "label": label,
                "cost_bn": _bn(support, w),
                "avg_per_household": round(weighted_mean(support, w)),
                "share_receiving_pct": round(
                    float(np.sum((support > 0) * w) / np.sum(w)) * 100, 1
                ),
                "recipients_m": round(recipients_m, 2),
                "share_of_shock_offset_pct": round(
                    float(
                        np.sum(np.minimum(support, pos_hit) * w) / np.sum(pos_hit * w)
                    )
                    * 100,
                    1,
                ),
                "deciles": [
                    round(weighted_mean(support, w, decile == d)) for d in range(1, 11)
                ],
                "by_hh_type": by_type(support),
                "by_region": by_region(support),
                "poverty": poverty,
                "note": note,
                **extra,
            }

        rows = {}
        for key, p in _policies(year).items():
            ref = _sim(year, elec, gas, p.get("params"), p.get("scenario"))
            support = _arr(ref, "household_net_income", year) - base_net
            rows[key] = summarise(
                p["label"],
                support,
                _poverty(ref, year),
                p.get("note"),
                assumptions=p.get("assumptions"),
                links=p.get("links"),
            )
        whd = rows["whd_top_up"]
        whd["note"] = _whd_note(whd["recipients_m"])

        for key, support in analytic_supports(year, fc, held, gb).items():
            meta = ANALYTIC_OPTIONS[key]
            rows[key] = summarise(meta["label"], support, note=meta["note"])
        rows = {k: rows[k] for k in OPTION_ORDER if k in rows}

        results[y["label"]] = {
            "baseline": {
                "consumption_profile": CONSUMPTION_PROFILE,
                "kwh_basis": KWH_BASIS,
                "elec_price_vs_apr_jun_2026_pct": round(typ["elec_pct"] * 100, 1),
                "gas_price_vs_apr_jun_2026_pct": round(typ["gas_pct"] * 100, 1),
                "typical_bill_old_tdcv": round(typ["bill"]),
                "typical_bill_old_tdcv_exact": round(typ["bill"], 2),
                # Dataset spend at its own (QEP FY2024-25) prices, and the
                # implied national volume, as diagnostics against ONS 2025
                # spending (£41.9bn) and DESNZ Energy Trends FY2024-25.
                "total_bill_dataset_prices_bn": _bn(
                    data["elec_spend"] + data["gas_spend"], w
                ),
                "implied_twh": {
                    "elec": round(float(np.sum(kwh["elec"] * w)) / 1e9, 1),
                    "gas": round(float(np.sum(kwh["gas"] * w)) / 1e9, 1),
                },
                # Connected households whose dataset spend equals the fixed
                # cost, so they carry zero kWh (under 0.5 kWh: spend is float32 in the
                # simulation) and only standing charges move.
                "connected_zero_kwh_pct": {
                    f: round(
                        float(np.sum(w * (connected[f] & (kwh[f] < 0.5))) / np.sum(w))
                        * 100,
                        1,
                    )
                    for f in FUELS
                },
                "households_m": round(float(np.sum(w)) / 1e6, 2),
                "mean_bill": round(weighted_mean(elec + gas, w)),
                "mean_bill_apr_jun_2026_prices": round(
                    weighted_mean(held["elec"] + held["gas"], w)
                ),
                "total_bill_bn": _bn(elec + gas, w),
                "bill_by_decile": [
                    round(weighted_mean(elec + gas, w, decile == d))
                    for d in range(1, 11)
                ],
                "bill_by_hh_type": by_type(elec + gas),
                "bill_by_region": by_region(elec + gas),
                "mean_extra_cost": round(weighted_mean(hit, w)),
                "total_extra_cost_bn": _bn(hit, w),
                "extra_cost_by_hh_type": by_type(hit),
                "income_by_decile": [
                    round(weighted_mean(base_net, w, decile == d)) for d in range(1, 11)
                ],
                "extra_cost_by_decile": [
                    round(weighted_mean(hit, w, decile == d)) for d in range(1, 11)
                ],
                "hh_type_share_pct": {
                    t: round(float(np.sum(w * (hh_type == t)) / np.sum(w)) * 100, 1)
                    for t in sorted(set(hh_type))
                },
                "poverty": _poverty(base, year),
                "note": TARIFF_NOTE,
                "note_link": TARIFF_NOTE_LINK,
                "sensitivities": {
                    f"profile_{alt_profile}": _sensitivity(
                        year, kwh, connected, is_ni, gb, w, alt_profile
                    ),
                    f"kwh_basis_{alt_basis}": _sensitivity(
                        year, alt_kwh, alt_conn, is_ni, gb, w, CONSUMPTION_PROFILE
                    ),
                },
            },
            "options": rows,
        }
    return results
