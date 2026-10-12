# UK energy bills and the Autumn Budget 2026

How much forecast gas and electricity prices add to UK household bills in 2026-27 and 2027-28, and what each Autumn Budget support option would cost and do. Scored with [PolicyEngine](https://policyengine.org) on Microcosm UK.

## Baseline: current law at forecast prices

| Quarter | Source | Status |
|---|---|---|
| Apr–Jun 2026 | [Ofgem cap](https://www.ofgem.gov.uk/your-energy-supply/your-energy-bill/energy-price-cap-unit-rates-and-standing-charges), £1,641 | Announced |
| Jul–Sep 2026 | Ofgem cap, £1,663 | Announced |
| Oct–Dec 2026 | [Ofgem cap](https://www.ofgem.gov.uk/press-release/energy-price-cap-will-rise-4-october-2026), £1,723, electricity VAT-free | Announced |
| Jan–Mar 2027 | [Cornwall Insight](https://www.cornwall-insight.com/press-releases/16-price-cap-rise-forecast-in-january/), £1,999 (30 Sep 2026) | Forecast |
| Apr–Jun 2027 | [Average of EDF, British Gas and E.ON Next](https://www.moneysavingexpert.com/utilities/energy-price-cap-prediction/), £2,074 (6–7 Oct 2026) | Forecast |
| Jul–Sep 2027 | Same average, £1,912 | Forecast |
| Oct–Dec 2027 | [OVO](https://www.ovoenergy.com/price-cap), £1,846 at 0% electricity VAT (7 Oct 2026); £1,890 with VAT restored | Forecast |
| Jan–Mar 2028 | Held at Oct–Dec 2027 | Assumed |

- Ofgem cut its typical consumption values on 1 July 2026, so published caps from July can't be compared with £1,641. Every quarter is re-costed from unit rates and standing charges at the old 2,700 / 11,500 kWh (`TARIFFS` in `config.py`; `tests/test_prices.py` checks each against the published figure).
- **Usage, not a bill multiplier.** Microcosm builds each household's spend as kWh priced at DESNZ Quarterly Energy Prices for FY2024-25 (regional unit cost plus fixed cost, VAT included) and then reweights households to ONS 2025 spending ([microcosm#1113](https://github.com/PolicyEngine/microcosm/issues/1113); the build record of the pinned release shows the `price_domestic_energy` stage, and each region's lowest electricity spend equals its QEP fixed cost). Each household's kWh are recovered as `max(0, spend − fixed cost) ÷ unit rate` (`bills.py`) and every quarter is costed as kWh × unit rate + standing charge. Households with no spend on a fuel have no connection for it and pay no standing charge; a connected household whose spend is at or below the fixed cost has zero kWh and pays the standing charge only. On the QEP basis no spend falls below the fixed cost, but about 10% of households have electricity spend exactly equal to it (zero kWh in the build), so only standing charges move for them and their bill change is understated. `KWH_BASIS` in `config.py` switches the reference tariff to the CY2025 Ofgem caps as a sensitivity.
- **Seasonal use.** The central estimate uses [Ofgem's winter shares](https://www.ofgem.gov.uk/sites/default/files/docs/2018/11/appendix_4_-_wholesale_costs.pdf#page=6): 75% of gas and 57% of electricity is used in October–March, split equally between the two quarters of each half-year; standing charges are time-weighted. Equal quarterly use is reported as a sensitivity (`CONSUMPTION_PROFILE`).
- VAT on domestic electricity is 0% for supplies in England, Wales and Scotland from 1 Oct 2026 to 31 Mar 2027 ([The Value Added Tax (Supplies of Domestic Electricity) Order 2026, SI 2026/987](https://www.legislation.gov.uk/uksi/2026/987/made)), then 5% again. Northern Ireland keeps the 5% reduced rate throughout.
- 2027-28: April–September 2027 use the average of supplier forecasts (EDF, British Gas, E.ON Next); October–December 2027 uses OVO's forecast with 5% electricity VAT restored; January–March 2028 is held at that level. Forecasts give no fuel split, so Cornwall Insight's January 2027 unit rates and standing charges are scaled to each total.
- Everything else is current law: the Energy Price Guarantee ended in April 2024 and pays nothing.

## Budget options

| Option | Design |
|---|---|
| Targeted discount (RF, simplified) | A fixed-payment illustration of the [Resolution Foundation](https://www.resolutionfoundation.org/publications/billing-me-softly/) unit-rate discount: £175 to GB households on means-tested benefits or whose highest individual income is under £24,000. Assumes a flat £175 per eligible household (RF's average) rather than a unit-rate discount, an annual rather than three-month income test, and full take-up. Reform copied from [uk-energy-reforms](https://github.com/PolicyEngine/uk-energy-reforms) into `src/energy_budget/reforms`. |
| Warm Home Discount top-up | Extra £100 to GB households where any member receives a listed means-tested benefit. A means-tested-household proxy: the scheme's own rules ([England and Wales](https://www.gov.uk/the-warm-home-discount-scheme/if-you-live-in-england-and-wales), [Scotland](https://www.gov.uk/the-warm-home-discount-scheme/if-you-live-in-scotland)) are narrower, and the modelled caseload (about 7.8m households) exceeds DESNZ's estimate of around 6 million recipient households across Great Britain in winter 2025/26 ([DESNZ, January 2026, p. 5](https://assets.publishing.service.gov.uk/media/697b454bf8f4a746d9572efe/continuing-the-warm-home-discount-scheme-government-response.pdf#page=5)). |
| Cost of Living Payment | £300 to households on means-tested benefits |
| £400 to every household | The 2022 Energy Bills Support Scheme design |
| Cap freeze | Electricity and gas unit rates and standing charges held at April–June 2026 levels. Each household's subsidy is its forecast bill minus its bill at April–June 2026 tariffs for the same kWh, floored at zero, costed directly from bills. A price restoration, outside HBAI income. |
| Extend the electricity VAT cut | 0% VAT on domestic electricity through 2027-28 (GB); costed from bills, as PolicyEngine UK has no domestic electricity VAT parameter |
| Remove remaining levies | £120 off a typical electricity bill, applied as a share of each GB electricity bill (2027-28) |

The first four are PolicyEngine reforms; the last three are price cuts costed from each household's bill. Poverty is PolicyEngine's HBAI relative measure: the WHD top-up counts as income (as DWP treats the Warm Home Discount) and the RF discount is counted the same way by assumption; price cuts do not move it.

## Limitations

- Every household is modelled on the capped variable tariff. Around 35% of households are on fixed tariffs and will not see the October 2026 cap rise ([Ofgem](https://www.ofgem.gov.uk/press-release/energy-price-cap-will-rise-4-october-2026)); tariff type, payment method and contract expiry are not modelled, and no correction is inferred from the 35% share.
- A static scenario: households keep the same kWh, and benefit uprating doesn't respond to higher inflation.
- Forecasts after March 2027 come from suppliers only, with no electricity/gas split. No forecaster publishes January–March 2028.
- Microcosm matches ONS energy spending but puts 2024-25 relative poverty after housing costs at 18.3% of people and 23.4% of people under 18, against DWP's 20% of people and 27% of children (enhanced FRS: 21.2% and 31.0%). Child rates here are under-18 rates (`age < 18`); DWP's child count covers dependent children, including some 16–19-year-olds in full-time non-advanced education, so the two are not directly comparable. Poverty outputs are relative poverty (`in_relative_poverty_*`); absolute poverty (`in_poverty_*`, fixed FYE 2025 line) is exported alongside. Its implied national volumes (about 84 TWh electricity, 207 TWh gas) sit below DESNZ Energy Trends for FY2024-25 (93 TWh, 260 TWh) because calibration reweights households to the lower ONS spending total.
- Microcosm UK 2024-25 (release `microcosm-uk-2024-25-national-20261002T230158Z-5c6b3f68`) is not in the certified policyengine.py bundle; it runs with `allow_unmanaged=True`, pinned by revision and SHA-256. Its producer certification covers policyengine-uk 2.100.0, not the 2.125.1 runtime used here.
- Households are grouped by type from the whole household: those with more than one benefit unit are "Multiple family units".
- Northern Ireland uses GB prices as a proxy.

## Reproducibility

`energy-budget` writes `reproducibility.json` at the repository root: the git commit (and whether the tree had uncommitted changes), the command, the timestamp, policyengine / policyengine-uk / policyengine-core versions, the dataset repository, revision, release and verified SHA-256, and the SHA-256 of every generated `src/data/*.json`.

## Model/data compatibility

The Microcosm release is certified for policyengine-uk 2.100.0 / core 3.32.5; this analysis runs 2.125.1 / 3.33.0. [`validation/compatibility_report.md`](validation/compatibility_report.md) re-runs the full pipeline under the certified pair and explains every difference: energy uprating that 2.100.0 would apply twice under the kWh method (policyengine-uk#1868), the absolute poverty line's move to FYE 2025 (#1889) and State Pension age (#1899, #1904, #1907).

## Run

```bash
# Model (Python 3.13)
uv venv --python 3.13 .venv && uv pip install -e ".[dev]"
export HUGGING_FACE_TOKEN=...   # access to policyengine/populace-uk-private
.venv/bin/energy-budget          # writes src/data/*.json and reproducibility.json
.venv/bin/python -m pytest

# Dashboard (Next.js, PolicyEngine ui-kit)
bun install
bun run dev                      # http://localhost:3000/uk/energy-autumn-budget
```
