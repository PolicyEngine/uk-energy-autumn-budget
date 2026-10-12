"""Run the model and write the dashboard's data files.

energy-budget            # writes dashboard/data/*.json
"""

import json
from pathlib import Path

from .baseline import provenance, run_baseline
from .budget_options import FORECAST_2027_28, _quarter_rates_2027_28, run_budget_options
from .config import PRICE_REBASE, TARIFFS, fuel_bill

REGION_LABELS = {
    "NORTH_EAST": "North East",
    "NORTH_WEST": "North West",
    "YORKSHIRE": "Yorkshire and the Humber",
    "EAST_MIDLANDS": "East Midlands",
    "WEST_MIDLANDS": "West Midlands",
    "EAST_OF_ENGLAND": "East of England",
    "LONDON": "London",
    "SOUTH_EAST": "South East",
    "SOUTH_WEST": "South West",
    "WALES": "Wales",
    "SCOTLAND": "Scotland",
    "NORTHERN_IRELAND": "Northern Ireland",
}

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "src" / "data"


def _dump(obj, path):
    with open(path, "w") as f:
        json.dump(obj, f, indent=1)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    data = run_baseline()
    r = run_budget_options(data)
    r["provenance"] = provenance(data["sim"])
    _dump(r, OUT / "results.json")
    write_tables(r)


OFG = "https://www.ofgem.gov.uk/your-energy-supply/your-energy-bill/energy-price-cap-unit-rates-and-standing-charges"
CI = "https://www.cornwall-insight.com/press-releases/16-price-cap-rise-forecast-in-january/"
EON = "https://www.eonnext.com/electricity-and-gas/price-cap/predictions"


def bill(rates, f, kwh):
    u, s = rates[f]
    return (u * kwh + s * 365) / 100


def write_tables(r):
    base = {f: fuel_bill("apr_jun_2026", f) for f in ("elec", "gas")}

    rows = []

    def add(period, fy, kind, source, link, rates, published):
        e = bill(rates, "elec", 2700)
        g = bill(rates, "gas", 11500)
        rows.append(
            {
                "period": period,
                "fy": fy,
                "kind": kind,
                "source": source,
                "link": link,
                "published_cap": published,
                "elec_unit_p": round(rates["elec"][0], 2),
                "elec_standing_p": round(rates["elec"][1], 2),
                "gas_unit_p": round(rates["gas"][0], 2),
                "gas_standing_p": round(rates["gas"][1], 2),
                "bill_1641_basis": round(e + g),
                # Typical bill on Ofgem's current (post-July 2026) consumption.
                "typical_bill": round(
                    bill(rates, "elec", 2500) + bill(rates, "gas", 9500)
                ),
                "elec_change_pct": round((e / base["elec"] - 1) * 100, 1),
                "gas_change_pct": round((g / base["gas"] - 1) * 100, 1),
            }
        )

    add(
        "Apr–Jun 2026",
        "2026-27",
        "Announced",
        "Ofgem cap",
        OFG,
        TARIFFS["apr_jun_2026"],
        1641,
    )
    add(
        "Jul–Sep 2026",
        "2026-27",
        "Announced",
        "Ofgem cap",
        OFG,
        TARIFFS["jul_sep_2026"],
        1663,
    )
    add(
        "Oct–Dec 2026",
        "2026-27",
        "Announced",
        "Ofgem cap (electricity VAT-free)",
        "https://www.ofgem.gov.uk/press-release/energy-price-cap-will-rise-4-october-2026",
        TARIFFS["oct_dec_2026"],
        1723,
    )
    add(
        "Jan–Mar 2027",
        "2026-27",
        "Forecast",
        "Cornwall Insight, 30 Sep 2026",
        CI,
        TARIFFS["jan_mar_2027_cornwall"],
        1999,
    )
    for q in FORECAST_2027_28:
        add(
            q["period"],
            "2027-28",
            q["kind"],
            q["source"],
            q["link"],
            _quarter_rates_2027_28(q["target"], q["elec_vat_in_target"]),
            q["target"] if q["kind"] == "Forecast" else None,
        )
    _dump(rows, OUT / "price_path.json")

    yrs = []
    regs = []
    opts = []
    dec = []
    hh = []
    LABEL = {
        "rf_targeted_discount": "Targeted discount (RF)",
        "cost_of_living_payment": "£300 Cost of Living Payment",
        "whd_top_up": "Warm Home Discount +£150",
        "extend_vat_cut": "Extend electricity VAT cut",
        "flat_400": "£400 to every household",
        "cap_freeze": "Cap freeze at £1,641",
    }
    for fy, v in r.items():
        if fy == "provenance":
            continue
        b = v["baseline"]
        p = b["poverty"]
        yrs.append(
            {
                "fy": fy,
                "elec_change_pct": b["elec_price_vs_apr_jun_2026_pct"],
                "gas_change_pct": b["gas_price_vs_apr_jun_2026_pct"],
                "typical_bill_1641_basis": b["typical_bill_old_tdcv"],
                "mean_bill": b["mean_bill"],
                "total_bill_bn": b["total_bill_bn"],
                "total_bill_2025_prices_bn": b["total_bill_2025_prices_bn"],
                "households_m": b["households_m"],
                "mean_extra_cost": b["mean_extra_cost"],
                "total_extra_cost_bn": b["total_extra_cost_bn"],
                "epg_subsidy_bn": b["epg_subsidy_bn"],
                "poverty_bhc_pct": p["bhc"],
                "poverty_ahc_pct": p["ahc"],
                "child_poverty_ahc_pct": p["child_ahc"],
            }
        )
        for k, o in v["options"].items():
            q = o["poverty"]
            opts.append(
                {
                    "fy": fy,
                    "option_id": k,
                    "option": LABEL[k],
                    "design": o["label"],
                    "cost_bn": o["cost_bn"],
                    "avg_per_household": o["avg_per_household"],
                    "share_receiving_pct": o["share_receiving_pct"],
                    "share_of_shock_covered_pct": o["share_of_shock_offset_pct"],
                    "poverty_ahc_change_pp": None
                    if q is None
                    else round(q["ahc"] - p["ahc"], 2),
                    "child_poverty_ahc_change_pp": None
                    if q is None
                    else round(q["child_ahc"] - p["child_ahc"], 2),
                    "poverty_bhc_change_pp": None
                    if q is None
                    else round(q["bhc"] - p["bhc"], 2),
                    "decile_1_gain": o["deciles"][0],
                    "decile_10_gain": o["deciles"][9],
                }
            )
        for d in range(10):
            row = {
                "fy": fy,
                "decile": d + 1,
                "extra_cost": b["extra_cost_by_decile"][d],
                "bill": b["bill_by_decile"][d],
                "net_income": b["income_by_decile"][d],
            }
            for k, o in v["options"].items():
                row[k] = o["deciles"][d]
            dec.append(row)
        for reg, val in b["bill_by_region"].items():
            row = {"fy": fy, "region": REGION_LABELS.get(reg, reg), "bill": val}
            for k, o in v["options"].items():
                row[k] = o["by_region"][reg]
            regs.append(row)
        for t, val in b["extra_cost_by_hh_type"].items():
            row = {
                "fy": fy,
                "hh_type": t.replace("_", " ").capitalize(),
                "extra_cost": val,
                "bill": b["bill_by_hh_type"][t],
            }
            for k, o in v["options"].items():
                row[k] = o["by_hh_type"][t]
            hh.append(row)
    notes = [
        {
            "id": "data",
            "topic": "Data and model",
            "detail": "PolicyEngine 6.2.4 (policyengine-uk 2.102.3) on Microcosm UK 2024-25, release microcosm-uk-2024-25-national-20261002T230158Z. The release is not yet in the certified bundle, so it is pinned by SHA-256.",
            "link": "https://github.com/PolicyEngine/policyengine.py",
        },
        {
            "id": "rebase",
            "topic": "Price basis",
            "detail": f"Microcosm energy spending is calibrated to ONS 2025 spending, so electricity is multiplied by {PRICE_REBASE['elec']:.3f} and gas by {PRICE_REBASE['gas']:.3f} to reach April–June 2026 prices, the start of the baseline.",
            "link": "https://github.com/PolicyEngine/microcosm/issues/1113",
        },
        {
            "id": "tdcv",
            "topic": "Typical bills",
            "detail": "Ofgem cut typical consumption on 1 Jul 2026, so published caps from July (£1,663, £1,723, £1,999) can't be compared with £1,641. Every quarter is re-costed from unit rates and standing charges at the old 2,700 / 11,500 kWh.",
            "link": "https://www.ofgem.gov.uk/sites/default/files/2026-05/Review%20of%20typical%20domestic%20consumption%20values%20decision.pdf",
        },
        {
            "id": "baseline",
            "topic": "Baseline",
            "detail": "Current law at forecast prices. Each household's electricity and gas spend rises by its fuel's price change and is loaded into PolicyEngine. The Energy Price Guarantee ended in April 2024, so it pays nothing.",
            "link": "https://www.ofgem.gov.uk/press-release/energy-price-cap-will-rise-4-october-2026",
        },
        {
            "id": "vat",
            "topic": "Electricity VAT",
            "detail": "VAT on domestic electricity is 0% from 1 Oct 2026 to 31 Mar 2027 (SI 2026/987), then returns to 5%. The 2027-28 baseline includes the return.",
            "link": "https://www.legislation.gov.uk/uksi/2026/987/made",
        },
        {
            "id": "forecast2728",
            "topic": "2027-28 prices",
            "detail": "April–September 2027 use the average of EDF, British Gas and E.ON Next forecasts; October–December 2027 uses OVO's forecast, and January–March 2028 holds that level. Forecasts give no fuel split, so Cornwall Insight's January unit rates are scaled to each total, with 5% VAT on electricity.",
            "link": "https://www.eonnext.com/electricity-and-gas/price-cap/predictions",
        },
        {
            "id": "poverty",
            "topic": "Poverty",
            "detail": "PolicyEngine's HBAI relative poverty. HBAI income excludes energy bills and energy bill support (bill credits, rebates, price guarantees), so only cash paid as income (Cost of Living Payment, targeted discount, Warm Home Discount) moves it.",
            "link": "https://www.gov.uk/government/statistics/households-below-average-income-for-financial-years-ending-1995-to-2024",
        },
        {
            "id": "behaviour",
            "topic": "Behaviour",
            "detail": "Households keep using the same energy; no cut in use, no change to benefit uprating from higher inflation. Northern Ireland uses GB prices as a proxy.",
            "link": "https://github.com/PolicyEngine/energy-price-shock",
        },
        {
            "id": "rf",
            "topic": "Targeted discount",
            "detail": "Resolution Foundation design: £175 to households on means-tested benefits or whose highest individual income is under £24,000.",
            "link": "https://www.resolutionfoundation.org/publications/billing-me-softly/",
        },
        {
            "id": "budget",
            "topic": "Budget date",
            "detail": "Autumn Budget and OBR forecast, Wednesday 28 October 2026. The OBR's March 2026 forecast closed before the conflict.",
            "link": "https://obr.uk/autumn-2026-forecast-date-announced/",
        },
    ]
    for name, data in [
        ("years", yrs),
        ("options", opts),
        ("deciles", dec),
        ("hh_types", hh),
        ("regions", regs),
        ("notes", notes),
    ]:
        _dump(data, OUT / f"{name}.json")
    _dump(r["provenance"], OUT / "provenance.json")
    print(
        {
            k: len(v)
            for k, v in [
                ("price", rows),
                ("years", yrs),
                ("options", opts),
                ("deciles", dec),
                ("hh", hh),
            ]
        }
    )
