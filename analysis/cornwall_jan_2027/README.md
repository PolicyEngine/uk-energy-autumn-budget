# Cornwall Insight's January 2027 cap forecast: cost by income decile and poverty

This note backs a reply to a stakeholder question. The question had two parts:

- If the price cap rises to Cornwall Insight's forecast £1,999.28 for January–March 2027, how many people would be pushed below the poverty line?
- What would each income decile pay in cash, and as a share of its income?

Every number below comes from [`run.py`](run.py) and is written to [`results.json`](results.json). The script uses the same model, data and household bills as the dashboard.

## Price assumptions

| | October–December 2026 (comparison) | January–March 2027 (scenario) |
|---|---|---|
| Source | Ofgem, [announced cap](https://www.ofgem.gov.uk/press-release/energy-price-cap-will-rise-4-october-2026) | Cornwall Insight, [forecast of 30 Sep 2026](https://www.cornwall-insight.com/predictions-and-insights-into-the-default-tariff-cap/) (wholesale prices at the close on 28 Sep) |
| Status | Set by Ofgem | Forecast; Ofgem announces the January cap by late November |
| Electricity, unit rate / standing charge | 26.32p/kWh / 54.83p a day | 30.28p/kWh / 55.00p a day |
| Gas, unit rate / standing charge | 7.97p/kWh / 29.68p a day | 9.76p/kWh / 31.00p a day |
| Typical bill (2,500 kWh electricity, 9,500 kWh gas) | £1,723.61 (Ofgem: £1,723) | £1,998.10 (Cornwall: £1,999.28; the gap is rounding in the rates) |

The rates are direct-debit averages for Great Britain, held in `TARIFFS` in [`config.py`](../../src/energy_budget/config.py). Both periods have 0% VAT on electricity in Great Britain, under [SI 2026/987](https://www.legislation.gov.uk/uksi/2026/987/made). The comparison is therefore like for like: the cost below is the cap rise alone, with no VAT change mixed in.

**Why October–December 2026 is the comparison point.** It is the cap in force immediately before January. Cornwall and Ofgem describe each new cap as a change from the previous one. The dashboard measures from April–June 2026 instead, because it covers the whole 2026-27 financial year. Measuring from April–June here would count both the October and the January rises as one rise.

**What "a year" means.** Cornwall's £1,999 is an annual figure: a typical household's bill over a year at January–March rates. The headline cost therefore holds the January–March rates for a full year, as the cap's headline figure does. The "January–March only" columns give the cost for that quarter alone. They use seasonal consumption: 37.5% of a year's gas and 28.5% of its electricity, [Ofgem's winter shares](https://www.ofgem.gov.uk/sites/default/files/docs/2018/11/appendix_4_-_wholesale_costs.pdf#page=6) split evenly across the two winter quarters. Because January–March is a high-use quarter, its cost (£80) is more than a quarter of the annual figure (£242 / 4 = £61).

## Cost by income decile

Great Britain only (28.6 million households). Northern Ireland is outside the Ofgem cap.

| Decile | Extra cost a year | Share of net income | Extra cost, Jan–Mar only | Share of that quarter's income |
|---|---|---|---|---|
| 1 | £201 | 0.8% | £66 | 1.0% |
| 2 | £223 | 0.6% | £74 | 0.8% |
| 3 | £220 | 0.5% | £72 | 0.7% |
| 4 | £218 | 0.4% | £72 | 0.6% |
| 5 | £235 | 0.4% | £78 | 0.6% |
| 6 | £249 | 0.4% | £82 | 0.5% |
| 7 | £231 | 0.3% | £77 | 0.5% |
| 8 | £268 | 0.3% | £89 | 0.5% |
| 9 | £278 | 0.3% | £92 | 0.4% |
| 10 | £298 | 0.2% | £99 | 0.2% |
| All GB households | £242 | | £80 | |

- **Deciles:** PolicyEngine's household income deciles (`household_income_decile`), ranking people by equivalised household net income before housing costs, as in DWP's HBAI.
- **Share of income:** the decile's mean extra cost divided by its mean household net income (a ratio of means). Averaging each household's own share instead gives a steeper gradient, because it puts more weight on households with very low incomes.
- **Why the average (£242) is below the typical-bill rise (£274):** Microcosm households use less energy on average than Ofgem's typical consumption values. Each household's kWh is recovered from its spending in the dataset; see the dashboard's methodology.

## Poverty

Official poverty statistics ([DWP's HBAI](https://www.gov.uk/government/collections/households-below-average-income-hbai--2)) measure income before energy bills are paid, so a price cap rise on its own does not change the official poverty rate. The figure below is **illustrative only**.

Method: deduct each household's annual extra cost from its income, keep the poverty line (60% of median equivalised income) where it is now, and count people who move below it. This is close to the after-energy-costs approach of England's official fuel poverty measure, [Low Income Low Energy Efficiency](https://www.gov.uk/government/collections/fuel-poverty-statistics), without its energy-efficiency test.

| | Before housing costs | After housing costs |
|---|---|---|
| People newly below the line | 0.23 million | 0.29 million |
| of whom under 18 | 0.04 million | 0.05 million |
| Baseline poverty rate (Microcosm, 2026-27) | 14.2% | 18.0% |

The reply rounds this to "around a quarter of a million". Reasons not to quote it more precisely:

- It applies a full year of higher prices. Over January–March alone the cost is about a third of that.
- Microcosm's baseline relative poverty is below DWP's (18% after housing costs, against DWP's 20% in 2024-25 ([HBAI](https://www.gov.uk/government/collections/households-below-average-income-hbai--2))), so levels near the line are uncertain.
- Under-18 counts are by age, not DWP's dependent-child definition.
- The poverty line is recovered as the cut-point between people in and out of poverty, because policyengine-uk computes the relative line inside `in_relative_poverty_*`. An independent check found it within £1 of the exact line, with identical counts.

## Assumptions

- Every household is on the capped direct-debit tariff. Around 35% are on fixed tariffs and would not see a January rise ([Ofgem](https://www.ofgem.gov.uk/press-release/energy-price-cap-will-rise-4-october-2026)).
- No change in how much energy households use.
- No new government support. Existing support in the baseline, such as the Warm Home Discount, is unchanged.
- The forecast can change before Ofgem sets the January cap.

## Not used in the reply, and why

- **£bn totals.** They weren't asked for and are easily misquoted.
- **The first draft's April–June 2026 comparison** (£443 a year). It mixed two cap rises together and assumed 0% VAT all year.
- **Two-decimal percentages and separate child counts.** They suggest more precision than the method supports.

## Reproduce

```bash
PYTHONPATH=src .venv/bin/python analysis/cornwall_jan_2027/run.py
```

policyengine 6.2.7 (policyengine-uk 2.125.1) on Microcosm UK 2024-25 (`microcosm_uk_2024_25.h5`, sha256 `aa31bdf6…`). Full provenance is in `results.json`.
