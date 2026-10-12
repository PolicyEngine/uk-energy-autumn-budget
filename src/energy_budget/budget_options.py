"""Autumn Budget 2026 options, scored in PolicyEngine against a
forecast-price baseline.

Baseline (current law at forecast prices), per financial year:

* **2026-27** — Ofgem caps for April-December 2026 and Cornwall Insight's
  January-March 2027 forecast, equal-weighted (the "2026-27 average"
  scenario). Electricity is VAT-free from October (SI 2026/987).
* **2027-28** — supplier forecasts (the average of EDF, British Gas and
  E.ON Next: £2,061 for April-June 2027, £1,876 for July-September 2027,
  post-July-2026 TDCVs). No forecaster publishes October 2027 onward, so
  the July level is held for the rest of the year. The electricity VAT
  cut has ended, so electricity carries 5% VAT again. Forecasts give no
  fuel split: each quarter scales Cornwall Insight's January 2027 unit
  rates (electricity with VAT restored) by one factor that hits the
  forecast total.

Each option is a PolicyEngine reform against that baseline, except the
VAT extension, which PolicyEngine UK does not model for domestic
electricity (policyengine-uk#2166) and is costed directly from each
household's electricity bill.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from policyengine_uk.utils.scenario import Scenario

from .baseline import _build_simulation, dataset_path, weighted_mean
from .config import (
    CURRENT_CAP,
    PRICE_REBASE,
    PRICE_SCENARIOS,
    TARIFFS,
    TDCV_ELEC_KWH,
    TDCV_GAS_KWH,
    fuel_bill,
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


def _typical_elec_bill(q):
    """Typical electricity bill (£/yr, post-July TDCVs) for a 2027-28 quarter."""
    unit, sc = _quarter_rates_2027_28(q["target"], q["elec_vat_in_target"])["elec"]
    return (unit * NEW_TDCV["elec"] + sc * 365) / 100


def _bill(rates, fuel):
    unit, sc = rates[fuel]
    kwh = TDCV_ELEC_KWH if fuel == "elec" else TDCV_GAS_KWH
    return (unit * kwh + sc * 365) / 100


def _year_2027_28():
    quarters = [
        _quarter_rates_2027_28(q["target"], q["elec_vat_in_target"])
        for q in FORECAST_2027_28
    ]
    out = {}
    for fuel in ("elec", "gas"):
        base = fuel_bill("apr_jun_2026", fuel)
        out[fuel] = np.mean([_bill(q, fuel) for q in quarters]) / base - 1
    old_basis = sum(np.mean([_bill(q, f) for q in quarters]) for f in ("elec", "gas"))
    return {"elec_pct": out["elec"], "gas_pct": out["gas"], "new_cap": round(old_basis)}


YEARS = {
    2026: {
        "label": "2026-27",
        **{
            k: PRICE_SCENARIOS["2026-27 average"][k]
            for k in ("elec_pct", "gas_pct", "new_cap")
        },
        "elec_vat_in_baseline": False,  # VAT-free Oct 2026 - Mar 2027
    },
    2027: {"label": "2027-28", **_year_2027_28(), "elec_vat_in_baseline": True},
}


def _policies(year):
    period = f"{year}-01-01.{year}-12-31"
    from energy_budget.reforms.targeted_energy_discount.presets import PRESETS
    from energy_budget.reforms.targeted_energy_discount.reform import scenario

    tp = "gov.contrib.targeted_energy_discount"
    return {
        "rf_targeted_discount": {
            "label": "Resolution Foundation targeted discount: £175 if highest income < £24k or on means-tested benefits",
            "params": {},
            "scenario": scenario(PRESETS["rf_flat"]),
        },
        "whd_top_up": {
            # Reported Treasury plan: £150 to £250, taxpayer-funded, about
            # £600m for 6m households (FT, 11 Oct 2026; Guardian, 6 Oct 2026).
            "label": "Warm Home Discount top-up: extra £100 to households on means-tested benefits, paid from taxation",
            "params": {},
            "scenario": scenario(
                {
                    **PRESETS["passport_only"],
                    f"{tp}.amount[0].amount": WHD_TOP_UP,
                    f"{tp}.amount[1].amount": WHD_TOP_UP,
                }
            ),
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
        "cap_freeze": {
            "label": f"Energy Price Guarantee holds bills at £{CURRENT_CAP:,}, the April–June 2026 cap",
            # policyengine-uk switches the guarantee off from April 2024, when
            # the 2022-24 scheme ended, so the reform switches it back on.
            "params": {
                "gov.ofgem.energy_price_guarantee": {period: CURRENT_CAP},
                "gov.ofgem.energy_price_guarantee_in_effect": {period: True},
            },
        },
    }


def _arr(sim, var, year, **kw):
    s = sim.calculate(var, year, **kw)
    return np.asarray(s.values if hasattr(s, "values") else s)


def _sim(year, elec, gas, cap, params=None, extra_scenario=None):
    period = f"{year}-01-01.{year}-12-31"
    reform = {"gov.ofgem.energy_price_cap": {period: cap}, **(params or {})}
    if extra_scenario is not None:
        import policyengine as pe

        sim = pe.uk.managed_microsimulation(
            dataset=dataset_path(),
            allow_unmanaged=True,
            scenario=Scenario.from_reform(reform) + extra_scenario,
        )
    else:
        sim = _build_simulation(reform)
    sim.set_input("electricity_consumption", year, elec)
    sim.set_input("gas_consumption", year, gas)
    sim.set_input("domestic_energy_consumption", year, elec + gas)
    return sim


def _poverty(sim, year):
    age = sim.calculate("age", year, map_to="person")
    out = {}
    for m in ("bhc", "ahc"):
        pov = sim.calculate(f"in_poverty_{m}", year, map_to="person")
        out[m] = round(float(pov.mean()) * 100, 2)
        out[f"child_{m}"] = round(float(pov[age < 18].mean()) * 100, 2)
    return out


def run_budget_options(data):
    """Score every option against each year's forecast baseline (UK)."""
    elec0, gas0 = data["elec"], data["gas"]
    results = {}
    for year, y in YEARS.items():
        elec = elec0 * (1 + y["elec_pct"])
        gas = gas0 * (1 + y["gas_pct"])
        hit = elec + gas - elec0 - gas0

        base = _sim(year, elec, gas, y["new_cap"])
        w = _arr(base, "household_weight", year, unweighted=True)
        base_net = _arr(base, "household_net_income", year)
        decile = _arr(base, "household_income_decile", year)
        hh_type = data["hh_type"]
        types = [t for t in sorted(set(hh_type)) if t != "OTHER"]

        def by_type(values, w=w, hh_type=hh_type, types=types):
            return {t: round(weighted_mean(values, w, hh_type == t)) for t in types}

        region = pd.Series(_arr(base, "region", year)).astype(str)
        gb = (region != "NORTHERN_IRELAND").to_numpy()
        region_arr = region.to_numpy()
        regions = [r for r in sorted(set(region_arr)) if r not in ("", "UNKNOWN")]

        def by_region(values, w=w, region_arr=region_arr, regions=regions):
            return {
                r: round(weighted_mean(values, w, region_arr == r)) for r in regions
            }

        def summarise(
            label, support, poverty=None, note=None, w=w, hit=hit, decile=decile
        ):
            return {
                "label": label,
                "cost_bn": round(float(np.sum(support * w)) / 1e9, 2),
                "avg_per_household": round(weighted_mean(support, w)),
                "share_receiving_pct": round(
                    float(np.sum((support > 0) * w) / np.sum(w)) * 100, 1
                ),
                "share_of_shock_offset_pct": round(
                    float(np.sum(np.minimum(support, hit) * w) / np.sum(hit * w)) * 100,
                    1,
                ),
                "deciles": [
                    round(weighted_mean(support, w, decile == d)) for d in range(1, 11)
                ],
                "by_hh_type": by_type(support),
                "by_region": by_region(support),
                "poverty": poverty,
                "note": note,
            }

        rows = {}
        for key, p in _policies(year).items():
            ref = _sim(
                year, elec, gas, y["new_cap"], p.get("params"), p.get("scenario")
            )
            support = _arr(ref, "household_net_income", year) - base_net
            rows[key] = summarise(p["label"], support, _poverty(ref, year))

        if y["elec_vat_in_baseline"]:
            # Zero-rate domestic electricity for the year (GB only, as the
            # 2026-27 cut). Not a PolicyEngine reform: PE-UK has no domestic
            # electricity VAT parameter (policyengine-uk#2166).
            support = np.where(gb, elec * VAT / (1 + VAT), 0.0)
            rows["extend_vat_cut"] = summarise(
                "Extend the 0% VAT on domestic electricity through 2027-28 (GB)",
                support,
                note="Price cut, costed from bills; not in HBAI income, so no poverty effect.",
            )
            typical_elec = np.mean([_typical_elec_bill(q) for q in FORECAST_2027_28])
            levy_share = LEVY_SAVING_TYPICAL / typical_elec
            support = np.where(gb, elec * levy_share, 0.0)
            rows["remove_levies"] = summarise(
                f"Move remaining levies to taxation: £{LEVY_SAVING_TYPICAL} off a typical bill "
                f"({levy_share:.1%} of each electricity bill, GB)",
                support,
                note="Price cut, costed from bills; not in HBAI income, so no poverty effect.",
            )

        results[y["label"]] = {
            "baseline": {
                "elec_price_vs_apr_jun_2026_pct": round(y["elec_pct"] * 100, 1),
                "gas_price_vs_apr_jun_2026_pct": round(y["gas_pct"] * 100, 1),
                "typical_bill_old_tdcv": y["new_cap"],
                # Benchmark against ONS Consumer Trends (calendar 2025 prices).
                "total_bill_2025_prices_bn": round(
                    float(
                        np.sum(
                            (elec0 / PRICE_REBASE["elec"] + gas0 / PRICE_REBASE["gas"])
                            * w
                        )
                    )
                    / 1e9,
                    1,
                ),
                "households_m": round(float(np.sum(w)) / 1e6, 2),
                "mean_bill": round(weighted_mean(elec + gas, w)),
                "total_bill_bn": round(float(np.sum((elec + gas) * w)) / 1e9, 2),
                "bill_by_decile": [
                    round(weighted_mean(elec + gas, w, decile == d))
                    for d in range(1, 11)
                ],
                "bill_by_hh_type": by_type(elec + gas),
                "bill_by_region": by_region(elec + gas),
                "mean_extra_cost": round(weighted_mean(hit, w)),
                "total_extra_cost_bn": round(float(np.sum(hit * w)) / 1e9, 2),
                "extra_cost_by_hh_type": by_type(hit),
                "income_by_decile": [
                    round(weighted_mean(base_net, w, decile == d)) for d in range(1, 11)
                ],
                "extra_cost_by_decile": [
                    round(weighted_mean(hit, w, decile == d)) for d in range(1, 11)
                ],
                "epg_subsidy_bn": round(
                    float(np.sum(_arr(base, "epg_subsidy", year) * w)) / 1e9, 2
                ),
                "poverty": _poverty(base, year),
            },
            "options": rows,
        }
    return results
