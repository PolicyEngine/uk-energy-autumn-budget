"""Shared baseline: run the microsimulation once, extract all household arrays.

Energy is electricity_consumption + gas_consumption. Each household's spend
is converted to annual kWh at the dataset's reference tariff (``KWH_BASIS``,
QEP FY2024-25 regional unit rate + fixed cost by default) and re-costed at
April-June 2026 Ofgem cap tariffs, the start of the analysis baseline.

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
    CONSUMPTION_PROFILE,
    DATASET_FILE,
    DATASET_RELEASE,
    DATASET_REPO,
    DATASET_REVISION,
    DATASET_SHA256,
    KWH_BASIS,
    REGION_TO_COUNTRY,
    TARIFFS,
    WINTER_SHARE,
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
        "kwh_basis": KWH_BASIS,
        "kwh_basis_source": (
            "Microcosm build stage price_domestic_energy: DESNZ QEP FY2024-25 "
            "regional unit cost + fixed cost, incl. VAT, all payment methods "
            "(PolicyEngine/microcosm#1113)"
        ),
        "consumption_profile": CONSUMPTION_PROFILE,
        "winter_share_oct_mar": dict(WINTER_SHARE),
        "tariff_coverage": (
            "All households on capped variable tariffs (Ofgem GB direct-debit "
            "averages); fixed tariffs, payment method and contract expiry not "
            "modelled. Northern Ireland on GB prices as a proxy."
        ),
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
    """Run baseline simulation and return dict of household-level arrays.

    ``elec`` and ``gas`` are each household's annual bill at April-June 2026
    tariffs for its kWh; ``elec_kwh``/``gas_kwh`` and ``has_elec``/
    ``has_gas`` carry the usage and connection used to cost every scenario.
    """
    from .bills import annual_bill, household_kwh

    sim = _build_simulation()

    region = _hh_array(sim, "region")
    region_str = pd.Series(region).astype(str).to_numpy()
    elec_spend = _hh_array(sim, "electricity_consumption")
    gas_spend = _hh_array(sim, "gas_consumption")
    elec_kwh, has_elec = household_kwh(elec_spend, region_str, "elec")
    gas_kwh, has_gas = household_kwh(gas_spend, region_str, "gas")
    elec = annual_bill(
        elec_kwh, has_elec, [TARIFFS["apr_jun_2026"]["elec"]] * 4, (0.25,) * 4
    )
    gas = annual_bill(
        gas_kwh, has_gas, [TARIFFS["apr_jun_2026"]["gas"]] * 4, (0.25,) * 4
    )
    energy = elec + gas

    income = _hh_array(sim, "household_net_income")
    weights = _weights(sim)
    decile = _hh_array(sim, "household_income_decile")
    tenure = _hh_array(sim, "tenure_type")
    accomm = _hh_array(sim, "accommodation_type")

    hh_type = _build_household_type(sim)

    country_arr = (
        pd.Series(region_str).map(REGION_TO_COUNTRY).fillna("UNKNOWN").to_numpy()
    )

    return {
        "sim": sim,
        "elec": elec,
        "gas": gas,
        "energy": energy,
        "elec_spend": elec_spend,
        "gas_spend": gas_spend,
        "elec_kwh": elec_kwh,
        "gas_kwh": gas_kwh,
        "has_elec": has_elec,
        "has_gas": has_gas,
        "income": income,
        "weights": weights,
        "decile": decile,
        "region": region,
        "tenure": tenure,
        "accomm": accomm,
        "hh_type": hh_type,
        "country": country_arr,
    }


def classify_household_types(
    household_ids, benunit_household_ids, family_types, person_household_ids, is_sp_age
):
    """Household type from the whole household, independent of row order.

    A household with more than one benefit unit is ``MULTI_UNIT`` (for
    example, adult children or sharers living with a family). A single-unit
    household takes its unit's family type, split by whether anyone in the
    household is at State Pension age:

    SINGLE -> SINGLE_PENSIONER / SINGLE_WORKING_AGE; COUPLE_NO_CHILDREN ->
    COUPLE_PENSIONER / COUPLE_NO_CHILDREN; COUPLE_WITH_CHILDREN and
    LONE_PARENT unchanged; anything else OTHER.
    """
    bu = pd.DataFrame(
        {
            "household_id": np.asarray(benunit_household_ids),
            "family_type": np.asarray(family_types).astype(str),
        }
    )
    grouped = bu.groupby("household_id")["family_type"]
    n_units = grouped.size()
    # With one unit, min == max == that unit's type, whatever the row order.
    only_ft = grouped.min().where(n_units == 1, "MULTI_UNIT")

    person = pd.DataFrame(
        {
            "household_id": np.asarray(person_household_ids),
            "is_sp": np.asarray(is_sp_age).astype(bool),
        }
    )
    any_sp = person.groupby("household_id")["is_sp"].any()

    hh = pd.Series(np.asarray(household_ids))
    ft = hh.map(only_ft).fillna("UNKNOWN").astype(str).to_numpy()
    is_pen = hh.map(any_sp).fillna(False).astype(bool).to_numpy()

    categories = np.full(len(hh), "OTHER", dtype=object)
    categories[(ft == "SINGLE") & is_pen] = "SINGLE_PENSIONER"
    categories[(ft == "COUPLE_NO_CHILDREN") & is_pen] = "COUPLE_PENSIONER"
    categories[(ft == "SINGLE") & ~is_pen] = "SINGLE_WORKING_AGE"
    categories[(ft == "COUPLE_NO_CHILDREN") & ~is_pen] = "COUPLE_NO_CHILDREN"
    categories[ft == "COUPLE_WITH_CHILDREN"] = "COUPLE_WITH_CHILDREN"
    categories[ft == "LONE_PARENT"] = "LONE_PARENT"
    categories[ft == "MULTI_UNIT"] = "MULTI_UNIT"
    return categories.astype(str)


def benunit_households(benunit_ids, person_benunit_ids, person_household_ids):
    """Household of each benefit unit, from the person table.

    ``sim.calculate("household_id", map_to="benunit")`` does not return the
    household of each unit on this dataset (it averages person values, giving
    ids such as 1.5), so the link is taken from persons, who each carry both
    ids.
    """
    link = (
        pd.DataFrame(
            {
                "benunit_id": np.asarray(person_benunit_ids),
                "household_id": np.asarray(person_household_ids),
            }
        )
        .drop_duplicates("benunit_id")
        .set_index("benunit_id")["household_id"]
    )
    return pd.Series(np.asarray(benunit_ids)).map(link).to_numpy()


def _build_household_type(sim) -> np.ndarray:
    """Household type for every household in the simulation's row order."""
    person_hh = _person_array(sim, "household_id")
    return classify_household_types(
        _hh_array(sim, "household_id"),
        benunit_households(
            _benunit_array(sim, "benunit_id"),
            _person_array(sim, "benunit_id"),
            person_hh,
        ),
        _benunit_array(sim, "family_type"),
        person_hh,
        _person_array(sim, "is_SP_age"),
    )


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
        "elec_spend",
        "gas_spend",
        "elec_kwh",
        "gas_kwh",
        "has_elec",
        "has_gas",
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
