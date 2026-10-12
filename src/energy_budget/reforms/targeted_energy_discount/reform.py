"""Attach the targeted energy discount to a policyengine-uk tax-benefit system."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from policyengine_core.parameters.helpers import load_parameter_file
from policyengine_core.periods import instant, period
from policyengine_uk.utils.scenario import Scenario

from energy_budget.reforms.targeted_energy_discount.variables import (
    NEW_VARIABLES,
    PARAMETER_PATH,
    UPDATED_VARIABLES,
)

PARAMETERS_FILE = Path(__file__).with_name("parameters.yaml")
DEFAULT_START = "2000-01-01"

ParameterChanges = Mapping[str, Any]


def install(tax_benefit_system) -> None:
    """Add the discount's parameters and variables to ``tax_benefit_system``.

    With the default parameters (``in_effect`` false) the system is numerically the
    policyengine-uk baseline.
    """
    contrib = tax_benefit_system.parameters.gov.contrib
    if "targeted_energy_discount" not in contrib.children:
        node = load_parameter_file(str(PARAMETERS_FILE), name=PARAMETER_PATH)
        contrib.add_child("targeted_energy_discount", node)
    for variable in NEW_VARIABLES:
        if variable.__name__ not in tax_benefit_system.variables:
            tax_benefit_system.add_variable(variable)
    for variable in UPDATED_VARIABLES:
        tax_benefit_system.update_variable(variable)


def apply_parameter_changes(parameters, changes: ParameterChanges | None) -> None:
    """Apply ``{path: value}`` or ``{path: {period_key: value}}`` changes.

    A bare value applies from 2000-01-01 onwards. Period keys follow policyengine-uk's
    reform dicts: ``"YYYY-MM-DD.YYYY-MM-DD"`` for a date range, or a period string such
    as ``"2026"``. Paths accept bracket indices, e.g. ``...amount[1].amount``.
    """
    for path, value in (changes or {}).items():
        node = parameters.get_child(path)
        if isinstance(value, Mapping):
            for period_key, period_value in value.items():
                if "." in str(period_key):
                    start, stop = str(period_key).split(".")
                    node.update(
                        start=instant(start), stop=instant(stop), value=period_value
                    )
                else:
                    node.update(period=period(str(period_key)), value=period_value)
        else:
            node.update(start=instant(DEFAULT_START), value=value)


def scenario(changes: ParameterChanges | None = None) -> Scenario:
    """A policyengine-uk Scenario that installs the discount and applies ``changes``.

    Pass the result as ``Microsimulation(scenario=..., dataset=...)`` or
    ``Simulation(scenario=..., situation=...)``.
    """

    def modifier(simulation) -> None:
        tbs = simulation.tax_benefit_system
        install(tbs)
        apply_parameter_changes(tbs.parameters, changes)
        tbs.reset_parameter_caches()

    return Scenario(simulation_modifier=modifier, applied_before_data_load=True)
