"""Household type is order-independent and flags multi-unit households (A2)."""

from __future__ import annotations

import numpy as np

from energy_budget.baseline import classify_household_types

# Household 1: two single working-age units (sharers).
# Household 2: a single adult and a couple with children.
# Household 3: one pensioner couple. Household 4: one lone parent.
BU_HH = [1, 1, 2, 2, 3, 4]
FAMILY = [
    "SINGLE",
    "SINGLE",
    "SINGLE",
    "COUPLE_WITH_CHILDREN",
    "COUPLE_NO_CHILDREN",
    "LONE_PARENT",
]
PERSON_HH = [1, 1, 2, 2, 2, 2, 3, 3, 4, 4]
IS_SP = [False] * 6 + [True, False, False, False]
HH = [1, 2, 3, 4]
EXPECTED = ["MULTI_UNIT", "MULTI_UNIT", "COUPLE_PENSIONER", "LONE_PARENT"]


def test_classification():
    out = classify_household_types(HH, BU_HH, FAMILY, PERSON_HH, IS_SP)
    assert list(out) == EXPECTED


def test_order_independent():
    rng = np.random.default_rng(0)
    for _ in range(20):
        b = rng.permutation(len(BU_HH))
        p = rng.permutation(len(PERSON_HH))
        out = classify_household_types(
            HH,
            np.array(BU_HH)[b],
            np.array(FAMILY)[b],
            np.array(PERSON_HH)[p],
            np.array(IS_SP)[p],
        )
        assert list(out) == EXPECTED


def test_household_order_follows_input():
    out = classify_household_types([4, 3], BU_HH, FAMILY, PERSON_HH, IS_SP)
    assert list(out) == ["LONE_PARENT", "COUPLE_PENSIONER"]


def test_single_unit_types_unchanged():
    out = classify_household_types(
        [1, 2, 3],
        [1, 2, 3],
        ["SINGLE", "SINGLE", "COUPLE_NO_CHILDREN"],
        [1, 2, 3, 3],
        [True, False, False, False],
    )
    assert list(out) == ["SINGLE_PENSIONER", "SINGLE_WORKING_AGE", "COUPLE_NO_CHILDREN"]


def test_benunit_households_from_persons():
    from energy_budget.baseline import benunit_households

    out = benunit_households(
        [301, 101, 302], [101, 201, 201, 301, 302], [1, 2, 2, 3, 3]
    )
    assert list(out) == [3, 1, 3]
