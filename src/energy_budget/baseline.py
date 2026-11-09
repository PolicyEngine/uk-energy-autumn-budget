"""Shared baseline: run the microsimulation once, extract all household arrays.

Runs on the certified Microcosm UK national dataset through
``policyengine.py``'s managed ``pe.uk.managed_microsimulation`` with no
dataset argument, so the bundle chooses and verifies the file. Each
household's annual electricity and gas kWh are read from that same file's
``electricity_kwh`` / ``gas_kwh`` export (they are not model variables) and
aligned to the simulation by ``household_id``.
"""

from __future__ import annotations

import hashlib
import os

import numpy as np
import pandas as pd

# ``policyengine`` pulls the whole UK tax-benefit system at import, so it
# is imported inside the simulation functions. That keeps the pure helpers
# (``weighted_mean``, ``decile_means``, ``filter_by_country``) cheap to
# import for the unit tests.
from .config import (
    BASELINE_LAW,
    CONSUMPTION_PROFILE,
    DATASET_ENERGY_LEVELS,
    DATASET_PRICE_BASIS,
    DATASET_YEAR,
    REGION_TO_COUNTRY,
    TARIFFS,
    WINTER_SHARE,
    YEAR,
)

ENERGY_COLUMNS = [
    "household_id",
    "region",
    "electricity_kwh",
    "gas_kwh",
    "electricity_consumption",
    "gas_consumption",
]


def _ensure_hf_token():
    """Expose the saved Hugging Face login to policyengine.py's downloader.

    The token is read from huggingface_hub's store and placed in the process
    environment only; it is never printed or written.
    """
    if os.environ.get("HUGGING_FACE_TOKEN"):
        return
    try:
        from huggingface_hub import get_token
    except ImportError:
        return
    token = get_token()
    if token:
        os.environ["HUGGING_FACE_TOKEN"] = token


def _build_simulation(reform: dict | None = None, scenario=None):
    """A managed ``policyengine_uk`` Microsimulation on the certified dataset.

    Reform dicts use the country package's parameter paths and date-keyed
    values; ``scenario`` is a policyengine-uk ``Scenario``.
    """
    import policyengine as pe

    _ensure_hf_token()
    kwargs = {}
    if reform:
        kwargs["reform"] = reform
    if scenario is not None:
        kwargs["scenario"] = scenario
    return pe.uk.managed_microsimulation(**kwargs)


def _sha256(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dataset_file(sim) -> str:
    """Local path of the certified dataset, verified against the bundle."""
    bundle = sim.policyengine_bundle
    path = bundle["runtime_dataset_source"]
    expected = bundle.get("runtime_dataset_sha256")
    certified = bundle.get("certified_data_artifact_sha256")
    if not expected or expected != certified or _sha256(path) != expected:
        raise RuntimeError(f"{path} does not match the certified SHA-256")
    return path


def read_energy_export(path, household_ids) -> pd.DataFrame:
    """The dataset's annual kWh and spending, in the simulation's row order.

    Raises if household ids are not unique or the dataset and simulation do
    not hold exactly the same households.
    """
    table = pd.read_hdf(path, "household", columns=ENERGY_COLUMNS)
    ids = np.asarray(household_ids)
    if table["household_id"].duplicated().any() or len(set(ids)) != len(ids):
        raise ValueError("household_id is not unique")
    if len(table) != len(ids) or set(table["household_id"]) != set(ids):
        raise ValueError("dataset and simulation hold different households")
    out = table.set_index("household_id").loc[ids].reset_index()
    for col in ENERGY_COLUMNS[2:]:
        values = out[col].to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values < 0).any():
            raise ValueError(f"{col} has missing or negative values")
    return out


def provenance(sim) -> dict:
    """Engine and data versions to record alongside the results."""
    bundle = getattr(sim, "policyengine_bundle", {})
    return {
        "policyengine_version": bundle.get("policyengine_version"),
        "bundle_id": bundle.get("bundle_id"),
        "model_version": bundle.get("model_version"),
        "dataset": bundle.get("runtime_dataset"),
        "dataset_uri": bundle.get("runtime_dataset_uri"),
        "dataset_revision": bundle.get("runtime_dataset_revision"),
        "dataset_sha256": bundle.get("runtime_dataset_sha256"),
        "dataset_build_id": bundle.get("certified_data_build_id"),
        "certified_dataset_sha256": bundle.get("certified_data_artifact_sha256"),
        "managed": bundle.get("managed_by") == "policyengine.py",
        "dataset_year": DATASET_YEAR,
        "kwh_source": "dataset export: household electricity_kwh and gas_kwh (annual, calendar 2024)",
        "expenditure_price_basis": DATASET_PRICE_BASIS,
        "dataset_energy_levels": DATASET_ENERGY_LEVELS,
        "baseline_policy": BASELINE_LAW,
        "consumption_profile": CONSUMPTION_PROFILE,
        "winter_share_oct_mar": dict(WINTER_SHARE),
        "tariff_coverage": (
            "All households on capped variable tariffs (Ofgem GB direct-debit "
            "averages); fixed tariffs, payment method and contract expiry not "
            "modelled. Northern Ireland on GB prices as a proxy."
        ),
    }


def _hh_array(sim, var: str, year: int = YEAR) -> np.ndarray:
    """Pull a household-level variable as a numpy array."""
    series = sim.calculate(var, year)
    return series.values if hasattr(series, "values") else np.asarray(series)


def _person_array(sim, var: str) -> np.ndarray:
    series = sim.calculate(var, YEAR, map_to="person")
    return series.values if hasattr(series, "values") else np.asarray(series)


def _benunit_array(sim, var: str) -> np.ndarray:
    series = sim.calculate(var, YEAR, map_to="benunit")
    return series.values if hasattr(series, "values") else np.asarray(series)


def _weights(sim, year: int = YEAR) -> np.ndarray:
    """Household weights as a raw numpy array (skip the MicroSeries)."""
    series = sim.calculate("household_weight", year, unweighted=True)
    return series.values if hasattr(series, "values") else np.asarray(series)


def run_baseline():
    """Run the baseline simulation and return household-level arrays.

    ``elec`` and ``gas`` are each household's annual bill at April-June 2026
    tariffs for its kWh; ``elec_kwh``/``gas_kwh`` and ``has_elec``/
    ``has_gas`` carry the usage and connection used to cost every scenario.
    """
    from .bills import annual_bill, connections

    sim = _build_simulation()
    path = dataset_file(sim)
    household_id = _hh_array(sim, "household_id")
    energy = read_energy_export(path, household_id)

    region = _hh_array(sim, "region")
    region_str = pd.Series(region).astype(str).to_numpy()
    if not (energy["region"].astype(str).to_numpy() == region_str).all():
        raise ValueError("dataset and simulation regions disagree")
    elec_spend = energy["electricity_consumption"].to_numpy(dtype=float)
    gas_spend = energy["gas_consumption"].to_numpy(dtype=float)
    elec_kwh = energy["electricity_kwh"].to_numpy(dtype=float)
    gas_kwh = energy["gas_kwh"].to_numpy(dtype=float)
    connected = connections(elec_spend, gas_spend)
    held = {f: [TARIFFS["apr_jun_2026"][f]] * 4 for f in ("elec", "gas")}
    elec = annual_bill(elec_kwh, connected["elec"], held["elec"], (0.25,) * 4)
    gas = annual_bill(gas_kwh, connected["gas"], held["gas"], (0.25,) * 4)

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
        "dataset_path": path,
        "household_id": household_id,
        "elec": elec,
        "gas": gas,
        "energy": elec + gas,
        "elec_spend": elec_spend,
        "gas_spend": gas_spend,
        "elec_kwh": elec_kwh,
        "gas_kwh": gas_kwh,
        "has_elec": connected["elec"],
        "has_gas": connected["gas"],
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
