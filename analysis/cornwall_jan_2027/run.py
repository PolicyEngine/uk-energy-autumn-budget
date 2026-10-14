"""Cornwall Insight's January-March 2027 cap forecast against the October-December 2026 cap.

Great Britain only: Northern Ireland is outside the Ofgem price cap. Both
caps have 0% VAT on GB electricity (SI 2026/987), so the comparison is like
for like. Writes results.json and decile_table.md next to this file.

Run from the repo root:
    PYTHONPATH=src .venv/bin/python analysis/cornwall_jan_2027/run.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from energy_budget.baseline import provenance, run_baseline, weighted_mean
from energy_budget.config import TARIFFS, quarter_shares

YEAR = 2026  # FY 2026-27
NEW, OLD = "jan_mar_2027_cornwall", "oct_dec_2026"
NEW_TDCV = {"elec": 2_500, "gas": 9_500}  # Ofgem TDCVs from 1 Jul 2026
JAN_MAR = 3  # index of Jan-Mar in financial-year quarter order
OUT = Path(__file__).parent


def typical_bill(period):
    return sum(
        (TARIFFS[period][f][0] * NEW_TDCV[f] + TARIFFS[period][f][1] * 365) / 100
        for f in NEW_TDCV
    )


def extra_costs(d, gb):
    """Annual (rates held a year) and Jan-Mar-only (seasonal use) extra cost."""
    annual, quarter = 0.0, 0.0
    for f in ("elec", "gas"):
        (u1, s1), (u0, s0) = TARIFFS[NEW][f], TARIFFS[OLD][f]
        kwh, on = d[f"{f}_kwh"], d[f"has_{f}"] & gb
        share = quarter_shares(f, "seasonal")[JAN_MAR]
        annual = annual + np.where(on, (kwh * (u1 - u0) + (s1 - s0) * 365) / 100, 0)
        quarter = quarter + np.where(
            on, (share * kwh * (u1 - u0) + (s1 - s0) * 365 / 4) / 100, 0
        )
    return annual, quarter


def illustrative_poverty(sim, annual):
    """People newly below a fixed 60%-of-median line once the annual extra
    cost is deducted from income. HBAI income does not deduct energy bills,
    so this is not an official poverty measure."""
    cost = sim.map_result(annual, "household", "person")
    w = np.asarray(sim.calculate("person_weight", YEAR, unweighted=True))
    age = np.asarray(sim.calculate("age", YEAR).values)
    out = {}
    for m, suffix in (("bhc", ""), ("ahc", "_ahc")):

        def person(var):
            return np.asarray(sim.calculate(var, YEAR, map_to="person").values)

        net = person(f"hbai_household_net_income{suffix}")
        eq = person(f"equiv_hbai_household_net_income{suffix}")
        poor = person(f"in_relative_poverty_{m}").astype(bool)
        # The relative line is computed inside in_relative_poverty_*; recover
        # it as the cut-point between people in and out of poverty.
        line = (eq[poor].max() + eq[~poor & (eq > 0)].min()) / 2
        factor = np.where((eq != 0) & (net != 0), net / np.where(eq == 0, 1, eq), 1)
        newly = ~poor & (eq - cost / factor < line)
        out[m] = {
            "line_equivalised_gbp": round(float(line)),
            "baseline_rate_pct": round(float((w * poor).sum() / w.sum()) * 100, 2),
            "newly_below_m": round(float((w * newly).sum()) / 1e6, 3),
            "newly_below_under_18_m": round(
                float((w * newly * (age < 18)).sum()) / 1e6, 3
            ),
        }
    return out


def main():
    d = run_baseline()
    sim, w = d["sim"], d["weights"]
    gb = pd.Series(d["region"]).astype(str).to_numpy() != "NORTHERN_IRELAND"
    annual, quarter = extra_costs(d, gb)
    # HBAI household net income (DWP's definition), not PolicyEngine's broader
    # household_net_income, so shares compare with ONS and DWP figures.
    income = np.asarray(sim.calculate("hbai_household_net_income", YEAR).values)
    decile = d["decile"]

    deciles = []
    for k in range(1, 11):
        m = (decile == k) & gb
        a, q, y = (weighted_mean(v, w, m) for v in (annual, quarter, income))
        deciles.append(
            {
                "decile": k,
                "extra_cost_annual": round(a),
                "share_of_income_pct": round(100 * a / y, 2),
                "extra_cost_jan_mar": round(q),
                "share_of_quarter_income_pct": round(100 * q / (y / 4), 2),
                "mean_net_income": round(y),
            }
        )

    results = {
        "comparison": f"{NEW} vs {OLD}, Great Britain",
        "typical_bill_new_tdcv": {
            OLD: round(typical_bill(OLD), 2),
            NEW: round(typical_bill(NEW), 2),
            "rise": round(typical_bill(NEW) - typical_bill(OLD), 2),
        },
        "mean_extra_cost_annual": round(weighted_mean(annual, w, gb)),
        "mean_extra_cost_jan_mar": round(weighted_mean(quarter, w, gb)),
        "households_gb_m": round(float(np.sum(w * gb)) / 1e6, 2),
        "deciles": deciles,
        "illustrative_poverty": illustrative_poverty(sim, annual),
        "provenance": provenance(sim),
    }
    (OUT / "results.json").write_text(
        json.dumps(results, indent=1, default=float) + "\n"
    )

    rows = [
        "| Decile | Extra cost a year | Share of net income | Extra cost, Jan–Mar only | Share of that quarter's income |",
        "|---|---|---|---|---|",
    ]
    for r in deciles:
        rows.append(
            f"| {r['decile']} | £{r['extra_cost_annual']} | {r['share_of_income_pct']:.1f}% "
            f"| £{r['extra_cost_jan_mar']} | {r['share_of_quarter_income_pct']:.1f}% |"
        )
    rows.append(
        f"| All GB households | £{results['mean_extra_cost_annual']} | | "
        f"£{results['mean_extra_cost_jan_mar']} | |"
    )
    (OUT / "decile_table.md").write_text("\n".join(rows) + "\n")
    print(
        json.dumps(
            {k: v for k, v in results.items() if k != "provenance"},
            indent=1,
            default=float,
        )
    )


if __name__ == "__main__":
    main()
