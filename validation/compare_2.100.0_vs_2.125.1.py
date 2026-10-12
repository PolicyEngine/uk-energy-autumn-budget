"""Compare the pipeline on the certified pair with the published run.

Inputs:

* ``src/data/results.json``: published outputs, policyengine 6.2.7 ->
  policyengine-uk 2.125.1 / policyengine-core 3.33.0 (managed constructor).
* ``validation/out_uk_2.100.0.json``: ``run_certified_pair.py`` under the
  release manifest's declared pair, policyengine-uk 2.100.0 /
  policyengine-core 3.32.5.
* ``validation/out_uk_2.125.1.json`` (required control): the same harness under
  2.125.1. It must equal ``results.json`` on every compared output, with no
  missing or extra keys, showing the harness's direct ``Microsimulation``
  construction matches the managed one; it also supplies 2.125.1 population
  checks.

Gate: both harness outputs must come from a clean tree whose source hashes
equal the current sources (``_provenance.SOURCE_GLOBS``), the certified run must
contain every published output, and the control must match exactly. If any
check fails, the report states the failure, makes no equivalence claim, and
the script exits with status 1.

Writes ``validation/compatibility_report.md``. A difference is flagged when
|diff| > 0.5% of the published value, or > £0.01bn for values in £bn, or
> 0.05pp for poverty rates and percentage shares. Published values are rounded
(pounds to £1, £bn to 0.01, rates to 0.01pp), so differences of one rounding
unit are noise.

Usage::

    python validation/compare_2.100.0_vs_2.125.1.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _provenance import source_hashes

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PUBLISHED = ROOT / "src" / "data" / "results.json"
CERTIFIED = HERE / "out_uk_2.100.0.json"
CONTROL = HERE / "out_uk_2.125.1.json"
REPORT = HERE / "compatibility_report.md"
NARRATIVE = HERE / "model_changes_2.100.0_to_2.125.1.md"

YEARS = ("2026-27", "2027-28")
BASELINE_KEYS = [
    "households_m",
    "total_bill_dataset_prices_bn",
    "implied_twh",
    "connected_zero_kwh_pct",
    "mean_bill",
    "mean_bill_apr_jun_2026_prices",
    "total_bill_bn",
    "mean_extra_cost",
    "total_extra_cost_bn",
    "poverty",
    "hh_type_share_pct",
    "bill_by_decile",
    "extra_cost_by_decile",
    "income_by_decile",
    "bill_by_hh_type",
    "extra_cost_by_hh_type",
    "bill_by_region",
]
OPTION_KEYS = [
    "cost_bn",
    "avg_per_household",
    "share_receiving_pct",
    "recipients_m",
    "share_of_shock_offset_pct",
    "poverty",
    "deciles",
    "by_hh_type",
    "by_region",
]
PCT_LIKE = ("pct", "poverty", "bhc", "ahc")


def flatten(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from flatten(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj, 1):
            yield from flatten(v, f"{prefix}[{i}]")
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        yield prefix, float(obj)


def select(results, year):
    y = results[year]
    out = {}
    for k in BASELINE_KEYS:
        out.update(dict(flatten(y["baseline"][k], f"baseline.{k}")))
    base_pov = y["baseline"]["poverty"]
    for name, row in y["options"].items():
        for k in OPTION_KEYS:
            if row.get(k) is not None:
                out.update(dict(flatten(row[k], f"{name}.{k}")))
        if row.get("poverty"):
            for m, v in row["poverty"].items():
                out[f"{name}.poverty_change_pp.{m}"] = round(v - base_pov[m], 2)
    return out


def is_pp(key):
    return any(t in key.split(".")[-1] or t in key for t in PCT_LIKE)


def flag(key, a, b):
    d = b - a
    if key.endswith("_bn") or "_bn." in key or key.split(".")[-1] == "cost_bn":
        return abs(d) > 0.01 + 1e-9
    if "poverty" in key or "pct" in key:
        return abs(d) > 0.05 + 1e-9
    if a == 0:
        return abs(d) > 0
    return abs(d / a) > 0.005


def extra_keys(pub, alt):
    """Outputs present in ``alt`` but not in the published results."""
    return [(y, k) for y in YEARS for k in select(alt, y) if k not in select(pub, y)]


def compare(pub, alt):
    rows = []
    for year in YEARS:
        a, b = select(pub, year), select(alt, year)
        for key in a:
            if key not in b:
                rows.append((year, key, a[key], math.nan, math.nan, math.nan, True))
                continue
            d = b[key] - a[key]
            pct = d / a[key] * 100 if a[key] else (0.0 if d == 0 else math.inf)
            rows.append((year, key, a[key], b[key], d, pct, flag(key, a[key], b[key])))
    return rows


def fmt(x):
    if isinstance(x, float) and math.isnan(x):
        return "n/a"
    if isinstance(x, float) and math.isinf(x):
        return "inf"
    if abs(x) >= 100:
        return f"{x:,.0f}"
    return f"{x:,.2f}"


def table(rows, header=("Year", "Output", "2.125.1 (published)", "2.100.0", "Diff", "Diff %", "Flag")):
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for year, key, a, b, d, pct, fl in rows:
        lines.append(
            f"| {year} | `{key}` | {fmt(a)} | {fmt(b)} | {fmt(d)} | "
            f"{fmt(pct)} | {'**yes**' if fl else ''} |"
        )
    return "\n".join(lines)


HEADLINE = [
    "baseline.households_m",
    "baseline.implied_twh.elec",
    "baseline.implied_twh.gas",
    "baseline.mean_bill",
    "baseline.total_bill_bn",
    "baseline.mean_extra_cost",
    "baseline.total_extra_cost_bn",
    "baseline.poverty.bhc",
    "baseline.poverty.ahc",
    "baseline.poverty.child_bhc",
    "baseline.poverty.child_ahc",
    "baseline.poverty.absolute_bhc",
    "baseline.poverty.absolute_ahc",
    "baseline.poverty.absolute_child_ahc",
    "baseline.hh_type_share_pct.SINGLE_PENSIONER",
    "baseline.hh_type_share_pct.COUPLE_PENSIONER",
]
for opt in (
    "rf_targeted_discount",
    "whd_top_up",
    "cost_of_living_payment",
    "flat_400",
    "cap_freeze",
    "extend_vat_cut",
    "remove_levies",
):
    HEADLINE += [f"{opt}.cost_bn", f"{opt}.avg_per_household", f"{opt}.share_receiving_pct"]
    if opt in ("rf_targeted_discount", "whd_top_up", "cost_of_living_payment", "flat_400"):
        HEADLINE += [
            f"{opt}.poverty_change_pp.bhc",
            f"{opt}.poverty_change_pp.ahc",
            f"{opt}.poverty_change_pp.child_ahc",
            f"{opt}.poverty_change_pp.absolute_ahc",
        ]


POP_KEYS = [
    "households_m",
    "benunits_m",
    "persons_m",
    "electricity_consumption_total_bn",
    "gas_consumption_total_bn",
    "domestic_energy_consumption_total_bn",
    "household_net_income_total_bn",
    "hbai_household_net_income_total_bn",
    "equiv_hbai_household_net_income_mean",
    "universal_credit_total_bn",
    "universal_credit_caseload_m",
    "pension_credit_total_bn",
    "pension_credit_caseload_m",
    "housing_benefit_total_bn",
    "housing_benefit_caseload_m",
    "esa_income_total_bn",
    "esa_income_caseload_m",
    "jsa_income_total_bn",
    "jsa_income_caseload_m",
    "income_support_total_bn",
    "income_support_caseload_m",
    "tax_credits_total_bn",
    "tax_credits_caseload_m",
    "in_relative_poverty_bhc_rate_pct",
    "in_relative_poverty_ahc_rate_pct",
    "in_relative_poverty_bhc_child_rate_pct",
    "in_relative_poverty_ahc_child_rate_pct",
    "in_poverty_bhc_rate_pct",
    "in_poverty_ahc_rate_pct",
    "in_poverty_bhc_child_rate_pct",
    "in_poverty_ahc_child_rate_pct",
]


def pop_table(new, old):
    lines = [
        "| Year | Variable (unreformed sim) | 2.125.1 | 2.100.0 | Diff | Diff % |",
        "|---|---|---|---|---|---|",
    ]
    for year in ("2026", "2027"):
        n, o = new[year], old[year]
        for k in POP_KEYS:
            a, b = n.get(k), o.get(k)
            if a is None or b is None:
                continue
            d = b - a
            pct = d / a * 100 if a else math.nan
            lines.append(f"| {year} | `{k}` | {a:,.3f} | {b:,.3f} | {d:+,.3f} | {fmt(pct)} |")
    return "\n".join(lines)


def provenance_errors(name, run, current):
    prov = run.get("provenance", {})
    errs = []
    if prov.get("git_dirty", True):
        errs.append(f"{name}: run from a dirty tree or without provenance")
    recorded = prov.get("source_sha256")
    if recorded is None:
        errs.append(f"{name}: no source hashes recorded (stale artifact)")
    elif recorded != current:
        changed = sorted(
            k for k in set(recorded) | set(current) if recorded.get(k) != current.get(k)
        )
        errs.append(f"{name}: sources changed since the run: {', '.join(changed)}")
    return errs


def main():
    pub = json.loads(PUBLISHED.read_text())
    cert = json.loads(CERTIFIED.read_text())
    current = source_hashes()
    errors = provenance_errors("certified run", cert, current)

    rows = compare(pub, cert)
    missing = [r for r in rows if math.isnan(r[3])]
    if missing:
        errors.append(f"certified run: {len(missing)} published outputs missing")
    by_key = {(r[0], r[1]): r for r in rows}
    head = [by_key[(y, k)] for y in YEARS for k in HEADLINE if (y, k) in by_key]
    flagged = [r for r in rows if r[6]]

    if not CONTROL.exists():
        ctrl = None
        errors.append("control run not found (validation/out_uk_2.125.1.json)")
        control_note = "Control run not found."
    else:
        ctrl = json.loads(CONTROL.read_text())
        errors += provenance_errors("control run", ctrl, current)
        crow = compare(pub, ctrl)
        cmissing = [r for r in crow if math.isnan(r[3])]
        cextra = extra_keys(pub, ctrl)
        mism = [r for r in crow if not math.isnan(r[3]) and r[4] != 0]
        if cmissing or cextra or mism:
            errors.append(
                f"control run: {len(mism)} values differ, {len(cmissing)} published "
                f"outputs missing, {len(cextra)} extra outputs"
                + (
                    " (largest: "
                    + ", ".join(
                        f"`{r[1]}` {fmt(r[4])}"
                        for r in sorted(mism, key=lambda r: -abs(r[4]))[:5]
                    )
                    + ")"
                    if mism
                    else ""
                )
            )
        control_note = (
            f"Control: the harness under policyengine-uk "
            f"{ctrl['provenance']['policyengine_uk']} (commit "
            f"`{ctrl['provenance'].get('git_commit', 'unknown')[:7]}`) reproduces "
            f"`src/data/results.json` on {len(crow) - len(mism) - len(cmissing)} of "
            f"{len(crow)} compared outputs exactly, with {len(cmissing)} missing and "
            f"{len(cextra)} extra outputs."
        )

    parts = [
        "# Compatibility: Microcosm release vs policyengine-uk 2.125.1",
        "",
        "Generated by `validation/compare_2.100.0_vs_2.125.1.py`. Do not edit the "
        "tables by hand; rerun the harness and this script.",
        "",
    ]
    if errors:
        parts += [
            "## Status: FAILED",
            "",
            "The checks below failed, so this report makes no equivalence claim. "
            "Rerun both harnesses from a clean tree at the current sources.",
            "",
            *[f"- {e}" for e in errors],
            "",
        ]
    else:
        parts += [
            "## Status: passed",
            "",
            "Both harness outputs were produced from a clean tree at the current "
            "source hashes; the certified run contains every published output; and "
            "the 2.125.1 control reproduces every published output exactly, so the "
            "direct `policyengine_uk.Microsimulation` construction is equivalent to "
            "`pe.uk.managed_microsimulation` and the differences below are "
            "model-version differences only.",
            "",
        ]

    if NARRATIVE.exists():
        parts += [NARRATIVE.read_text().strip(), ""]

    cp = cert["provenance"]
    parts += [
        "## Run",
        "",
        f"- Certified pair: policyengine-uk {cp['policyengine_uk']}, "
        f"policyengine-core {cp['policyengine_core']}, Python {cp['python']}, numpy "
        f"{cp['numpy']}, pandas {cp['pandas']}; commit "
        f"`{cp.get('git_commit', 'unknown')[:7]}`; dataset SHA-256 "
        f"`{cp['dataset_sha256']}` verified before the run.",
        f"- {control_note}",
        "- Source SHA-256 at both runs:",
        "",
        *[f"  - `{k}` `{v}`" for k, v in sorted(current.items())],
        "",
        f"- Compared outputs: {len(rows)}; flagged: {len(flagged)} "
        "(|diff| > 0.5%, > £0.01bn for £bn values, > 0.05pp for rates and shares).",
        "",
        "## Headline outputs",
        "",
        "`poverty.bhc`/`ahc` are relative poverty (below 60% of the median, "
        "`in_relative_poverty_*`); `absolute_*` are absolute poverty "
        "(`in_poverty_*`). `child_*` are under-18 rates. % of people. "
        "`poverty_change_pp` is option minus baseline.",
        "",
        table(head),
        "",
    ]
    if ctrl is not None and "population_checks" in ctrl and "population_checks" in cert:
        parts += [
            "## Population and interaction checks",
            "",
            "Weighted totals from the unreformed baseline simulation (energy inputs "
            "as stored, before the pipeline overrides them). These are the model "
            "variables the pipeline reads: energy spend, benefit caseloads that "
            "drive eligibility, net incomes and poverty.",
            "",
            pop_table(ctrl["population_checks"], cert["population_checks"]),
            "",
        ]
    parts += [
        "## All flagged differences",
        "",
        table(flagged) if flagged else "None.",
        "",
        "## All compared outputs",
        "",
        "<details><summary>Full table</summary>",
        "",
        table(rows),
        "",
        "</details>",
        "",
    ]
    REPORT.write_text("\n".join(parts))
    print(f"wrote {REPORT}: {len(rows)} outputs, {len(flagged)} flagged")
    if errors:
        for e in errors:
            print(f"FAILED: {e}", file=sys.stderr)
        sys.exit(1)
    print("passed: control matches published outputs exactly")


if __name__ == "__main__":
    main()
