"""Variables for the targeted energy discount.

The discount is household-level: energy is billed per meter, which usually means per
household (RF, "Billing me softly", p. 6). A household is eligible if it receives a
passporting benefit or if its highest-income member passes the income test. Support
then follows a schedule by the household's assessed income.
"""

from policyengine_uk.model_api import *
from policyengine_uk.variables.gov.gov_spending import (
    gov_spending as _baseline_gov_spending,
)
from policyengine_uk.variables.household.income.hbai_household_net_income import (
    hbai_household_net_income as _baseline_hbai_household_net_income,
)
from policyengine_uk.variables.household.income.household_benefits import (
    household_benefits as _baseline_household_benefits,
)

PARAMETER_PATH = "gov.contrib.targeted_energy_discount"


def _params(period, parameters):
    return parameters(period).gov.contrib.targeted_energy_discount


def _schedule(p, income, bill):
    """Support due at an assessed income, in pounds per household."""
    if p.bill_share.in_effect:
        return p.bill_share.rate.calc(income) * bill
    return p.amount.calc(income)


def _schedule_pays(p, income):
    """Whether the schedule pays anything at this assessed income."""
    if p.bill_share.in_effect:
        return p.bill_share.rate.calc(income) > 0
    return p.amount.calc(income) > 0


class claims_targeted_energy_discount(Variable):
    label = "Claims the targeted energy discount if eligible through the income test"
    documentation = (
        "Households eligible only through the income test must self-declare (RF p. 10). "
        "This is an input so take-up draws are made at data-construction time; "
        "passported households are enrolled automatically."
    )
    entity = Household
    definition_period = YEAR
    value_type = bool
    default_value = True


class targeted_energy_discount_bill(Variable):
    label = "Annual gas and electricity bill for the targeted energy discount"
    entity = Household
    definition_period = YEAR
    value_type = float
    unit = GBP
    adds = ["electricity_consumption", "gas_consumption"]  # noqa: RUF012


class targeted_energy_discount_person_income(Variable):
    label = "Individual income assessed by the targeted energy discount income test"
    documentation = (
        "Floored at zero: a person's taxable income cannot be negative, and one "
        "member's loss does not reduce another's income in the household test "
        "(the dashboard calculator does the same)."
    )
    entity = Person
    definition_period = YEAR
    value_type = float
    unit = GBP

    def formula(person, period, parameters):
        p = _params(period, parameters)
        return max_(add(person, period, p.income_test.sources), 0)


class targeted_energy_discount_highest_income(Variable):
    label = "Highest individual income in the household (targeted energy discount)"
    entity = Household
    definition_period = YEAR
    value_type = float
    unit = GBP

    def formula(household, period, parameters):
        income = household.members("targeted_energy_discount_person_income", period)
        return household.max(income)


class targeted_energy_discount_tested_income(Variable):
    label = "Income tested by the targeted energy discount"
    documentation = (
        "The highest individual income in the household, or, when the income test is "
        "household-based, total household income divided by the BHC equivalisation "
        "factor (the modified OECD scale RF uses for its household-income option)."
    )
    entity = Household
    definition_period = YEAR
    value_type = float
    unit = GBP

    def formula(household, period, parameters):
        p = _params(period, parameters)
        if p.income_test.household_equivalised:
            income = household.members("targeted_energy_discount_person_income", period)
            return household.sum(income) / household(
                "household_equivalisation_bhc", period
            )
        return household("targeted_energy_discount_highest_income", period)


class targeted_energy_discount_passported(Variable):
    label = (
        "Household receives a benefit that passports it to the targeted energy discount"
    )
    entity = Household
    definition_period = YEAR
    value_type = bool

    def formula(household, period, parameters):
        p = _params(period, parameters).passport
        if not p.in_effect:
            return household.empty_array() > 0
        return add(household, period, p.benefits) > 0


class targeted_energy_discount_assessed_income(Variable):
    label = "Income at which the household is placed on the targeted energy discount schedule"
    entity = Household
    definition_period = YEAR
    value_type = float
    unit = GBP

    def formula(household, period, parameters):
        p = _params(period, parameters)
        tested = household("targeted_energy_discount_tested_income", period)
        passported = household("targeted_energy_discount_passported", period)
        return where(passported, min_(tested, p.passport.assessed_income), tested)


class targeted_energy_discount_income_route(Variable):
    label = "Household passes the targeted energy discount income test"
    entity = Household
    definition_period = YEAR
    value_type = bool

    def formula(household, period, parameters):
        p = _params(period, parameters)
        if not p.income_test.in_effect:
            return household.empty_array() > 0
        tested = household("targeted_energy_discount_tested_income", period)
        return _schedule_pays(p, tested)


class targeted_energy_discount_eligible(Variable):
    label = "Household is eligible for the targeted energy discount"
    entity = Household
    definition_period = YEAR
    value_type = bool

    def formula(household, period, parameters):
        p = _params(period, parameters)
        if not p.in_effect:
            return household.empty_array() > 0
        region = household("region", period)
        in_scope = (
            region != region.possible_values.NORTHERN_IRELAND
            if p.gb_only
            else household.empty_array() == 0
        )
        passported = household("targeted_energy_discount_passported", period)
        income_route = household("targeted_energy_discount_income_route", period)
        return in_scope & (passported | income_route)


class targeted_energy_discount(Variable):
    label = "Targeted energy discount"
    documentation = (
        "Support under the targeted energy discount, in pounds per household for the "
        "scheme period."
    )
    entity = Household
    definition_period = YEAR
    value_type = float
    unit = GBP

    def formula(household, period, parameters):
        p = _params(period, parameters)
        eligible = household("targeted_energy_discount_eligible", period)
        passported = household("targeted_energy_discount_passported", period)
        claims = household("claims_targeted_energy_discount", period)
        income = household("targeted_energy_discount_assessed_income", period)
        bill = household("targeted_energy_discount_bill", period)
        support = _schedule(p, income, bill)
        return where(eligible & (passported | claims), support, 0)


class household_benefits(_baseline_household_benefits):
    def formula(household, period, parameters):
        return _baseline_household_benefits.formula(
            household, period, parameters
        ) + household("targeted_energy_discount", period)


class gov_spending(_baseline_gov_spending):
    def formula(household, period, parameters):
        return _baseline_gov_spending.formula(
            household, period, parameters
        ) + household("targeted_energy_discount", period)


class hbai_household_net_income(_baseline_hbai_household_net_income):
    def formula(household, period, parameters):
        base = _baseline_hbai_household_net_income.formula(
            household, period, parameters
        )
        if not _params(period, parameters).count_in_hbai_income:
            return base
        return base + household("targeted_energy_discount", period)


NEW_VARIABLES = [
    claims_targeted_energy_discount,
    targeted_energy_discount_bill,
    targeted_energy_discount_person_income,
    targeted_energy_discount_highest_income,
    targeted_energy_discount_tested_income,
    targeted_energy_discount_passported,
    targeted_energy_discount_assessed_income,
    targeted_energy_discount_income_route,
    targeted_energy_discount_eligible,
    targeted_energy_discount,
]

UPDATED_VARIABLES = [household_benefits, gov_spending, hbai_household_net_income]
