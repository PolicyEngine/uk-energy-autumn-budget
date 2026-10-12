"""Run the model and write the dashboard's data files.

energy-budget            # writes src/data/*.json and reproducibility.json
"""

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from .baseline import dataset_path, provenance, run_baseline
from .budget_options import (
    FORECAST_2027_28,
    WHD_LINKS,
    _quarter_rates_2027_28,
    run_budget_options,
)
from .config import (
    DATASET_FILE,
    DATASET_RELEASE,
    DATASET_REPO,
    DATASET_REVISION,
    DATASET_SHA256,
    TARIFFS,
    WINTER_SHARE,
    fuel_bill,
)

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

HH_TYPE_LABELS = {
    "COUPLE_NO_CHILDREN": "Couple no children",
    "COUPLE_PENSIONER": "Couple pensioner",
    "COUPLE_WITH_CHILDREN": "Couple with children",
    "LONE_PARENT": "Lone parent",
    "SINGLE_PENSIONER": "Single pensioner",
    "SINGLE_WORKING_AGE": "Single working age",
    "MULTI_UNIT": "Multiple family units",
}

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "src" / "data"
COMMAND = "HF_HUB_OFFLINE=1 .venv/bin/energy-budget"


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
    write_receipt(r["provenance"])


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(*args):
    try:
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def write_receipt(prov):
    """Reproducibility receipt: code, runtime, data and output hashes."""
    status = _git("status", "--porcelain")
    receipt = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "command": COMMAND,
        "git": {
            "head": _git("rev-parse", "HEAD"),
            "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "uncommitted_changes": bool(status),
            "uncommitted_paths": status.splitlines() if status else [],
        },
        "runtime": {
            "python": sys.version.split()[0],
            "policyengine": version("policyengine"),
            "policyengine_uk": version("policyengine-uk"),
            "policyengine_core": version("policyengine-core"),
            "bundle_id": prov.get("bundle_id"),
            "bundle_model_version": prov.get("model_version"),
        },
        "dataset": {
            "repo": DATASET_REPO,
            "file": DATASET_FILE,
            "revision": DATASET_REVISION,
            "release": DATASET_RELEASE,
            "sha256_pinned": DATASET_SHA256,
            "sha256_verified": _sha256(dataset_path()),
        },
        "model_choices": {
            "kwh_basis": prov.get("kwh_basis"),
            "consumption_profile": prov.get("consumption_profile"),
        },
        "outputs": {
            f"src/data/{p.name}": _sha256(p) for p in sorted(OUT.glob("*.json"))
        },
    }
    if receipt["dataset"]["sha256_verified"] != DATASET_SHA256:
        raise RuntimeError("dataset SHA-256 does not match the pin")
    _dump(receipt, ROOT / "reproducibility.json")


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
        "rf_targeted_discount": "Targeted discount (RF, simplified)",
        "cost_of_living_payment": "£300 Cost of Living Payment",
        "whd_top_up": "Warm Home Discount +£100 (proxy)",
        "remove_levies": "Remove remaining levies",
        "extend_vat_cut": "Extend electricity VAT cut",
        "flat_400": "£400 to every household",
        "cap_freeze": "Cap freeze at April–June 2026 tariffs",
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
                "consumption_profile": b["consumption_profile"],
                "kwh_basis": b["kwh_basis"],
                "typical_bill_1641_basis": b["typical_bill_old_tdcv"],
                "mean_bill": b["mean_bill"],
                "mean_bill_apr_jun_2026_prices": b["mean_bill_apr_jun_2026_prices"],
                "total_bill_bn": b["total_bill_bn"],
                "total_bill_dataset_prices_bn": b["total_bill_dataset_prices_bn"],
                "implied_elec_twh": b["implied_twh"]["elec"],
                "implied_gas_twh": b["implied_twh"]["gas"],
                "households_m": b["households_m"],
                "mean_extra_cost": b["mean_extra_cost"],
                "total_extra_cost_bn": b["total_extra_cost_bn"],
                **{
                    f"{name}__{k}": val
                    for name, sens in b["sensitivities"].items()
                    for k, val in sens.items()
                    if k != "option_cost_bn"
                },
                "note": b["note"],
                "poverty_bhc_pct": p["bhc"],
                "poverty_ahc_pct": p["ahc"],
                "child_poverty_ahc_pct": p["child_ahc"],
                "absolute_poverty_ahc_pct": p["absolute_ahc"],
                "absolute_child_poverty_ahc_pct": p["absolute_child_ahc"],
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
                    "recipients_m": o["recipients_m"],
                    "share_of_shock_covered_pct": o["share_of_shock_offset_pct"],
                    "note": o["note"],
                    "assumptions": o.get("assumptions"),
                    "links": o.get("links"),
                    "sensitivity_cost_bn": {
                        name: sens["option_cost_bn"][k]
                        for name, sens in b["sensitivities"].items()
                        if k in sens["option_cost_bn"]
                    }
                    or None,
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
                "hh_type": HH_TYPE_LABELS.get(t, t.replace("_", " ").capitalize()),
                "share_of_households_pct": b["hh_type_share_pct"].get(t),
                "extra_cost": val,
                "bill": b["bill_by_hh_type"][t],
            }
            for k, o in v["options"].items():
                row[k] = o["by_hh_type"][t]
            hh.append(row)
    notes = build_notes(r)
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


def build_notes(r):
    """Method notes, with versions and caseloads taken from the results."""
    prov = r["provenance"]
    years = {fy: v for fy, v in r.items() if fy != "provenance"}
    whd = {fy: v["options"]["whd_top_up"]["recipients_m"] for fy, v in years.items()}
    whd_text = ", ".join(f"{m:.1f}m in {fy}" for fy, m in whd.items())
    sens = {fy: v["baseline"]["sensitivities"] for fy, v in years.items()}
    eq = {fy: s.get("profile_equal", {}) for fy, s in sens.items()}
    profile_text = "; ".join(
        f"{fy}: typical bill £{v['baseline']['typical_bill_old_tdcv_exact']:,.2f} seasonal vs "
        f"£{eq[fy].get('typical_bill_old_tdcv', float('nan')):,.2f} equal-weight, "
        f"extra cost £{v['baseline']['total_extra_cost_bn']}bn vs "
        f"£{eq[fy].get('total_extra_cost_bn', float('nan'))}bn"
        for fy, v in years.items()
    )
    zero_kwh = next(iter(years.values()))["baseline"]["connected_zero_kwh_pct"]["elec"]
    basis_key = next(
        (k for k in next(iter(sens.values())) if k.startswith("kwh_basis_")), None
    )
    basis_text = (
        "; ".join(
            f"{fy}: extra cost £{s[basis_key]['total_extra_cost_bn']}bn, mean bill £{s[basis_key]['mean_bill']:,}"
            for fy, s in sens.items()
        )
        if basis_key
        else ""
    )
    return [
        {
            "id": "data",
            "topic": "Data and model",
            "detail": (
                f"policyengine.py {prov['policyengine_version']} (policyengine-uk "
                f"{prov['model_version']}, bundle {prov['bundle_id']}) on Microcosm UK "
                f"2024-25, release {prov['dataset_release']}. The release is not in the "
                "certified bundle, so it runs with allow_unmanaged=True, pinned by "
                "repository revision and SHA-256."
            ),
            "link": "https://github.com/PolicyEngine/policyengine.py",
        },
        {
            "id": "kwh",
            "topic": "Usage and price basis",
            "detail": (
                "Microcosm builds each household's energy spend as kWh priced at DESNZ "
                "Quarterly Energy Prices for FY2024-25 (regional unit cost plus fixed cost, "
                "VAT included), then reweights households to ONS 2025 spending. Each "
                "household's kWh are recovered as (spend − fixed cost) ÷ unit rate and "
                "every scenario is costed from those kWh: unit rate × kWh plus the standing "
                "charge. Households with no spend on a fuel pay no standing charge for it. "
                f"In the data, {zero_kwh:.1f}% of households have electricity spend exactly "
                "equal to their region's fixed cost, so zero electricity kWh: only the "
                "standing charge moves for them, which understates their bill change."
                + (
                    f" Sensitivity with CY2025 Ofgem cap tariffs as the reference ({basis_text})."
                    if basis_text
                    else ""
                )
            ),
            "link": "https://github.com/PolicyEngine/microcosm/issues/1113",
        },
        {
            "id": "seasonal",
            "topic": "Seasonal use",
            "detail": (
                f"Central estimate uses Ofgem's winter shares: {WINTER_SHARE['gas']:.0%} of gas "
                f"and {WINTER_SHARE['elec']:.0%} of electricity used in October–March, split "
                "equally between the two quarters of each half-year; standing charges are "
                "time-weighted. Equal quarterly use is reported as a sensitivity ("
                + profile_text
                + ")."
            ),
            "link": "https://www.ofgem.gov.uk/sites/default/files/docs/2018/11/appendix_4_-_wholesale_costs.pdf#page=6",
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
            "detail": "Current law at forecast prices. Each household's kWh are costed at each quarter's tariffs and the resulting electricity and gas bills are loaded into PolicyEngine. The Energy Price Guarantee ended in April 2024, so it pays nothing.",
            "link": "https://www.ofgem.gov.uk/press-release/energy-price-cap-will-rise-4-october-2026",
        },
        {
            "id": "tariffs",
            "topic": "Tariff types",
            "detail": "Every household is modelled on the capped variable tariff. Around 35% of households are on fixed tariffs and will not see the October 2026 cap rise (Ofgem); tariff type, payment method and contract expiry are not modelled, and no correction is inferred from the 35% share. The electricity VAT cut reaches fixed-tariff customers too.",
            "link": "https://www.ofgem.gov.uk/press-release/energy-price-cap-will-rise-4-october-2026",
        },
        {
            "id": "vat",
            "topic": "Electricity VAT",
            "detail": "VAT on domestic electricity is 0% for supplies in England, Wales and Scotland from 1 Oct 2026 to 31 Mar 2027 (SI 2026/987), then returns to 5%. Northern Ireland keeps the 5% reduced rate, so its electricity carries VAT in every quarter. The 2027-28 baseline includes the return.",
            "link": "https://www.legislation.gov.uk/uksi/2026/987/made",
        },
        {
            "id": "forecast2728",
            "topic": "2027-28 prices",
            "detail": "April–September 2027 use the average of supplier forecasts (EDF, British Gas, E.ON Next); October–December 2027 uses OVO's forecast with 5% electricity VAT restored, and January–March 2028 holds that level. Forecasts give no fuel split, so Cornwall Insight's January unit rates and standing charges are scaled to each total.",
            "link": "https://www.eonnext.com/electricity-and-gas/price-cap/predictions",
        },
        {
            "id": "cap_freeze",
            "topic": "Cap freeze",
            "detail": "Electricity and gas unit rates and standing charges are held at April–June 2026 levels. The cost is each household's forecast bill minus its bill at those tariffs for the same kWh, floored at zero. It is a price restoration, so it sits outside HBAI income and has no poverty effect.",
            "link": "https://www.ofgem.gov.uk/your-energy-supply/your-energy-bill/energy-price-cap-unit-rates-and-standing-charges",
        },
        {
            "id": "rf",
            "topic": "Targeted discount (RF, simplified)",
            "detail": "A simplified fixed-payment illustration of the Resolution Foundation's unit-rate discount, with three assumptions: a flat £175 per eligible household (RF's average) rather than a unit-rate discount; an annual income test rather than the previous three months' income; and full take-up. Eligible: GB households on means-tested benefits or whose highest individual income is under £24,000.",
            "link": "https://www.resolutionfoundation.org/publications/billing-me-softly/",
        },
        {
            "id": "whd",
            "topic": "Warm Home Discount top-up",
            "detail": (
                "Means-tested-household proxy: £100 to every GB household where any member "
                "receives a listed means-tested benefit during the year. The scheme's actual "
                "rules (qualifying date, participating supplier, account holder; core and "
                "broader groups in Scotland) are not modelled. Modelled caseload "
                f"{whd_text}, against around 6 million households in England and Wales "
                "(DESNZ, Continuing the Warm Home Discount Scheme: Government Response, January 2026)."
            ),
            "link": WHD_LINKS[0],
            "links": WHD_LINKS
            + [
                "https://assets.publishing.service.gov.uk/media/697b454bf8f4a746d9572efe/continuing-the-warm-home-discount-scheme-government-response.pdf"
            ],
        },
        {
            "id": "poverty",
            "topic": "Poverty",
            "detail": "Relative poverty: people in households below 60% of median equivalised HBAI income (PolicyEngine UK in_relative_poverty_bhc/ahc, the DWP headline measure). Absolute poverty (in_poverty_*, a fixed FYE 2025 line) is also exported. DWP counts the Warm Home Discount, a bill credit, as HBAI income, so the top-up moves poverty; the RF discount is counted the same way by assumption. Price cuts (cap freeze, VAT, levies) lower bills rather than raise income, so they do not move HBAI poverty.",
            "link": "https://www.gov.uk/government/statistics/households-below-average-income-for-financial-years-ending-1995-to-2025/households-below-average-income-background-information-and-methodology-report-fye-2025",
        },
        {
            "id": "deciles",
            "topic": "Income deciles",
            "detail": "Deciles of equivalised HBAI household income before housing costs, person-weighted (household weight × household size), as PolicyEngine UK defines household_income_decile. Households with negative income are excluded from the ten deciles. Gains shown are household-weighted means within each decile.",
            "link": "https://github.com/PolicyEngine/policyengine-uk/blob/2.125.1/policyengine_uk/variables/household/income/household_income_decile.py",
        },
        {
            "id": "hh_types",
            "topic": "Household types",
            "detail": "Households with more than one benefit unit (for example adult children or sharers) are grouped as 'Multiple family units'; other households take their family type, split by whether anyone is over State Pension age.",
            "link": "https://github.com/PolicyEngine/uk-energy-autumn-budget/issues/1",
        },
        {
            "id": "behaviour",
            "topic": "Behaviour",
            "detail": "A static scenario: households keep the same kWh, and benefit uprating does not respond to higher inflation. Northern Ireland uses GB prices as a proxy.",
            "link": "https://github.com/PolicyEngine/energy-price-shock",
        },
        {
            "id": "budget",
            "topic": "Budget date",
            "detail": "Autumn Budget and OBR forecast, Wednesday 28 October 2026. The OBR's March 2026 forecast closed before the conflict.",
            "link": "https://obr.uk/autumn-2026-forecast-date-announced/",
        },
    ]
