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
payment are identical. Each moving output traces to one of three documented
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
2. **Absolute poverty line (baseline poverty rates 4-5pp lower under 2.100.0; poverty
   effects of the payment options smaller).** policyengine-uk#1889 moved the HBAI
   absolute low-income line from the FYE 2011 reference year to FYE 2025, as DWP did in
   HBAI from March 2026. The 2026 BHC line is £456.63 a week in 2.125.1 against
   £403.42 in 2.100.0 (+13.2%; AHC £395.49 against £345.64, +14.4%). Fewer people lie
   near the lower line, so the same £175/£100/£300 payments lift fewer of them across
   it. This is a definitional change; the published figures use the current official
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
#1868), and its SPA and poverty-line definitions are out of date. The differences are
attributable and directional; none is unexplained. A Microcosm release recertified
against policyengine-uk 2.125.1 would remove the manifest mismatch; until then this
report is the revalidation evidence.
