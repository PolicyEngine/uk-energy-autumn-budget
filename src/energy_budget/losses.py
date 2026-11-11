"""Households with the largest remaining losses (issue #11, section B).

Pure numpy, no PolicyEngine import, so the tests can exercise it directly.

Reference period. Each financial year (2026-27, 2027-28) is compared with the
same household's energy use priced for a whole year at April-June 2026 cap
rates, the last quarter before the rise. That is the dashboard's existing
"price rise".

Remaining loss. A household's remaining loss is its price rise minus the new
support it receives, in pounds a year:

    remaining loss = (bill at the year's prices - bill at April-June 2026 rates)
                     - new cash support - new tariff savings

Cash and tariff savings are treated alike: a £100 payment and a £100 cut in
the bill reduce the loss by £100, whether or not HBAI counts them as income.
In the post-Budget baseline the price rise already reflects the electricity
VAT extension (it is in the tariffs) and the only new cash is the Household
Energy Payment. With an option, the option's support (its change in household
net income, or its cut in bills) is subtracted as well. The £150 Warm Home
Discount was paid in both periods, so it does not change the loss.

Energy-cost share. Net energy spending as a share of household income after
housing costs, both before any energy support:

    share = (bill - energy support) / (HBAI income after housing costs
                                       - energy support counted in it)

Energy support is the Household Energy Payment, the Warm Home Discount and,
with an option, the option's support. Taking it off the bill and out of income
treats cash and bill cuts identically. Households whose income after housing
costs (before energy support) is zero or negative have no defined share; they
are counted separately, not as above or below the threshold. A household
spends a "high share" when the share exceeds ``HIGH_SHARE``.

HBAI poverty is reported separately elsewhere and is not used here.
"""

from __future__ import annotations

import numpy as np

# Remaining losses below £1 a year count as none (float rounding).
WORSE_OFF_GBP = 1.0
HIGH_SHARE = 0.10
# Loss bands (£ a year) for the distribution; the last is open-ended.
LOSS_BANDS = [0, 100, 250, 500, 750]
# Percentiles of the remaining loss among households still worse off.
PERCENTILES = (50, 75, 90, 95)
# Groups with fewer survey records than this get no median or percentiles.
MIN_RECORDS = 100


def weighted_quantile(values, weights, q):
    """Weighted quantile (``q`` in [0, 1]) by the inverted weighted CDF."""
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    keep = weights > 0
    values, weights = values[keep], weights[keep]
    if values.size == 0:
        return float("nan")
    order = np.argsort(values, kind="stable")
    values, weights = values[order], weights[order]
    cdf = np.cumsum(weights) / weights.sum()
    i = int(np.searchsorted(cdf, q, side="left"))
    return float(values[min(i, values.size - 1)])


def quarter_bill(kwh, connected, quarter, share):
    """One quarter's £ bill: its share of annual kWh plus a quarter's standing charge.

    ``quarter`` is a (unit p/kWh, standing p/day) tuple. The four quarters of
    a year sum to ``bills.annual_bill`` with the same shares.
    """
    unit, standing = quarter
    kwh = np.asarray(kwh, dtype=float)
    return np.where(connected, (unit * share * kwh + standing * 365 / 4) / 100, 0.0)


def energy_cost_share(bill, support, income_ahc, support_in_income):
    """Net energy spending over income after housing costs, before support.

    Returns the share (NaN where the denominator is zero or negative) and a
    mask of households with a defined share.
    """
    net_bill = np.asarray(bill, dtype=float) - np.asarray(support, dtype=float)
    income = np.asarray(income_ahc, dtype=float) - np.asarray(
        support_in_income, dtype=float
    )
    defined = income > 0
    share = np.full(net_bill.shape, np.nan)
    np.divide(net_bill, income, out=share, where=defined)
    return share, defined


def _pct(mask, w):
    total = float(np.sum(w))
    return round(float(np.sum(w * mask)) / total * 100, 1) if total else None


def loss_bands(loss, w):
    """Share of households (%) in each remaining-loss band."""
    out = [{"band": "No remaining loss", "share_pct": _pct(loss < WORSE_OFF_GBP, w)}]
    edges = LOSS_BANDS[1:] + [None]
    lo = WORSE_OFF_GBP
    for i, hi in enumerate(edges):
        label_lo = LOSS_BANDS[i]
        if hi is None:
            mask = loss >= lo
            label = f"£{label_lo:,} or more"
        else:
            mask = (loss >= lo) & (loss < hi)
            label = f"Up to £{hi:,}" if label_lo == 0 else f"£{label_lo:,}–{hi:,}"
        out.append({"band": label, "share_pct": _pct(mask, w)})
        lo = hi
    return out


def summarise_losses(loss, share, defined, w):
    """Headline remaining-loss and energy-cost-share statistics for a group."""
    loss = np.asarray(loss, dtype=float)
    w = np.asarray(w, dtype=float)
    worse = loss >= WORSE_OFF_GBP
    records = int(np.sum(w > 0))
    worse_records = int(np.sum(worse & (w > 0)))
    enough = records >= MIN_RECORDS
    enough_worse = worse_records >= MIN_RECORDS
    out = {
        "records": records,
        "households_m": round(float(np.sum(w)) / 1e6, 2),
        "worse_off_m": round(float(np.sum(w * worse)) / 1e6, 2),
        "worse_off_pct": _pct(worse, w),
        "mean_loss": round(float(np.average(loss, weights=w))) if w.sum() else None,
        "median_loss": round(weighted_quantile(loss, w, 0.5)) if enough else None,
        "worse_off_records": worse_records,
        "loss_percentiles_worse_off": (
            {
                f"p{p}": round(weighted_quantile(loss[worse], w[worse], p / 100))
                for p in PERCENTILES
            }
            if enough_worse
            else None
        ),
        "high_share_pct": _pct(defined & (share > HIGH_SHARE), w),
        "no_income_after_housing_pct": _pct(~defined, w),
        "median_share_pct": (
            round(weighted_quantile(share[defined], w[defined], 0.5) * 100, 1)
            if int(np.sum(defined & (w > 0))) >= MIN_RECORDS
            else None
        ),
    }
    return out


def by_group(loss, share, defined, w, groups, order):
    """``summarise_losses`` for each group label in ``order``."""
    groups = np.asarray(groups)
    return {
        g: summarise_losses(
            loss[groups == g], share[groups == g], defined[groups == g], w[groups == g]
        )
        for g in order
        if np.any(groups == g)
    }


def use_quintiles(total_kwh, w):
    """Household-weighted quintile (1-5) of total annual kWh."""
    total_kwh = np.asarray(total_kwh, dtype=float)
    cuts = [weighted_quantile(total_kwh, w, q) for q in (0.2, 0.4, 0.6, 0.8)]
    return np.searchsorted(cuts, total_kwh, side="left") + 1


TENURE_GROUPS = {
    "OWNED_OUTRIGHT": "Owned outright",
    "OWNED_WITH_MORTGAGE": "Owned with a mortgage",
    "RENT_FROM_COUNCIL": "Social rent",
    "RENT_FROM_HA": "Social rent",
    "RENT_PRIVATELY": "Private rent",
}


def tenure_group(tenure):
    """Tenure labels, with council and housing association grouped as social rent."""
    return np.array([TENURE_GROUPS.get(str(t), "Other") for t in tenure])


def remaining_losses(
    hit,
    new_cash,
    bill,
    energy_support,
    income_ahc,
    w,
    groups,
    group_order,
    options,
):
    """Remaining losses for the baseline and each option.

    ``hit`` is the price rise against April-June 2026 rates; ``new_cash`` the
    baseline's new cash support (the Household Energy Payment);
    ``energy_support`` all energy support counted in HBAI income (that payment
    plus the Warm Home Discount); ``options`` maps option id to its support
    per household. ``groups`` maps a breakdown name to per-household labels,
    ``group_order`` to the label order.
    """
    out = {}
    scenarios = {"baseline": np.zeros_like(hit)} | dict(options)
    for key, support in scenarios.items():
        loss = hit - new_cash - support
        share, defined = energy_cost_share(
            bill, energy_support + support, income_ahc, energy_support
        )
        out[key] = {
            **summarise_losses(loss, share, defined, w),
            "bands": loss_bands(loss, w),
            "by": {
                name: by_group(loss, share, defined, w, labels, group_order[name])
                for name, labels in groups.items()
            },
        }
    return out
