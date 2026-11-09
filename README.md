# UK energy bills and the Autumn Budget 2026

How much forecast gas and electricity prices add to UK household bills in 2026-27 and 2027-28 under the law after the Autumn Budget 2026, what the Budget's energy measures are worth, and what further support options would cost and do. Scored with [PolicyEngine](https://policyengine.org) on the certified Microcosm UK dataset.

## Baseline: post-Budget law at forecast prices

| Quarter | Source | Status |
|---|---|---|
| Apr–Jun 2026 | [Ofgem cap](https://www.ofgem.gov.uk/your-energy-supply/your-energy-bill/energy-price-cap-unit-rates-and-standing-charges), £1,641 | Announced |
| Jul–Sep 2026 | Ofgem cap, £1,663 | Announced |
| Oct–Dec 2026 | [Ofgem cap](https://www.ofgem.gov.uk/press-release/energy-price-cap-will-rise-4-october-2026), £1,723, electricity VAT-free | Announced |
| Jan–Mar 2027 | [Cornwall Insight](https://www.cornwall-insight.com/press-releases/16-price-cap-rise-forecast-in-january/), £1,999 (30 Sep 2026) | Forecast |
| Apr–Jun 2027 | [Average of EDF, British Gas and E.ON Next](https://www.moneysavingexpert.com/utilities/energy-price-cap-prediction/), £2,074 at 5% electricity VAT (6–7 Oct 2026); £2,025 with the Budget's 0% | Forecast |
| Jul–Sep 2027 | Same average, £1,912 | Forecast |
| Oct–Dec 2027 | [OVO](https://www.ovoenergy.com/price-cap), £1,846 at 0% electricity VAT (7 Oct 2026); £1,890 with 5% VAT | Forecast |
| Jan–Mar 2028 | Held at Oct–Dec 2027 | Assumed |

- The forecasts were made before the Budget and are unchanged. Each quarter's rates, status, source, date, published figure and the electricity VAT inside it sit together in `PRICE_PATH` / `TARIFFS` (`config.py`); `tests/test_prices.py` checks each against the published figure. To replace January–March 2027 with Ofgem's announcement, edit its `TARIFFS` and `PRICE_PATH` entries: later quarters take their fuel split from `FUEL_SPLIT_REFERENCE` (Cornwall Insight's 30 Sep 2026 January rates), not from January's tariffs.
- Ofgem cut its typical consumption values on 1 July 2026, so published caps from July can't be compared with £1,641. Every quarter is re-costed from unit rates and standing charges at the old 2,700 / 11,500 kWh.
- **Energy use.** The certified Microcosm release exports each household's annual electricity and gas use in kWh (household columns `electricity_kwh` and `gas_kwh`, calendar 2024; gas levelled to DESNZ Energy Trends, electricity to ONS 2024 spending at the QEP UK price). They are not policyengine-uk variables (the model's `*_consumption_kwh` inputs are monthly and unpopulated), so `baseline.py` reads them from the file the managed loader materialised, after checking its SHA-256 against the bundle, and aligns them to the simulation by `household_id`. Every quarter is costed as kWh × unit rate + standing charge, with kWh held fixed. The dataset's spending columns are those kWh priced at DESNZ Quarterly Energy Prices CY2024 (regional unit cost plus fixed cost, 5% VAT included, the basis policyengine-uk assumes); the build checks that every connected household's spend equals that price to the penny but costs nothing from spend.
- **Zero use and no connection.** A household with no gas spend has no mains gas and pays no gas standing charge (15.9% of households). GB households with electricity spend equal to their region's fixed cost are connected with zero use and pay the standing charge only (3.6% of households). In Northern Ireland the fixed cost is zero, so zero spend can't separate zero use from no connection; those 84 records are treated as not connected.
- **Seasonal use.** The central estimate uses [Ofgem's winter shares](https://www.ofgem.gov.uk/sites/default/files/docs/2018/11/appendix_4_-_wholesale_costs.pdf#page=6): 75% of gas and 57% of electricity is used in October–March, split equally between the two quarters of each half-year; standing charges are time-weighted. Equal quarterly use is reported as a sensitivity (`CONSUMPTION_PROFILE`).
- **Electricity VAT.** 0% for supplies in England, Wales and Scotland from 1 Oct 2026 ([SI 2026/987](https://www.legislation.gov.uk/uksi/2026/987/made)); [Budget 2026](https://www.gov.uk/government/publications/budget-2026-document/budget-2026-html) extends the zero rate to 30 June 2027 and expects it to apply in Northern Ireland from 1 April 2027 (announced policy, not yet law); 5% otherwise. `ELEC_VAT` in `config.py` sets the rate by quarter and nation, matching policyengine-uk 2.174.1. Each quarter's published electricity rates are taken back to their VAT-exclusive level and priced at that rate, so a VAT change enters bills once, through the tariff. policyengine-uk's own energy VAT (`domestic_energy_vat`: a fiscal-year day-weighted rate on bills ÷ 1.05) is not used for any result; no simulation changes a VAT rate, so its `vat_change` is zero (checked in every run) and VAT savings never reach income twice. `validation.json` reports both figures.
- 2027-28: April–September 2027 use the average of supplier forecasts (EDF, British Gas, E.ON Next); October–December 2027 uses OVO's forecast; January–March 2028 is held at that level. Forecasts give no fuel split, so `FUEL_SPLIT_REFERENCE` is scaled to each total.
- **Household Energy Payment.** £100 to households in council tax bands A–D in England in 2026-27 (Budget 2026), from policyengine-uk. It counts in household and HBAI income, so it moves poverty; bills are not reduced by it.
- Everything else is current law: the Energy Price Guarantee ended in April 2024 and pays nothing.

## The Budget's energy measures

Measured against a counterfactual with the same prices, data and other policies but no Household Energy Payment and electricity VAT as under SI 2026/987 alone (5% from April 2027 in Great Britain, 5% throughout in Northern Ireland). Results are in `src/data/budget_measures.json` and the `pre_budget` block of `results.json`.

| Measure | Year | Cost | Households receiving | Change in relative poverty (AHC) |
|---|---|---|---|---|
| £100 Household Energy Payment | 2026-27 | £1.96bn | 19.6m (67%) | −0.08pp (children −0.01pp) |
| Electricity VAT at 0% to June 2027 | 2027-28 | £0.36bn | 29.2m (all with electricity) | none (a price cut, not income) |

The payment is £0 in 2027-28 and the VAT extension changes nothing in 2026-27 (Great Britain was already at 0% to March 2027 and Northern Ireland stays at 5% until April 2027).

## Further options

| Option | Design |
|---|---|
| Targeted discount (RF, simplified) | A fixed-payment illustration of the [Resolution Foundation](https://www.resolutionfoundation.org/publications/billing-me-softly/) unit-rate discount: £175 to GB households on means-tested benefits or whose highest individual income is under £24,000. Assumes a flat £175 per eligible household (RF's average) rather than a unit-rate discount, an annual rather than three-month income test, and full take-up. Reform copied from [uk-energy-reforms](https://github.com/PolicyEngine/uk-energy-reforms) into `src/energy_budget/reforms`. |
| Warm Home Discount top-up | Extra £100 to GB households where any member receives a listed means-tested benefit. A means-tested-household proxy: the scheme's own rules ([England and Wales](https://www.gov.uk/the-warm-home-discount-scheme/if-you-live-in-england-and-wales), [Scotland](https://www.gov.uk/the-warm-home-discount-scheme/if-you-live-in-scotland)) are narrower, and the modelled caseload (about 7.6m households) exceeds DESNZ's estimate of around 6 million recipient households across Great Britain in winter 2025/26 ([DESNZ, January 2026, p. 5](https://assets.publishing.service.gov.uk/media/697b454bf8f4a746d9572efe/continuing-the-warm-home-discount-scheme-government-response.pdf#page=5)). |
| Cost of Living Payment | £300 to households on means-tested benefits |
| £400 to every household | The 2022 Energy Bills Support Scheme design |
| Cap freeze | Electricity and gas unit rates and standing charges held at April–June 2026 levels. Each household's subsidy is its forecast bill minus its bill at April–June 2026 tariffs for the same kWh, floored at zero, costed directly from bills. A price restoration, outside HBAI income. |
| Extend the electricity VAT cut | 0% VAT on domestic electricity from July 2027 to March 2028, UK-wide; costed from bills as the relief beyond the Budget's extension to June 2027 |
| Remove remaining levies | £120 off a typical electricity bill, applied as a share of each GB electricity bill (2027-28) |

All are scored against the post-Budget baseline. The first four are PolicyEngine reforms; the last three are price cuts costed from each household's bill. Poverty is PolicyEngine's HBAI relative measure: the WHD top-up counts as income (as DWP treats the Warm Home Discount), as does the £400 credit (policyengine-uk 2.174.1 follows DWP's treatment of the 2022 Energy Bills Support Scheme), and the RF discount is counted the same way by assumption; price cuts do not move it.

## Limitations

- Every household is modelled on the capped variable tariff. Around 35% of households are on fixed tariffs and will not see the October 2026 cap rise ([Ofgem](https://www.ofgem.gov.uk/press-release/energy-price-cap-will-rise-4-october-2026)); tariff type, payment method and contract expiry are not modelled, and no correction is inferred from the 35% share.
- A static scenario: households keep the same kWh, and benefit uprating doesn't respond to higher inflation.
- Forecasts after March 2027 come from suppliers only, with no electricity/gas split. No forecaster publishes January–March 2028.
- Microcosm puts 2024-25 relative poverty after housing costs at 18.5% of people, against DWP's 20%. Child rates here are under-18 rates (`age < 18`); DWP's child count covers dependent children, including some 16–19-year-olds in full-time non-advanced education, so the two are not directly comparable. Poverty outputs are relative poverty (`in_relative_poverty_*`); absolute poverty (`in_poverty_*`, fixed FYE 2025 line) is exported alongside.
- Its 2024 volumes are 85.9 TWh of electricity, against 91.7 TWh in DESNZ Energy Trends (the build levels electricity to ONS spending rather than volume), and 253.2 TWh of gas, against 252.3 TWh.
- Households are grouped by type from the whole household: those with more than one benefit unit are "Multiple family units".
- Northern Ireland uses GB prices as a proxy.

## Reproducibility

`energy-budget` writes `reproducibility.json` at the repository root: the git commit (and whether the tree had uncommitted changes), the command, the timestamp, policyengine / policyengine-uk / policyengine-core versions, the certified dataset's name, URI, build ID and SHA-256 (certified and verified), and the SHA-256 of every generated `src/data/*.json`. `src/data/validation.json` holds the run's checks: price-basis residuals, zero-use and unconnected records, energy totals against the release's DESNZ/ONS levels, Household Energy Payment eligibility and income treatment, `vat_change` in every simulation, and the VAT reconciliation.

## Model/data compatibility

policyengine.py 6.16.1 pins policyengine-uk 2.174.1 and certifies the Microcosm UK 2024-25 national release `microcosm-uk-2024-25-national-20261107T020434Z-eeb6093e` for it (built with the same model version), so the model and data are the certified pair. Earlier validation notes in `validation/` cover the previous releases.

## Run

```bash
# Model (Python 3.13)
uv venv --python 3.13 .venv && uv pip install -e ".[dev]"
export HUGGING_FACE_TOKEN=...   # access to policyengine/populace-uk-private (or a saved huggingface-cli login)
.venv/bin/energy-budget          # run from the repository root; writes src/data/*.json and reproducibility.json
.venv/bin/python -m pytest

# Dashboard (Next.js, PolicyEngine ui-kit)
bun install
bun run dev                      # http://localhost:3000/uk/energy-autumn-budget
```
