"""Run the dashboard pipeline on whichever policyengine-uk is installed.

Purpose: compatibility evidence for the pinned Microcosm release
``microcosm-uk-2024-25-national-20261002T230158Z-5c6b3f68``, whose
``release_manifest.json`` declares ``policyengine-uk==2.100.0`` and
``policyengine-core==3.32.5``. The published dashboard runs on
``policyengine==6.2.7`` (policyengine-uk 2.125.1, policyengine-core 3.33.0).

``policyengine==6.2.7`` pins policyengine-uk 2.125.1, so it cannot be installed
next to 2.100.0. This harness therefore bypasses ``policyengine.py`` and builds
``policyengine_uk.Microsimulation`` directly, exactly as
``pe.uk.managed_microsimulation`` does internally (wrap the verified local H5 in
``UKSingleYearDataset``/``UKMultiYearDataset`` and pass ``reform=`` or
``scenario=``). Nothing else in the pipeline changes: the same reforms, the
same targeted-discount Scenario, the same dataset file (SHA-256 checked by
``baseline.dataset_path()``).

It also records weighted population/interaction totals for the model
variables the pipeline depends on (benefit caseloads and spend used for
eligibility, net incomes, poverty, decile), so drift between model versions can
be traced to its source.

Usage (certified pair, separate venv)::

    uv venv --python 3.13 venv-uk2100
    VIRTUAL_ENV=venv-uk2100 uv pip install policyengine-uk==2.100.0 \
        policyengine-core==3.32.5 numpy pandas microdf-python huggingface-hub
    VIRTUAL_ENV=venv-uk2100 uv pip install --no-deps -e .
    HF_HUB_OFFLINE=1 venv-uk2100/bin/python validation/run_certified_pair.py

Run with the project's own ``.venv`` (policyengine-uk 2.125.1) as a control:
the output must match ``src/data/results.json`` exactly, which shows that this
direct-construction path is equivalent to the managed one.

Writes ``validation/out_uk_<policyengine-uk version>.json``; never touches
``src/data``. Each output records the git commit, whether the tree was dirty,
and the SHA-256 of every source file that determines the results
(``_provenance.SOURCE_GLOBS``); the comparator rejects outputs whose hashes do
not match the current sources. Run from a clean tree.
"""

from __future__ import annotations

import json
import sys
import time
from importlib.metadata import version
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _provenance import git, source_hashes

import energy_budget.baseline as baseline
import energy_budget.budget_options as budget_options

HERE = Path(__file__).resolve().parent


def _microsim(**kwargs):
    """``policyengine_uk.Microsimulation`` on the verified pinned dataset,
    constructed the way ``pe.uk.managed_microsimulation`` does it."""
    from policyengine_uk import Microsimulation
    from policyengine_uk.data.dataset_schema import (
        UKMultiYearDataset,
        UKSingleYearDataset,
    )

    path = baseline.dataset_path()  # raises unless the SHA-256 matches the pin
    if UKMultiYearDataset.validate_file_path(path, False):
        dataset = UKMultiYearDataset(path)
    elif UKSingleYearDataset.validate_file_path(path, False):
        dataset = UKSingleYearDataset(path)
    else:
        dataset = path
    return Microsimulation(dataset=dataset, **kwargs)


def _build_simulation(reform: dict | None = None):
    return _microsim(reform=reform)


def _sim(year, elec, gas, params=None, extra_scenario=None):
    """Same as ``budget_options._sim`` with the managed constructor swapped out."""
    if extra_scenario is not None:
        sim = _microsim(scenario=extra_scenario)
    else:
        sim = _build_simulation(params or None)
    sim.set_input("electricity_consumption", year, elec)
    sim.set_input("gas_consumption", year, gas)
    sim.set_input("domestic_energy_consumption", year, elec + gas)
    return sim


# ``budget_options`` imported ``_build_simulation`` by name, so patch both.
baseline._build_simulation = _build_simulation
budget_options._build_simulation = _build_simulation
budget_options._sim = _sim


# Model variables the pipeline relies on: eligibility for the WHD proxy, the
# targeted discount and the Cost of Living Payment (means-tested benefits),
# the £400 credit, HBAI income and poverty, deciles, and weights.
HH_VARS = [
    "household_weight",
    "household_net_income",
    "hbai_household_net_income",
    "equiv_hbai_household_net_income",
    "household_income_decile",
    "electricity_consumption",
    "gas_consumption",
    "domestic_energy_consumption",
    "cost_of_living_support_payment",
    "energy_bills_rebate",
]
BENUNIT_VARS = [
    "universal_credit",
    "pension_credit",
    "housing_benefit",
    "esa_income",
    "jsa_income",
    "income_support",
    "working_tax_credit",
    "child_tax_credit",
    "tax_credits",
]
PERSON_VARS = [
    "in_relative_poverty_bhc",
    "in_relative_poverty_ahc",
    "in_poverty_bhc",
    "in_poverty_ahc",
]


def _vals(s):
    return np.asarray(s.values if hasattr(s, "values") else s, dtype=float)


def population_checks(sim, years=(2026, 2027)):
    """Weighted totals/caseloads of the model variables the pipeline uses."""
    out = {}
    for year in years:
        row = {}
        hw = _vals(sim.calculate("household_weight", year, unweighted=True))
        bw = _vals(
            sim.calculate("benunit_weight", year, unweighted=True)
        )
        pw = _vals(sim.calculate("person_weight", year, unweighted=True))
        row["households_m"] = float(hw.sum()) / 1e6
        row["benunits_m"] = float(bw.sum()) / 1e6
        row["persons_m"] = float(pw.sum()) / 1e6
        for v in HH_VARS[1:]:
            x = _vals(sim.calculate(v, year, unweighted=True))
            if v == "household_income_decile":
                row[v] = {
                    str(d): float(hw[x == d].sum()) / 1e6 for d in range(1, 11)
                }
                continue
            row[f"{v}_total_bn"] = float((x * hw).sum()) / 1e9
            row[f"{v}_mean"] = float((x * hw).sum() / hw.sum())
        for v in BENUNIT_VARS:
            x = _vals(sim.calculate(v, year, unweighted=True))
            row[f"{v}_total_bn"] = float((x * bw).sum()) / 1e9
            row[f"{v}_caseload_m"] = float(((x > 0) * bw).sum()) / 1e6
        age = _vals(sim.calculate("age", year, map_to="person", unweighted=True))
        for v in PERSON_VARS:
            # Household-level flags, mapped to people as in budget_options._poverty.
            x = _vals(sim.calculate(v, year, map_to="person", unweighted=True))
            row[f"{v}_rate_pct"] = float((x * pw).sum() / pw.sum()) * 100
            kids = age < 18
            row[f"{v}_child_rate_pct"] = (
                float((x * pw)[kids].sum() / pw[kids].sum()) * 100
            )
        out[str(year)] = row
    return out


def _write(results):
    out = HERE / f"out_uk_{version('policyengine-uk')}.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=1, default=float)
    return out


def main():
    t0 = time.time()
    data = baseline.run_baseline()
    results = budget_options.run_budget_options(data)
    results["provenance"] = {
        "harness": "validation/run_certified_pair.py",
        "constructor": "policyengine_uk.Microsimulation (direct, no policyengine.py)",
        "python": sys.version.split()[0],
        "policyengine_uk": version("policyengine-uk"),
        "policyengine_core": version("policyengine-core"),
        "numpy": version("numpy"),
        "pandas": version("pandas"),
        "dataset_path_sha256_verified": baseline.dataset_path() is not None,
        "dataset_release": baseline.DATASET_RELEASE,
        "dataset_revision": baseline.DATASET_REVISION,
        "dataset_sha256": baseline.DATASET_SHA256,
        "runtime_s": round(time.time() - t0, 1),
        "git_commit": git("rev-parse", "HEAD"),
        "git_dirty": bool(git("status", "--porcelain", "--untracked-files=no")),
        "source_sha256": source_hashes(),
    }
    _write(results)  # keep the pipeline outputs even if the checks below fail
    results["population_checks"] = population_checks(data["sim"])
    print(f"wrote {_write(results)}")


if __name__ == "__main__":
    main()
