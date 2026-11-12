"""Warm Home Discount top-up receipt rates (DESNZ IA para. 40; pe-uk#2616).

A passported household receives the top-up when its receipt draw is below its
group's rate: 85% with Pension Credit, 70% otherwise. Mirrors the YAML cases
in policyengine-uk#2616.
"""

from __future__ import annotations

import pytest
from policyengine_uk import Simulation

from energy_budget.budget_options import (
    WHD_RECEIPT_RATE_OTHER,
    WHD_RECEIPT_RATE_PENSION_CREDIT,
    WHD_TOP_UP,
    _policies,
    whd_scheme,
)
from energy_budget.reforms.targeted_energy_discount.presets import PRESETS
from energy_budget.reforms.targeted_energy_discount.reform import scenario

BENEFITS = (
    "pension_credit",
    "universal_credit",
    "housing_benefit",
    "esa_income",
    "jsa_income",
    "income_support",
)


def _situation(benefit, age=None, region="LONDON", child_age=None):
    if age is None:
        age = 70 if benefit == "pension_credit" else 40
    people = {"person": {"age": {"2026": age}}}
    if child_age is not None:
        people["child"] = {"age": {"2026": child_age}}
    members = list(people)
    return {
        "people": people,
        "benunits": {
            "benunit": {
                "members": members,
                **{b: {"2026": 1_000 if b == benefit else 0} for b in BENEFITS},
            }
        },
        "households": {"household": {"members": members, "region": region}},
    }


def _support(situation, sc, draw=None, engine_draw=None):
    # The reform's variables are installed by the scenario, after the
    # situation is parsed, so the draw is set as an input afterwards.
    sim = Simulation(scenario=sc, situation=situation)
    if draw is not None:
        sim.set_input("targeted_energy_discount_receipt_draw", 2026, [draw])
    if engine_draw is not None:
        sim.set_input("warm_home_discount_random_draw", 2026, [engine_draw])
    return float(sim.calculate("targeted_energy_discount", 2026)[0])


WHD = _policies(2026)["whd_top_up"]["scenario"]


def test_rates_match_desnz():
    assert WHD_RECEIPT_RATE_PENSION_CREDIT == 0.85
    assert WHD_RECEIPT_RATE_OTHER == 0.70


@pytest.mark.parametrize("year", [2026, 2027])
def test_scheme_rules_come_from_the_engine(year):
    rules = whd_scheme(year)
    # Eligibility statement for 2026-27 onwards: income-based JSA and Income
    # Support are no longer on the list.
    assert sorted(rules["qualifying_benefits"]) == sorted(
        ["pension_credit", "universal_credit", "housing_benefit", "esa_income"]
    )
    assert rules["receipt_rate_pension_credit"] == WHD_RECEIPT_RATE_PENSION_CREDIT
    assert rules["receipt_rate_other"] == WHD_RECEIPT_RATE_OTHER
    assert rules["rebate"] == 150


@pytest.mark.parametrize("benefit", ["jsa_income", "income_support"])
def test_benefits_off_the_list_do_not_qualify(benefit):
    assert _support(_situation(benefit), WHD) == 0


def test_draw_is_the_engines():
    # The top-up follows policyengine-uk's own receipt draw, so it reaches the
    # households that get the model's £150 rebate.
    assert _support(_situation("universal_credit"), WHD, engine_draw=0.69) == WHD_TOP_UP
    assert _support(_situation("universal_credit"), WHD, engine_draw=0.71) == 0


@pytest.mark.parametrize(
    ("benefit", "child_age", "paid"),
    [
        # Scotland's core group: Pension Credit is automatic.
        ("pension_credit", None, True),
        # Universal Credit alone (no disability element, no young child) is in
        # the broader group, which applies to a supplier: not modelled.
        ("universal_credit", None, False),
        ("housing_benefit", None, False),
        # A child under 5 with Universal Credit and no earnings is core group.
        ("universal_credit", 3, True),
        ("universal_credit", 7, False),
    ],
)
def test_scotland_core_group(benefit, child_age, paid):
    sit = _situation(benefit, region="SCOTLAND", child_age=child_age)
    assert _support(sit, WHD) == (WHD_TOP_UP if paid else 0)


@pytest.mark.parametrize(
    ("benefit", "draw", "paid"),
    [
        ("pension_credit", 0.84, True),
        ("pension_credit", 0.86, False),
        ("universal_credit", 0.69, True),
        ("universal_credit", 0.71, False),
        # Between the two rates: Pension Credit households receive it, others don't.
        ("universal_credit", 0.80, False),
        ("pension_credit", 0.80, True),
    ],
)
def test_receipt_by_group(benefit, draw, paid):
    assert _support(_situation(benefit), WHD, draw) == (WHD_TOP_UP if paid else 0)


def test_single_household_default_receives():
    # The draw defaults to 0 outside representative data, so calculators pay it.
    assert _support(_situation("universal_credit"), WHD) == WHD_TOP_UP


def test_rf_option_keeps_full_take_up():
    # Receipt rates default to 1, so the RF option still pays every passported
    # household, whatever its draw.
    rf = scenario(PRESETS["rf_flat"])
    assert _support(_situation("universal_credit"), rf, 0.99) == 175
