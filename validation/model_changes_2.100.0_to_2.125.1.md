## Summary

The pinned dataset release `microcosm-uk-2024-25-national-20261002T230158Z-5c6b3f68`
(HF `policyengine/populace-uk-private` @ `f9d1922cddab6b54a0dd37794a9bac74e3780c88`)
declares in `releases/microcosm-uk-2024-25-national/release_manifest.json`:

- `build.built_with_model_package`: policyengine-uk 2.100.0;
  `build.built_with_core_package`: policyengine-core 3.32.5 (built 2026-10-04T18:18:33Z);
- `compatible_model_packages`: `policyengine-uk ==2.100.0`;
  `compatible_core_packages`: `policyengine-core ==3.32.5`;
- artifact `microcosm_uk_2024_25.h5`, SHA-256 `aa31bdf6…9588af` (the file we pin).

The dashboard runs on policyengine 6.2.7, which pins policyengine-uk 2.125.1 and
policyengine-core 3.33.0, outside the declared specifier. To test this, the full pipeline
was rerun on the declared pair (`validation/run_certified_pair.py`, separate venv, same
dataset file, same reforms and Scenario) and compared output by output.

**Conclusion: the upgraded pair does not reproduce the certified pair within tolerance,
and should not be expected to.** Population, weights, household count and the £400
payment are identical. Each moving output traces to one of four documented
policyengine-uk changes between the versions, and in each case the 2.125.1 behaviour
is the one our pipeline's assumptions require:

1. **Energy spend uprating (bills, extra cost, cap freeze, VAT, levies: +5.8% to +7.5%
   under 2.100.0).** In 2.100.0, `electricity_consumption`, `gas_consumption` and
   `domestic_energy_consumption` are on the CPI list in `data/uprating_indices.yaml`
   (PolicyEngine/policyengine-uk#1860), so the stored 2024 values are uprated by CPI to
   2026 (x1.0578) and 2027 (x1.0789). policyengine-uk#1868 (fixes #1867, merged
   23 Sep 2026, after 2.100.0) removed them, because the data build already prices
   energy. Our pipeline recovers kWh by dividing each household's spend by the
   dataset's own reference tariff (QEP FY2024-25, the Microcosm `price_domestic_energy`
   stage), so it needs the spend at the build's prices, i.e. unuprated. Under 2.100.0
   the spend is 5.78% higher (the population-check table shows exactly +5.78% in 2026),
   kWh is inflated by 7.0-7.5% (more than 5.78% because the fixed cost is subtracted
   first), and the 10.3% of households whose electricity spend equals the fixed cost
   (zero kWh) acquire spurious usage. Every bill-based output scales accordingly. Under
   2.100.0 the pipeline would double-count 2024-26 price growth; 2.125.1 is the
   consistent pairing for this method.
2. **Absolute poverty line (`absolute_*` baseline rates 4-5pp lower under 2.100.0;
   absolute-poverty effects of the payment options smaller).** This explains the
   `absolute_*` outputs only; it cannot move relative poverty, whose line is recomputed
   from each run's own median (item 4). policyengine-uk#1889 moved the HBAI
   absolute low-income line from the FYE 2011 reference year to FYE 2025, as DWP did in
   HBAI from March 2026. The 2026 BHC line is £456.63 a week in 2.125.1 against
   £403.42 in 2.100.0 (+13.2%; AHC £395.49 against £345.64, +14.4%). Fewer people lie
   near the lower line, so the same £175/£100/£300 payments lift fewer of them across
   it. This is a definitional change; the `absolute_*` figures use the current official
   definition.
3. **State Pension age and benefit rules (eligibility shares about 1pp lower under
   2.100.0; option costs 2-4% lower; household-type and decile shifts).** 2.100.0 holds
   State Pension age at 66 from 2020. 2.125.1 legislates the 66-to-67 rise from April
   2026 (policyengine-uk#1899) and tests SPA by date of birth at mid-year
   (#1904, #1907). With the same people, 2.125.1 has 0.18m fewer people over SPA in
   2026-27 and 0.54m fewer in 2027-28, £3.9bn and £9.0bn less State Pension, and
   people aged 66 stay on working-age benefits: Universal Credit caseload +0.35m
   (+5.5%), Pension Credit spend -8% to -11%. More households pass the means-tested
   passport, so the targeted discount, WHD top-up and Cost of Living Payment reach
   about 1pp more households and cost 2-4% more under 2.125.1; pensioner household
   shares are 0.2pp lower. Further benefit-rule corrections in the range, not quantified one by one (UC minimum
   income floor #1973, UC claimant-only income #1978, HB passport and disregards
   #2000/#2123/#2133, Pension Credit capital #2018/#2070, contributory JSA double count
   in `household_benefits` #1924), together with the SPA change, move net incomes and decile assignment by up to 2.5%
   within deciles; total HBAI income differs by 0.2-0.5%.

4. **Relative poverty (the dashboard's headline measure): all-person rates within 0.4pp,
   under-18 rates 0.6-1.2pp higher under 2.100.0, payment options' relative-poverty
   effects larger under 2.100.0.** The relative line is 60% of each run's own median
   equivalised HBAI income, so it moves only with the income distribution. The medians
   differ by 0.2-0.8% (AHC line £22,097 against £22,195 in 2026-27; £22,446 against
   £22,619 in 2027-28), and holding the line fixed moves the 2026-27 under-18 AHC rate by
   under 0.1pp; the differences come from incomes, through two channels (person-level
   dumps of both runs, same people and weights):
   - *Universal Credit earned income (policyengine-uk#1978, with #1973).* In 2.100.0,
     `uc_earned_income` adds the earnings of every benefit-unit member, including
     qualifying young people and other non-claimants, and deducts the whole benefit
     unit's tax. #1978 (merged 5 Oct 2026) counts only claimants' earned income, each
     net of their own deductions (UC Regulations 2013 reg. 22(1)(b)); #1973 moved the
     minimum income floor to a net basis. For the 8.46m benefit units with children,
     2.100.0 assesses £7.2bn more earned income and £4.6bn more taper reduction in
     2026-27, so under-18s' equivalised AHC income is £214 a year lower on average
     (£524 among the 41% whose income differs). That raises the under-18 relative AHC
     rate from 22.63% to 23.58% in 2026-27 (22.80% to 23.96% in 2027-28).
   - *State Pension age (item 3).* Under 2.125.1 people aged 66 have no State Pension:
     their mean equivalised AHC income is £3,915 lower in 2026-27 and £11,048 lower in
     2027-28 than under 2.100.0, and their relative AHC rate is 20.9% and 33.8%, against
     16.8% and 16.6%. This raises the 2.125.1 all-person rate while the UC channel lowers
     it, so all-person AHC rates differ by only 0.1-0.2pp (BHC by 0.2-0.4pp the other way).

   With lower UC under 2.100.0, more people sit just below the line: 0.55m people within
   £300 below the 2026-27 AHC line (0.14m under 18) against 0.42m (0.10m) under 2.125.1.
   The same £175/£100/£300 payments therefore lift more people across it under 2.100.0,
   which is why its relative-poverty effects are larger (for example the targeted
   discount: -0.23pp against -0.14pp AHC in 2026-27). Both changes correct the model
   towards current law, so the 2.125.1 relative figures are the ones to publish.

Other changes checked and found not to affect our outputs: `energy_bills_credit` became
an annual top-up plus monthly EBSS components (both new components are 0 in 2026-27 and
2027-28, and the £400 option is identical to the penny); the Cost of Living Payment's
`qualifying_benefits` diff removes a duplicate `pension_credit` entry, not the benefit;
`uses_energy_prepayment_meter` and the EPG parameters are new but unused here (we do
not use the EPG); household weights, region and household counts are identical; the
Scenario API (`applied_before_data_load`, `simulation_modifier`) and every parameter
path we set exist in 2.100.0, so the harness needed no adaptation beyond bypassing
policyengine.py.

**Recommendation for the reviewer.** Keep 2.125.1. The certified pair's runtime CPI
uprating of energy is incompatible with how this dataset prices energy (fixed upstream in
#1868), its SPA and absolute poverty-line definitions are out of date, and its UC earned-income
rule counts non-claimants' earnings. The differences are
attributable and directional; none is unexplained. A Microcosm release recertified
against policyengine-uk 2.125.1 would remove the manifest mismatch; until then this
report is the revalidation evidence.
