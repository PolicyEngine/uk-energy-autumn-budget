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

import numpy as np

from .baseline import _hh_array, _weights, provenance, run_baseline
from .bills import FUELS, price_basis_residual
from .budget_options import WHD_LINKS, run_budget_options
from .config import (
    DATASET_ENERGY_LEVELS,
    DATASET_YEAR,
    ELEC_VAT,
    NEG_BLOCK_KWH,
    NEG_GAS_TO_ELEC_FACTOR,
    NEG_PRICE_MULTIPLE,
    NEG_SOURCE_COST_BN,
    NEG_SOURCE_UNIT_RATE,
    NEW_TDCV,
    PRICE_PATH,
    TDCV_ELEC_KWH,
    TDCV_GAS_KWH,
    WINTER_SHARE,
)
from .prices import published_rates, quarter_rates

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
    prov = provenance(data["sim"])
    dataset_checks = dataset_validation(data)
    # Free the extraction simulation before the scenario runs.
    data["sim"] = None
    r = run_budget_options(data)
    r["provenance"] = prov
    r["validation"] = dataset_checks
    _dump(r, OUT / "results.json")
    write_tables(r)
    write_receipt(r["provenance"], data["dataset_path"])


def dataset_validation(data):
    """Checks on the dataset's energy export, at its own (2024) weights."""
    sim = data["sim"]
    w = _weights(sim, DATASET_YEAR)
    region = np.asarray(data["region"]).astype(str)
    is_ni = region == "NORTHERN_IRELAND"
    out = {"households_m": round(float(np.sum(w)) / 1e6, 2)}
    for f, col in (("elec", "electricity"), ("gas", "gas")):
        kwh, spend = data[f"{f}_kwh"], data[f"{f}_spend"]
        connected = data[f"has_{f}"]
        residual = price_basis_residual(spend, kwh, region, f)
        out[f] = {
            "twh": round(float(np.sum(kwh * w)) / 1e9, 2),
            "spend_bn": round(float(np.sum(spend * w)) / 1e9, 2),
            "max_abs_price_basis_residual_gbp": float(np.max(np.abs(residual))),
            "records": len(kwh),
            "connected_zero_kwh_records": int(np.sum(connected & (kwh == 0))),
            "connected_zero_kwh_pct": round(
                float(np.sum(w * (connected & (kwh == 0))) / np.sum(w)) * 100, 2
            ),
            "not_connected_records": int(np.sum(~connected)),
            "not_connected_pct": round(
                float(np.sum(w * ~connected) / np.sum(w)) * 100, 2
            ),
            "not_connected_northern_ireland_records": int(np.sum(~connected & is_ni)),
            "kwh_without_spend_records": int(np.sum((kwh > 0) & (spend == 0))),
            "spend_above_fixed_without_kwh_records": int(
                np.sum((kwh == 0) & (np.abs(residual) > 0.01))
            ),
        }
        if out[f]["max_abs_price_basis_residual_gbp"] > 0.01:
            raise AssertionError(f"{col} export is not on the documented price basis")
        if out[f]["kwh_without_spend_records"]:
            raise AssertionError(f"{col} kWh without spending")
    out["release_levels"] = DATASET_ENERGY_LEVELS
    poverty = sim.calculate("in_relative_poverty_ahc", DATASET_YEAR, map_to="person")
    out["relative_poverty_ahc_pct"] = round(float(poverty.mean()) * 100, 2)
    out["household_id_aligned"] = bool(
        np.array_equal(_hh_array(sim, "household_id"), data["household_id"])
    )
    return out


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


def write_receipt(prov, dataset_path):
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
            "managed": prov.get("managed"),
            "name": prov.get("dataset"),
            "uri": prov.get("dataset_uri"),
            "build_id": prov.get("dataset_build_id"),
            "revision": prov.get("dataset_revision"),
            "sha256_certified": prov.get("certified_dataset_sha256"),
            "sha256_verified": _sha256(dataset_path),
        },
        "model_choices": {
            "baseline_policy": prov.get("baseline_policy"),
            "consumption_profile": prov.get("consumption_profile"),
            "kwh_source": prov.get("kwh_source"),
        },
        "outputs": {
            f"src/data/{p.name}": _sha256(p) for p in sorted(OUT.glob("*.json"))
        },
    }
    if receipt["dataset"]["sha256_verified"] != receipt["dataset"]["sha256_certified"]:
        raise RuntimeError("dataset SHA-256 does not match the certified bundle")
    _dump(receipt, ROOT / "reproducibility.json")


def bill(rates, f, kwh):
    u, s = rates[f]
    return (u * kwh + s * 365) / 100


def price_rows():
    """The price path as shown: rates at post-Budget GB law, with sources."""
    base = quarter_rates("apr_jun_2026")
    base_bill = {
        f: bill(base, f, TDCV_ELEC_KWH if f == "elec" else TDCV_GAS_KWH) for f in FUELS
    }
    rows = []
    for q in PRICE_PATH:
        rates = quarter_rates(q["key"])
        pub = published_rates(q["key"])
        e = bill(rates, "elec", TDCV_ELEC_KWH)
        g = bill(rates, "gas", TDCV_GAS_KWH)
        rows.append(
            {
                "key": q["key"],
                "period": q["period"],
                "fy": f"{q['fy']}-{str(q['fy'] + 1)[2:]}",
                "kind": q["kind"],
                "source": q["source"],
                "source_date": q["source_date"],
                "link": q["link"],
                "published_cap": q["published_cap"],
                "published_tdcv": q["published_tdcv"],
                "published_elec_vat_pct": round(q["embedded_elec_vat"] * 100),
                "elec_vat_gb_pct": round(ELEC_VAT["post_budget"]["GB"][q["key"]] * 100),
                "elec_vat_ni_pct": round(ELEC_VAT["post_budget"]["NI"][q["key"]] * 100),
                "elec_vat_gb_pre_budget_pct": round(
                    ELEC_VAT["pre_budget"]["GB"][q["key"]] * 100
                ),
                "elec_unit_p": round(rates["elec"][0], 2),
                "elec_standing_p": round(rates["elec"][1], 2),
                "gas_unit_p": round(rates["gas"][0], 2),
                "gas_standing_p": round(rates["gas"][1], 2),
                "bill_1641_basis": round(e + g),
                # Typical bill on Ofgem's current (post-July 2026) consumption,
                # at post-Budget VAT; and as published.
                "typical_bill": round(
                    bill(rates, "elec", NEW_TDCV["elec"])
                    + bill(rates, "gas", NEW_TDCV["gas"])
                ),
                "typical_bill_as_published": round(
                    bill(pub, "elec", NEW_TDCV["elec"])
                    + bill(pub, "gas", NEW_TDCV["gas"])
                ),
                "elec_change_pct": round((e / base_bill["elec"] - 1) * 100, 1),
                "gas_change_pct": round((g / base_bill["gas"] - 1) * 100, 1),
            }
        )
    return rows


def write_tables(r):
    rows = price_rows()
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
        "extend_vat_cut": "Extend VAT cut to March 2028",
        "flat_400": "£400 to every household",
        "cap_freeze": "Cap freeze at April–June 2026 tariffs",
        "national_energy_guarantee": "National Energy Guarantee",
    }
    measures = []
    for fy, v in _years(r).items():
        b = v["baseline"]
        p = b["poverty"]
        yrs.append(
            {
                "fy": fy,
                "elec_change_pct": b["elec_price_vs_apr_jun_2026_pct"],
                "gas_change_pct": b["gas_price_vs_apr_jun_2026_pct"],
                "consumption_profile": b["consumption_profile"],
                "policy": b["policy"],
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
                "connected_zero_elec_kwh_pct": b["connected_zero_kwh_pct"]["elec"],
                "pre_budget_typical_bill_1641_basis": v["pre_budget"][
                    "typical_bill_old_tdcv"
                ],
                "pre_budget_mean_bill": v["pre_budget"]["mean_bill"],
                "pre_budget_mean_extra_cost": v["pre_budget"]["mean_extra_cost"],
                "pre_budget_total_extra_cost_bn": v["pre_budget"][
                    "total_extra_cost_bn"
                ],
            }
        )
        for k, m in v["budget_measures"].items():
            pc = m.get("poverty_change_pp")
            measures.append(
                {
                    "fy": fy,
                    "measure_id": k,
                    "measure": m["label"],
                    "cost_bn": m["cost_bn"],
                    "avg_per_household": m["avg_per_household"],
                    "share_receiving_pct": m["share_receiving_pct"],
                    "recipients_m": m["recipients_m"],
                    "counted_in_hbai_income": m.get("counted_in_hbai_income"),
                    "poverty_ahc_change_pp": pc and pc["ahc"],
                    "child_poverty_ahc_change_pp": pc and pc["child_ahc"],
                    "poverty_bhc_change_pp": pc and pc["bhc"],
                    "deciles": m["deciles"],
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
                    "bill_cut_pct": o.get("bill_cut_pct"),
                    "cost_at_source_prices_bn": o.get("cost_at_source_prices_bn"),
                    "unit_rate_p": o.get("unit_rate_p"),
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
            row = {
                "fy": fy,
                "region": REGION_LABELS.get(reg, reg),
                "extra_cost": b["extra_cost_by_region"][reg],
                "bill": val,
            }
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
        ("budget_measures", measures),
    ]:
        _dump(data, OUT / f"{name}.json")
    _dump(r["provenance"], OUT / "provenance.json")
    _dump(
        {
            "dataset": r["validation"],
            **{fy: v["validation"] for fy, v in _years(r).items()},
        },
        OUT / "validation.json",
    )
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


def _years(r):
    return {fy: v for fy, v in r.items() if fy not in ("provenance", "validation")}


def build_notes(r):
    """Method notes, with versions and caseloads taken from the results."""
    prov = r["provenance"]
    checks = r["validation"]
    years = _years(r)
    whd = {fy: v["options"]["whd_top_up"]["recipients_m"] for fy, v in years.items()}
    whd_text = ", ".join(f"{m:.1f}m in {fy}" for fy, m in whd.items())
    hep = years["2026-27"]["budget_measures"]["household_energy_payment"]
    vat = years["2027-28"]["budget_measures"]["electricity_vat_extension"]
    sens = {fy: v["baseline"]["sensitivities"] for fy, v in years.items()}
    eq = {fy: s.get("profile_equal", {}) for fy, s in sens.items()}
    profile_text = "; ".join(
        f"{fy}: typical bill £{v['baseline']['typical_bill_old_tdcv_exact']:,.2f} seasonal vs "
        f"£{eq[fy].get('typical_bill_old_tdcv', float('nan')):,.2f} equal-weight, "
        f"extra cost £{v['baseline']['total_extra_cost_bn']}bn vs "
        f"£{eq[fy].get('total_extra_cost_bn', float('nan'))}bn"
        for fy, v in years.items()
    )
    neg = {fy: v["options"]["national_energy_guarantee"] for fy, v in years.items()}
    neg_text = "; ".join(
        f"{fy}: £{o['cost_bn']:.2f}bn at {o['unit_rate_p']['elec']:.1f}p electricity and "
        f"{o['unit_rate_p']['gas']:.1f}p gas"
        for fy, o in neg.items()
    )
    neg_source = neg["2026-27"]["cost_at_source_prices_bn"]
    zero_kwh = checks["elec"]["connected_zero_kwh_pct"]
    no_gas = checks["gas"]["not_connected_pct"]
    return [
        {
            "id": "data",
            "topic": "Data and model",
            "detail": (
                f"policyengine.py {prov['policyengine_version']} (policyengine-uk "
                f"{prov['model_version']}, bundle {prov['bundle_id']}) on its certified "
                f"Microcosm UK 2024-25 national dataset, release {prov['dataset_build_id']}, "
                "loaded through the package's managed loader and checked against the "
                "bundle's SHA-256."
            ),
            "link": "https://github.com/PolicyEngine/policyengine.py/releases/tag/"
            + str(prov["policyengine_version"]),
        },
        {
            "id": "kwh",
            "topic": "Energy use",
            "detail": (
                "Each household's annual electricity and gas use in kWh comes from the "
                "dataset's export (calendar 2024: gas levelled to DESNZ Energy Trends "
                "domestic volumes, electricity to ONS 2024 spending) and is held fixed. "
                "The dataset's spending columns are those kWh priced at DESNZ Quarterly "
                "Energy Prices CY2024 (regional unit cost plus fixed cost, 5% VAT "
                "included); the pipeline checks that basis but costs every scenario from "
                f"kWh. {zero_kwh:.1f}% of households use no electricity and pay only the "
                f"standing charge; {no_gas:.1f}% have no mains gas and pay no gas standing "
                "charge."
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
            "detail": "Post-Budget law at forecast prices: the Household Energy Payment and the electricity VAT extension announced in Budget 2026 are in the baseline. Each household's kWh are costed at each quarter's tariffs and the resulting electricity and gas bills are loaded into PolicyEngine. The Energy Price Guarantee ended in April 2024, so it pays nothing.",
            "link": "https://www.gov.uk/government/news/what-the-autumn-budget-2026-means-for-your-energy-bills",
        },
        {
            "id": "budget_measures",
            "topic": "Budget energy measures",
            "detail": (
                "Their effect is measured against a counterfactual with the same prices, data "
                "and other policies but no Household Energy Payment and electricity VAT as "
                "under SI 2026/987 alone. The payment reaches "
                f"{hep['recipients_m']:.1f}m households in 2026-27 at £{hep['cost_bn']:.2f}bn; "
                f"the VAT extension saves households £{vat['cost_bn']:.2f}bn in 2027-28."
            ),
            "link": "https://www.gov.uk/government/news/what-the-autumn-budget-2026-means-for-your-energy-bills",
        },
        {
            "id": "hep",
            "topic": "Household Energy Payment",
            "detail": "£100 to households in council tax bands A–D in England in 2026-27, paid by local authorities from January 2027. policyengine-uk pays every household in those bands (it cannot identify landlords liable for council tax) and counts the payment in household and HBAI income, as DWP counted the 2022 Council Tax Rebate, so it moves poverty. The devolved governments' Barnett share is not allocated.",
            "link": "https://www.gov.uk/government/publications/budget-2026-document/budget-2026-html",
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
            "detail": "VAT on domestic electricity is 0% in England, Wales and Scotland from 1 Oct 2026 (SI 2026/987). Budget 2026 extends the zero rate to 30 June 2027 and expects it to apply in Northern Ireland from 1 April 2027; this is announced policy, not yet law. The rate is 5% from 1 July 2027. Each quarter's published electricity rates are taken back to their VAT-exclusive level and priced at the rate in force for that quarter and nation, so the April–June 2027 supplier forecast, made at 5%, is reduced. policyengine-uk's own energy VAT (a fiscal-year day-weighted rate on bills ÷ 1.05) is not used: no simulation changes a VAT rate, so it never reaches income and VAT savings are counted once.",
            "link": "https://www.legislation.gov.uk/uksi/2026/987/made",
        },
        {
            "id": "forecast2728",
            "topic": "2027-28 prices",
            "detail": "April–September 2027 use the average of supplier forecasts (EDF, British Gas, E.ON Next); October–December 2027 uses OVO's forecast, and January–March 2028 holds that level. Forecasts give no fuel split, so Cornwall Insight's January 2027 rates as forecast on 30 Sep 2026 are scaled to each total. These forecasts predate the Budget and are unchanged.",
            "link": "https://www.eonnext.com/electricity-and-gas/price-cap/predictions",
        },
        {
            "id": "cap_freeze",
            "topic": "Cap freeze",
            "detail": "Electricity and gas unit rates and standing charges are held at April–June 2026 levels. The cost is each household's forecast bill minus its bill at those tariffs for the same kWh, floored at zero. It is a price restoration, so it sits outside HBAI income and has no poverty effect.",
            "link": "https://www.ofgem.gov.uk/your-energy-supply/your-energy-bill/energy-price-cap-unit-rates-and-standing-charges",
        },
        {
            "id": "national_energy_guarantee",
            "topic": "National Energy Guarantee",
            "detail": (
                f"Two-tier version: each household's first {NEG_BLOCK_KWH['elec']:,} kWh of "
                f"electricity and {NEG_BLOCK_KWH['gas']:,} kWh of gas a year at "
                f"{NEG_PRICE_MULTIPLE['elec']:.2f} and {NEG_PRICE_MULTIPLE['gas']:.2f} times "
                "the unit rate; households with no mains gas add "
                f"{NEG_BLOCK_KWH['gas'] * NEG_GAS_TO_ELEC_FACTOR:,.0f} kWh to their electricity "
                "block. Standing charges are unchanged, with no premium tier and no child or "
                "disability allowances. The saving is min(kWh, block) times the discount on "
                "each year's consumption-weighted forecast unit rate at post-Budget VAT, "
                f"UK-wide with Northern Ireland on GB prices: {neg_text}. A price cut, outside "
                "HBAI income. The source costing model prices the scheme at flat "
                f"{NEG_SOURCE_UNIT_RATE['elec'] * 100:.0f}p and "
                f"{NEG_SOURCE_UNIT_RATE['gas'] * 100:.0f}p unit rates on LCFS 2024-25 and puts "
                f"the cost at £{NEG_SOURCE_COST_BN:.2f}bn; the same rates on Microcosm give "
                f"£{neg_source:.2f}bn."
            ),
            "link": "https://neweconomics.org/2023/04/the-national-energy-guarantee",
        },
        {
            "id": "extend_vat_cut",
            "topic": "Extend VAT cut",
            "detail": "Keeps 0% VAT on domestic electricity from 1 July 2027 to 31 March 2028, UK-wide like the Budget's extension. Its cost is the additional relief beyond the extension to June 2027, which is already in the baseline.",
            "link": "https://www.legislation.gov.uk/uksi/2026/987/made",
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
                f"{whd_text}. DESNZ estimates around 6 million recipient households across Great "
                "Britain in winter 2025/26 (DESNZ, Continuing the Warm Home Discount Scheme: "
                "Government Response, January 2026, p. 5)."
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
            "detail": "Relative poverty: people in households below 60% of median equivalised HBAI income (PolicyEngine UK in_relative_poverty_bhc/ahc, the DWP headline measure). Absolute poverty (in_poverty_*, a fixed FYE 2025 line) is also exported. Child rates (child_*) are under-18 rates (age < 18), not DWP's dependent-child cohort, which includes some 16-19-year-olds in full-time non-advanced education. HBAI income counts the Household Energy Payment, the Warm Home Discount and (as DWP did for the 2022 Energy Bills Support Scheme) the £400 credit, so they move poverty; the RF discount is counted the same way by assumption. Price cuts (VAT, cap freeze, levies) lower bills rather than raise income, so they do not move HBAI poverty.",
            "link": "https://www.gov.uk/government/statistics/households-below-average-income-for-financial-years-ending-1995-to-2025/households-below-average-income-background-information-and-methodology-report-fye-2025",
        },
        {
            "id": "deciles",
            "topic": "Income deciles",
            "detail": "Deciles of equivalised HBAI household income before housing costs, person-weighted (household weight × household size), as PolicyEngine UK defines household_income_decile. As in HBAI, negative incomes are reset to zero and ranked in the bottom decile. Gains shown are household-weighted means within each decile.",
            "link": f"https://github.com/PolicyEngine/policyengine-uk/blob/{prov['model_version']}/policyengine_uk/variables/household/income/household_income_decile.py",
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
            "topic": "Budget and forecasts",
            "detail": "Autumn Budget 2026 and the OBR's forecast were published on 28 October 2026. The energy price forecasts used here were made before the Budget and are unchanged; Ofgem's January–March 2027 cap can replace Cornwall Insight's forecast separately.",
            "link": "https://www.gov.uk/government/publications/budget-2026-document/budget-2026-html",
        },
    ]
