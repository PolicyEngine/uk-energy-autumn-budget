# UK energy bills and the Autumn Budget 2026

How much forecast gas and electricity prices add to UK household bills in 2026-27 and 2027-28, and what each Autumn Budget support option would cost and do. Scored with [PolicyEngine](https://policyengine.org) on Microcosm UK.

## Baseline: current law at forecast prices

| Quarter | Source | Status |
|---|---|---|
| Apr–Jun 2026 | [Ofgem cap](https://www.ofgem.gov.uk/your-energy-supply/your-energy-bill/energy-price-cap-unit-rates-and-standing-charges), £1,641 | Pre-conflict reference |
| Jul–Sep 2026 | Ofgem cap, £1,663 | Announced |
| Oct–Dec 2026 | [Ofgem cap](https://www.ofgem.gov.uk/press-release/energy-price-cap-will-rise-4-october-2026), £1,723, electricity VAT-free | Announced |
| Jan–Mar 2027 | [Cornwall Insight](https://www.cornwall-insight.com/press-releases/16-price-cap-rise-forecast-in-january/), £1,999 (30 Sep 2026) | Forecast |
| Apr–Jun 2027 | [Average of EDF, British Gas and E.ON Next](https://www.moneysavingexpert.com/utilities/energy-price-cap-prediction/), £2,074 (6–7 Oct 2026) | Forecast |
| Jul–Sep 2027 | Same average, £1,912 | Forecast |
| Oct–Dec 2027 | [OVO](https://www.ovoenergy.com/price-cap), £1,846 at 0% electricity VAT (7 Oct 2026); £1,890 with VAT restored | Forecast |
| Jan–Mar 2028 | Held at Oct–Dec 2027 | Assumed |

- Ofgem cut its typical consumption values on 1 July 2026, so published caps from July can't be compared with £1,641. Every quarter is re-costed from unit rates and standing charges at the old 2,700 / 11,500 kWh (`TARIFFS` in `config.py`; `tests/test_prices.py` checks each against the published figure).
- Each household's electricity and gas spend rises by its fuel's price change and is loaded into PolicyEngine as its energy spending. Everything else is current law: the Energy Price Guarantee ended in April 2024 and pays nothing.
- VAT on domestic electricity is 0% from 1 Oct 2026 to 31 Mar 2027 ([SI 2026/987](https://www.legislation.gov.uk/uksi/2026/987/made)), then 5% again.
- Microcosm UK binds energy spending to ONS calendar-2025 spending ([microcosm#1113](https://github.com/PolicyEngine/microcosm/issues/1113)), so each fuel is rebased to April–June 2026 prices first.

## Budget options

Each option is a PolicyEngine reform against the baseline:

| Option | Design |
|---|---|
| Targeted discount | [Resolution Foundation](https://www.resolutionfoundation.org/publications/billing-me-softly/): £175 to households on means-tested benefits or whose highest individual income is under £24,000 (reform copied from [uk-energy-reforms](https://github.com/PolicyEngine/uk-energy-reforms) into `src/energy_budget/reforms`) |
| Cost of Living Payment | £300 to households on means-tested benefits |
| Warm Home Discount top-up | Extra £150 to households on means-tested benefits |
| Extend the electricity VAT cut | 0% VAT on domestic electricity through 2027-28 (GB); costed from bills, as PolicyEngine UK has no domestic electricity VAT parameter |
| £400 to every household | The 2022 Energy Bills Support Scheme design |
| Cap freeze | Energy Price Guarantee switched back on at £1,641, the April–June 2026 cap |

Poverty is PolicyEngine's HBAI relative measure. HBAI income excludes energy bills and energy bill support, so only cash counted as income moves it.

## Limitations

- Households keep using the same energy, and benefit uprating doesn't respond to higher inflation.
- Forecasts after March 2027 come from suppliers only, with no electricity/gas split; Cornwall Insight's January unit rates are scaled to each total. No forecaster publishes January–March 2028.
- Microcosm matches ONS energy spending (£42.2bn vs £41.9bn in 2025) but puts 2024-25 relative poverty after housing costs at 15.3% against DWP's 20%.
- Microcosm's gas spending is well below enhanced FRS (£469 against £770 per household at April–June 2026 prices), so the shock is smaller than in earlier PolicyEngine analyses.
- Microcosm UK 2024-25 (release `microcosm-uk-2024-25-national-20261002T230158Z-5c6b3f68`) is not yet in the policyengine.py 6.2.7 certified bundle; it runs with `allow_unmanaged=True`, pinned by revision and SHA-256.
- Northern Ireland uses GB prices as a proxy.

## Run

```bash
# Model (Python 3.13)
uv venv --python 3.13 .venv && uv pip install -e ".[dev]"
export HUGGING_FACE_TOKEN=...   # access to policyengine/populace-uk-private
.venv/bin/energy-budget          # writes src/data/*.json
.venv/bin/python -m pytest

# Dashboard (Next.js, PolicyEngine ui-kit)
bun install
bun run dev                      # http://localhost:3000/uk/energy-autumn-budget
```
