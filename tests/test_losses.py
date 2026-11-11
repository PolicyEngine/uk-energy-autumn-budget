"""Remaining losses after support (issue #11, section B): data-free checks."""

import numpy as np
import pytest

from energy_budget.bills import annual_bill
from energy_budget.config import quarter_shares
from energy_budget.losses import (
    MIN_RECORDS,
    energy_cost_share,
    loss_bands,
    quarter_bill,
    remaining_losses,
    summarise_losses,
    tenure_group,
    use_quintiles,
    weighted_quantile,
)
from energy_budget.prices import HELD_QUARTERS, year_quarters


def test_weighted_quantile():
    v = np.array([1.0, 2.0, 3.0, 4.0])
    assert weighted_quantile(v, np.ones(4), 0.5) == 2.0
    # A heavy weight on 4 moves the median there.
    assert weighted_quantile(v, np.array([1, 1, 1, 10]), 0.5) == 4.0
    assert weighted_quantile(v, np.array([0, 0, 1, 0]), 0.5) == 3.0


@pytest.mark.parametrize("fuel", ["elec", "gas"])
@pytest.mark.parametrize("year", [2026, 2027])
def test_quarters_sum_to_annual_bill(fuel, year):
    kwh = np.array([0.0, 2_700.0, 11_500.0])
    connected = np.array([True, True, False])
    quarters = year_quarters(year)[fuel]
    shares = quarter_shares(fuel)
    parts = sum(quarter_bill(kwh, connected, q, s) for q, s in zip(quarters, shares))
    assert parts == pytest.approx(annual_bill(kwh, connected, quarters, shares))


def test_jan_mar_reference_is_seasonal_share_of_held_rates():
    unit, standing = HELD_QUARTERS["gas"][3]
    share = quarter_shares("gas")[3]
    bill = quarter_bill(np.array([10_000.0]), np.array([True]), (unit, standing), share)
    assert bill[0] == pytest.approx((unit * share * 10_000 + standing * 365 / 4) / 100)


def test_cash_and_bill_cuts_count_alike():
    bill = np.array([2_000.0, 2_000.0])
    income = np.array([20_000.0, 20_000.0])
    # A £100 payment (in income) and a £100 bill cut give the same share.
    cash, _ = energy_cost_share(bill, np.array([100.0, 0]), income + [100, 0], [100, 0])
    cut, _ = energy_cost_share(bill - [0, 100], np.zeros(2), income, np.zeros(2))
    assert cash[0] == pytest.approx(cut[1]) == pytest.approx(1_900 / 20_000)


def test_non_positive_income_has_no_share():
    share, defined = energy_cost_share(
        np.array([1_000.0, 1_000.0]), np.zeros(2), np.array([0.0, -50.0]), np.zeros(2)
    )
    assert not defined.any() and np.isnan(share).all()


def test_summary_and_bands():
    n = 2 * MIN_RECORDS
    loss = np.concatenate([np.zeros(MIN_RECORDS), np.full(MIN_RECORDS, 300.0)])
    w = np.ones(n)
    share = np.full(n, 0.12)
    out = summarise_losses(loss, share, np.ones(n, dtype=bool), w)
    assert out["worse_off_pct"] == 50.0
    assert out["median_loss"] == 0
    assert out["loss_percentiles_worse_off"]["p50"] == 300
    assert out["high_share_pct"] == 100.0
    bands = {b["band"]: b["share_pct"] for b in loss_bands(loss, w)}
    assert bands["No remaining loss"] == 50.0 and bands["£250–500"] == 50.0
    assert sum(bands.values()) == pytest.approx(100)


def test_thin_groups_get_no_medians():
    out = summarise_losses(
        np.full(5, 200.0), np.full(5, 0.1), np.ones(5, bool), np.ones(5)
    )
    assert out["median_loss"] is None and out["loss_percentiles_worse_off"] is None
    assert out["worse_off_pct"] == 100.0


def test_option_support_reduces_loss_pound_for_pound():
    n = MIN_RECORDS
    hit = np.full(n, 400.0)
    hep = np.full(n, 100.0)
    out = remaining_losses(
        hit,
        hep,
        np.full(n, 2_000.0),
        hep,
        np.full(n, 20_000.0),
        np.ones(n),
        {"all": np.array(["x"] * n)},
        {"all": ["x"]},
        {"cash": np.full(n, 150.0), "cut": np.full(n, 150.0)},
    )
    assert out["baseline"]["mean_loss"] == 300
    assert out["cash"]["mean_loss"] == out["cut"]["mean_loss"] == 150
    assert out["cash"]["median_share_pct"] == out["cut"]["median_share_pct"]


def test_groupings():
    assert tenure_group(
        ["RENT_FROM_COUNCIL", "RENT_FROM_HA", "OWNED_OUTRIGHT"]
    ).tolist() == [
        "Social rent",
        "Social rent",
        "Owned outright",
    ]
    q = use_quintiles(np.arange(10.0), np.ones(10))
    assert q.tolist() == [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]
