"""Named parameter settings for the targeted energy discount.

Amounts are RF's published averages for a 2 billion GBP scheme ("Billing me softly",
p. 9): a flat 175 GBP for households whose highest individual income is below
24,000 GBP, or a tiered 220 GBP below 18,000 GBP and 85 GBP from 18,000 GBP to
24,000 GBP. RF's scheme cuts unit prices, so these are averages; the analysis layer can
turn them into a bill-share discount (``calibrate.bill_share_changes``) or rescale them
to a budget (``calibrate.budget_changes``).
"""

P = "gov.contrib.targeted_energy_discount"

RF_FLAT = {
    f"{P}.in_effect": True,
    f"{P}.amount[0].amount": 175,
    f"{P}.amount[1].amount": 175,
    f"{P}.amount[2].threshold": 24_000,
}

RF_TIERED = {
    f"{P}.in_effect": True,
    f"{P}.amount[0].amount": 220,
    f"{P}.amount[1].threshold": 18_000,
    f"{P}.amount[1].amount": 85,
    f"{P}.amount[2].threshold": 24_000,
}

# RF does not say which tier passported households get. RF_TIERED places them all in
# the top tier; this variant tiers them on their own income, with 85 GBP as the floor.
RF_TIERED_OWN_INCOME = {
    **RF_TIERED,
    f"{P}.passport.assessed_income": 23_999,
}

# RF's comparator: equivalised total household income below 30,000 GBP (Figure 3).
RF_HOUSEHOLD_INCOME = {
    **RF_FLAT,
    f"{P}.income_test.household_equivalised": True,
    f"{P}.amount[2].threshold": 30_000,
}

# Warm-Home-Discount-style comparator: passporting only, flat 175 GBP.
PASSPORT_ONLY = {
    f"{P}.in_effect": True,
    f"{P}.income_test.in_effect": False,
}

PRESETS = {
    "rf_flat": RF_FLAT,
    "rf_tiered": RF_TIERED,
    "rf_tiered_own_income": RF_TIERED_OWN_INCOME,
    "rf_household_income": RF_HOUSEHOLD_INCOME,
    "passport_only": PASSPORT_ONLY,
}

DESCRIPTIONS = {
    "rf_flat": "RF flat option: 175 GBP per household below 24,000 GBP or passported",
    "rf_tiered": (
        "RF tiered option: 220 GBP below 18,000 GBP (and passported), "
        "85 GBP from 18,000 GBP to 24,000 GBP"
    ),
    "rf_tiered_own_income": (
        "RF tiered option with passported households tiered on their own income "
        "(85 GBP floor)"
    ),
    "rf_household_income": (
        "RF comparator: 175 GBP per household with equivalised household income below "
        "30,000 GBP, or passported"
    ),
    "passport_only": "Passporting only (no income test), 175 GBP per household",
}


def preset(name: str) -> dict:
    """A copy of a named preset's parameter changes."""
    try:
        return dict(PRESETS[name])
    except KeyError:
        raise KeyError(f"Unknown preset {name!r}; choose from {sorted(PRESETS)}")
