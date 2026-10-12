"""Shared baseline: run the microsimulation once, extract all household arrays.

Energy is defined as electricity_consumption + gas_consumption throughout,
rebased from the dataset's CY2025 prices to April-June 2026 prices
(``PRICE_REBASE``).

Runs on Microcosm UK through ``policyengine.py``'s managed
``pe.uk.managed_microsimulation``. The dataset is outside the release
bundle, so it is passed with ``allow_unmanaged=True`` and pinned by
revision and SHA-256 here.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache

import numpy as np
import pandas as pd

# ``policyengine`` pulls the whole UK tax-benefit system at import, so it
# is imported inside the simulation functions. That keeps the pure helpers
# (``weighted_mean``, ``decile_means``, ``filter_by_country``) cheap to
# import for the unit tests.
from .config import (
    DATASET_FILE,
    DATASET_RELEASE,
    DATASET_REPO,
    DATASET_REVISION,
    DATASET_SHA256,
    PRICE_REBASE,
    REGION_TO_COUNTRY,
    YEAR,
)


@lru_cache(maxsize=1)
def dataset_path() -> str:
    """Local path of the pinned Microcosm file, verified by SHA-256."""
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(
        DATASET_REPO, DATASET_FILE, repo_type="dataset", revision=DATASET_REVISION
    )
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    if digest.hexdigest() != DATASET_SHA256:
        raise RuntimeError(f"{DATASET_FILE} does not match the pinned SHA-256")
    return path


def _build_simulation(reform: dict | None = None):
    """Construct a managed ``policyengine_uk`` Microsimulation on Microcosm.

    Reform dicts use the country package's parameter paths and date-keyed
    values.
    """
    import policyengine as pe

    return pe.uk.managed_microsimulation(
        dataset=dataset_path(), allow_unmanaged=True, reform=reform
    )


def provenance(sim) -> dict:
    """Engine and data versions to record alongside the results."""
    bundle = getattr(sim, "policyengine_bundle", {})
    return {
        "policyengine_version": bundle.get("policyengine_version"),
        "bundle_id": bundle.get("bundle_id"),
        "model_version": bundle.get("model_version"),
        "dataset": DATASET_FILE,
        "dataset_repo": DATASET_REPO,
        "dataset_release": DATASET_RELEASE,
        "dataset_revision": DATASET_REVISION,
        "dataset_sha256": DATASET_SHA256,
        "managed": False,
        "price_rebase_cy2025_to_apr_jun_2026": {
            k: round(v, 4) for k, v in PRICE_REBASE.items()
        },
    }


def _hh_array(sim, var: str) -> np.ndarray:
    """Pull a household-level variable as a numpy array."""
    series = sim.calculate(var, YEAR)
    return series.values if hasattr(series, "values") else np.asarray(series)


def _person_array(sim, var: str) -> np.ndarray:
    series = sim.calculate(var, YEAR, map_to="person")
    return series.values if hasattr(series, "values") else np.asarray(series)


def _benunit_array(sim, var: str) -> np.ndarray:
    series = sim.calculate(var, YEAR, map_to="benunit")
    return series.values if hasattr(series, "values") else np.asarray(series)


def _weights(sim) -> np.ndarray:
    """Household weights as a raw numpy array (skip the MicroSeries)."""
    series = sim.calculate("household_weight", YEAR, unweighted=True)
    return series.values if hasattr(series, "values") else np.asarray(series)


def run_baseline():
    """Run baseline simulation and return dict of household-level arrays."""
    sim = _build_simulation()

    elec = _hh_array(sim, "electricity_consumption") * PRICE_REBASE["elec"]
    gas = _hh_array(sim, "gas_consumption") * PRICE_REBASE["gas"]
    energy = elec + gas

    income = _hh_array(sim, "household_net_income")
    weights = _weights(sim)
    decile = _hh_array(sim, "household_income_decile")
    region = _hh_array(sim, "region")
    tenure = _hh_array(sim, "tenure_type")
    accomm = _hh_array(sim, "accommodation_type")

    hh_type = _build_household_type(sim)

    country_arr = (
        pd.Series(region)
        .astype(str)
        .map(REGION_TO_COUNTRY)
        .fillna("UNKNOWN")
        .to_numpy()
    )

    return {
        "sim": sim,
        "elec": elec,
        "gas": gas,
        "energy": energy,
        "income": income,
        "weights": weights,
        "decile": decile,
        "region": region,
        "tenure": tenure,
        "accomm": accomm,
        "hh_type": hh_type,
        "country": country_arr,
    }


def _build_household_type(sim) -> np.ndarray:
    """Classify each household into type based on family_type + pensioner status.

    ``family_type`` is held at benunit level; ``is_SP_age`` at person
    level. Aggregate both up to the household via pandas groupby, keeping
    the household frame's row order.
    """
    hh_ids = _hh_array(sim, "household_id")

    # First benunit's family_type per household.
    bu_frame = pd.DataFrame(
        {
            "household_id": _benunit_array(sim, "household_id"),
            "family_type": _benunit_array(sim, "family_type").astype(str),
        }
    )
    first_ft = bu_frame.groupby("household_id")["family_type"].first()

    # Any person at SP age → pensioner household.
    person_frame = pd.DataFrame(
        {
            "household_id": _person_array(sim, "household_id"),
            "is_sp": _person_array(sim, "is_SP_age").astype(bool),
        }
    )
    any_sp = person_frame.groupby("household_id")["is_sp"].any()

    ft = pd.Series(hh_ids).map(first_ft).fillna("UNKNOWN").astype(str).to_numpy()
    is_pen = pd.Series(hh_ids).map(any_sp).fillna(False).astype(bool).to_numpy()

    categories = np.full(len(hh_ids), "OTHER", dtype=object)
    categories[(ft == "SINGLE") & is_pen] = "SINGLE_PENSIONER"
    categories[(ft == "COUPLE_NO_CHILDREN") & is_pen] = "COUPLE_PENSIONER"
    categories[(ft == "SINGLE") & ~is_pen] = "SINGLE_WORKING_AGE"
    categories[(ft == "COUPLE_NO_CHILDREN") & ~is_pen] = "COUPLE_NO_CHILDREN"
    categories[ft == "COUPLE_WITH_CHILDREN"] = "COUPLE_WITH_CHILDREN"
    categories[ft == "LONE_PARENT"] = "LONE_PARENT"
    return categories.astype(str)


def build_reform_simulation(reform: dict):
    """Construct a reformed Simulation. Reform dict uses the same parameter
    paths and date-keyed values as the raw ``policyengine-uk`` reforms.

    Example:

    .. code-block:: python

        sim = build_reform_simulation({
            "gov.ofgem.energy_price_cap": {"2026-01-01": 2625},
        })
    """
    return _build_simulation(reform=reform)


def filter_by_country(data, country):
    """Filter all household arrays to a single country/nation.

    country: "UK" (no filter), "ENGLAND", "SCOTLAND", "WALES", "NORTHERN_IRELAND"
    Returns a new data dict with filtered arrays, a ``country_mask`` key
    containing the boolean mask against the original arrays, and a
    ``country_label`` string naming the filter.

    ``data["country"]`` stays a per-household array so downstream
    groupby / masking by country works the same shape in filtered and
    unfiltered data dicts.
    """
    country = country.upper()
    if country == "UK":
        mask = np.ones(len(data["weights"]), dtype=bool)
        return {**data, "country_mask": mask, "country_label": country}

    hh_country = (
        pd.Series(data["region"])
        .astype(str)
        .map(REGION_TO_COUNTRY)
        .fillna("")
        .to_numpy()
    )
    mask = hh_country == country

    filtered = {
        "sim": data["sim"],  # keep original sim for policy reform lookups
        "country_mask": mask,
        "country_label": country,
    }
    for key in (
        "elec",
        "gas",
        "energy",
        "income",
        "weights",
        "decile",
        "region",
        "tenure",
        "accomm",
        "hh_type",
        "country",
    ):
        filtered[key] = data[key][mask]
    return filtered


def weighted_mean(values, weights, mask=None):
    """Weighted average, optionally filtered by boolean mask."""
    if mask is not None:
        values = values[mask]
        weights = weights[mask]
    if weights.sum() == 0:
        return 0
    return float(np.average(values, weights=weights))


def decile_means(data, var_key):
    """Return dict {1: mean, 2: mean, ...} for a variable by income decile."""
    out = {}
    for d in range(1, 11):
        mask = data["decile"] == d
        out[d] = weighted_mean(data[var_key], data["weights"], mask)
    return out
