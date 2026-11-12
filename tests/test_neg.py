"""National Energy Guarantee (two-tier): block kWh at a discounted unit rate."""

import numpy as np
import pytest

from energy_budget.budget_options import (
    neg_blocks,
    neg_support,
    neg_support_at_source_prices,
    neg_unit_rate,
)
from energy_budget.config import quarter_shares
from energy_budget.prices import year_quarters

KWH = {
    "elec": np.array([5_000.0, 5_000.0, 1_000.0, 0.0]),
    "gas": np.array([20_000.0, 0.0, 0.0, 0.0]),
}
CONNECTED = {
    "elec": np.array([True, True, True, False]),
    "gas": np.array([True, False, False, False]),
}
GB = np.zeros(4, dtype=bool)


def _rate(year, fuel, nation="GB"):
    q = year_quarters(year, nation)[fuel]
    return sum(s * u for s, (u, _) in zip(quarter_shares(fuel), q)) / 100


def test_blocks_port_half_the_gas_block():
    blocks = neg_blocks(CONNECTED)
    assert blocks["elec"].tolist() == [1_800, 4_850, 4_850, 0]
    assert blocks["gas"].tolist() == [6_100, 0, 0, 0]


@pytest.mark.parametrize("year", [2026, 2027])
def test_saving_on_block(year):
    saving = neg_support(year, KWH, CONNECTED, GB)
    e, g = _rate(year, "elec"), _rate(year, "gas")
    # Gas home above both blocks: the whole of each block is discounted.
    assert saving[0] == pytest.approx(1_800 * e * 0.25 + 6_100 * g * 0.4)
    # No gas: the electricity block is 1,800 + 6,100 / 2 = 4,850 kWh.
    assert saving[1] == pytest.approx(4_850 * e * 0.25)
    # Below the block: only the kWh used are discounted.
    assert saving[2] == pytest.approx(1_000 * e * 0.25)
    # Not connected: nothing.
    assert saving[3] == 0


def test_unit_rate_uses_post_budget_vat():
    assert neg_unit_rate(2026, "elec") == pytest.approx(_rate(2026, "elec"))
    # GB electricity is VAT-free from October 2026; Northern Ireland pays 5%
    # throughout 2026-27, so its weighted rate is higher.
    assert neg_unit_rate(2026, "elec", "NI") > neg_unit_rate(2026, "elec")
    ni = np.array([False, True, False, False])
    saving = neg_support(2026, KWH, CONNECTED, ni)
    assert saving[1] == pytest.approx(4_850 * _rate(2026, "elec", "NI") * 0.25)


def test_source_prices_check():
    saving = neg_support_at_source_prices(KWH, CONNECTED)
    assert saving[0] == pytest.approx(1_800 * 0.31 * 0.25 + 6_100 * 0.10 * 0.4)
    assert saving[1] == pytest.approx(4_850 * 0.31 * 0.25)
