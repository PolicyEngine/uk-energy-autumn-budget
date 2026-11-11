import { useState } from "react";
import losses from "../data/losses.json";

const BASE = "#DD6B20";
const WITH_OPTION = "#319795";
const fmt = (v) => (v == null ? "—" : `${v < 0 ? "−" : ""}£${Math.abs(Math.round(v)).toLocaleString("en-GB")}`);
const pct = (v) => (v == null ? "—" : `${v.toFixed(1)}%`);

const BREAKDOWNS = [
  { key: "decile", label: "Income decile" },
  { key: "hh_type", label: "Household type" },
  { key: "region", label: "Region" },
  { key: "disability", label: "Disability benefits" },
  { key: "tenure", label: "Tenure" },
  { key: "energy_use", label: "Energy use (quintile of kWh)" },
  { key: "heating", label: "Heating fuel" },
];

const MEASURES = {
  worse_off_pct: { label: "Share still worse off", y: "% of households", fmt: pct },
  median_loss: { label: "Median remaining loss", y: "£/yr, median household", fmt },
  mean_loss: { label: "Average remaining loss", y: "£/yr, average household", fmt },
  high_share_pct: { label: "Energy costs above 10% of income", y: "% of households", fmt: pct },
};

/** Remaining losses after support: the post-Budget baseline next to the selected option.
 * Rendered by the Household effects tab; `ColumnChart`, `ExpandablePillRow`, `YearOptionPills`,
 * `MoreDetail`, `Legend` and `ChartValuesTable` come from Dashboard.jsx. */
export default function RemainingLossesSection({ fy, setFy, sel, setOpt, optionName, ui }) {
  const { ColumnChart, ExpandablePillRow, YearOptionPills, MoreDetail, Legend, ChartValuesTable, FallbackNote } = ui;
  const [breakdown, setBreakdown] = useState("decile");
  const [measure, setMeasure] = useState("worse_off_pct");
  const year = losses.years[fy];
  const base = year.scenarios.baseline;
  const opt = year.scenarios[sel.id] || base;
  const d = losses.definitions;
  const m = MEASURES[measure];
  const series = [
    { key: "base", label: "Post-Budget baseline", color: BASE },
    { key: "opt", label: `With ${optionName}`, color: WITH_OPTION },
  ];
  const optBy = Object.fromEntries((opt.by[breakdown] || []).map((g) => [g.group, g]));
  const groups = (base.by[breakdown] || []).map((g) => {
    const o = optBy[g.group] || {};
    return {
      label: g.group,
      base: g[measure] ?? 0,
      opt: o[measure] ?? 0,
      raw: { base: g, opt: o },
      tooltip: `${g.group}: baseline ${m.fmt(g[measure])}, with option ${m.fmt(o[measure])} (${g.records.toLocaleString("en-GB")} survey records)`,
    };
  });
  const maxVal = Math.max(1, ...groups.flatMap((g) => [g.base, g.opt])) * 1.15;
  const bandMap = Object.fromEntries(opt.bands.map((b) => [b.band, b.share_pct]));
  const bands = base.bands.map((b) => ({ label: b.band, base: b.share_pct, opt: bandMap[b.band] ?? 0 }));
  const jm = year.jan_mar;
  const p = (s, k) => s.loss_percentiles_worse_off?.[k];

  const rows = [
    ["Households still worse off", (s) => `${s.worse_off_m.toFixed(1)}m (${pct(s.worse_off_pct)})`],
    ["Median remaining loss, all households", (s) => fmt(s.median_loss)],
    ["Remaining loss of the worse-off: median", (s) => fmt(p(s, "p50"))],
    ["Remaining loss of the worse-off: 75th / 90th / 95th percentile", (s) => `${fmt(p(s, "p75"))} / ${fmt(p(s, "p90"))} / ${fmt(p(s, "p95"))}`],
    [`Energy costs above ${d.high_share_threshold_pct}% of income after housing costs`, (s) => pct(s.high_share_pct)],
    ["Median energy cost share of income after housing costs", (s) => pct(s.median_share_pct)],
    ["No positive income after housing costs (no share defined)", (s) => pct(s.no_income_after_housing_pct)],
  ];

  return (
    <div id="remaining-losses">
      <h2 className="section-heading">Remaining losses after support</h2>
      <p className="section-description">
        A household&apos;s <strong>remaining loss</strong> is its price rise against April–June 2026 cap rates in {fy}, minus the new
        support it receives. Cash payments and bill cuts count pound for pound. The baseline&apos;s new support is the Household Energy
        Payment; the electricity VAT extension is already in its bills.
      </p>
      <MoreDetail label="Definitions">
        <p className="section-description">
          Reference period: the same household&apos;s energy use priced for a whole year at April–June 2026 cap rates. A household is
          still worse off when its remaining loss is at least £{d.worse_off_threshold_gbp}. The Warm Home Discount was paid in both
          periods, so it does not change the loss.
        </p>
        <p className="section-description">
          Energy cost share: the energy bill minus energy support (the Household Energy Payment, the Warm Home Discount and the
          option&apos;s support), divided by HBAI household income after housing costs minus the energy support counted in it. This
          treats a payment and an equal bill cut the same. Households with no positive income after housing costs have no share and
          are shown separately. Medians and percentiles are left out for groups with fewer than {d.min_records_for_medians} survey
          records. HBAI poverty rates are a separate measure, shown with each option.
        </p>
      </MoreDetail>

      <div className="section-card">
        <div className="pill-rows">
          <YearOptionPills fy={fy} setFy={setFy} sel={sel} setOpt={setOpt} />
        </div>
        <FallbackNote sel={sel} fy={fy} setFy={setFy} />
        <div className="chart-values-scroll">
          <table className="scenario-table">
            <caption className="sr-only">Remaining losses, {fy}: post-Budget baseline and {optionName}</caption>
            <thead>
              <tr>
                <th scope="col">{fy}</th>
                <th scope="col" className="num">Post-Budget baseline</th>
                <th scope="col" className="num">With {optionName}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(([label, f]) => (
                <tr key={label}>
                  <th scope="row">{label}</th>
                  <td className="num">{f(base)}</td>
                  <td className="num">{f(opt)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <h3 className="chart-title" style={{ marginTop: 16 }}>Households by remaining loss</h3>
        <div className="chart-wrapper">
          <Legend series={series} />
          <ColumnChart
            data={bands}
            series={series}
            maxValue={Math.max(...bands.flatMap((b) => [b.base, b.opt])) * 1.15}
            formatValue={(v) => `${Math.round(v)}%`}
            yLabel="% of households"
            xLabel="Remaining loss, £ a year"
            wrapLabels
          />
          <ChartValuesTable
            caption={`Households by remaining loss, ${fy}`}
            rows={bands}
            columns={[
              { label: "Remaining loss", value: (b) => b.label },
              { label: "Baseline", value: (b) => pct(b.base) },
              { label: `With ${optionName}`, value: (b) => pct(b.opt) },
            ]}
          />
        </div>
      </div>

      <div className="section-card">
        <h3 className="chart-title">Who is still worse off</h3>
        <div className="pill-rows">
          <YearOptionPills fy={fy} setFy={setFy} sel={sel} setOpt={setOpt} />
          <ExpandablePillRow label="BREAKDOWN" options={BREAKDOWNS} value={breakdown} onChange={setBreakdown} />
          <ExpandablePillRow
            label="MEASURE"
            options={Object.entries(MEASURES).map(([k, v]) => ({ key: k, label: v.label }))}
            value={measure}
            onChange={setMeasure}
          />
        </div>
        <div className="chart-wrapper">
          <Legend series={series} />
          <ColumnChart
            data={groups}
            series={series}
            maxValue={maxVal}
            formatValue={m.fmt}
            yLabel={m.y}
            xLabel={BREAKDOWNS.find((b) => b.key === breakdown).label}
            wrapLabels
          />
          <p className="chart-sentence">Negative amounts are net gains and show as no bar; dashes mark groups with too few survey records.</p>
          <ChartValuesTable
            caption={`${m.label} by ${breakdown}, ${fy}`}
            rows={groups}
            columns={[
              { label: BREAKDOWNS.find((b) => b.key === breakdown).label, value: (g) => g.label },
              { label: "Survey records", value: (g) => g.raw.base.records.toLocaleString("en-GB") },
              { label: "Still worse off (baseline / option)", value: (g) => `${pct(g.raw.base.worse_off_pct)} / ${pct(g.raw.opt.worse_off_pct)}` },
              { label: "Median loss (baseline / option)", value: (g) => `${fmt(g.raw.base.median_loss)} / ${fmt(g.raw.opt.median_loss)}` },
              { label: "Average loss (baseline / option)", value: (g) => `${fmt(g.raw.base.mean_loss)} / ${fmt(g.raw.opt.mean_loss)}` },
              { label: "Energy costs >10% of income (baseline / option)", value: (g) => `${pct(g.raw.base.high_share_pct)} / ${pct(g.raw.opt.high_share_pct)}` },
            ]}
          />
        </div>
      </div>

      <div className="section-card">
        <h3 className="chart-title">January–March {fy.slice(0, 2)}{fy.slice(5)}</h3>
        <p className="section-description box-intro">
          Spending in the winter quarter, at the baseline&apos;s prices and seasonal use (57% of electricity and 75% of gas in
          October–March), against the same quarter at April–June 2026 rates. Spending only: payments are annual amounts and are not
          split by quarter. Across all households, January–March adds {fmt(jm.all.mean_extra_cost)} to the average bill
          (£{jm.all.total_extra_cost_bn.toFixed(2)}bn), {pct(jm.all.share_of_year_extra_cost_pct)} of the year&apos;s price rise.
        </p>
        <div className="pill-rows">
          <ExpandablePillRow label="BREAKDOWN" options={BREAKDOWNS} value={breakdown} onChange={setBreakdown} />
        </div>
        <div className="chart-values-scroll">
          <table className="scenario-table">
            <caption className="sr-only">January–March spending by {breakdown}, {fy}</caption>
            <thead>
              <tr>
                <th scope="col">{BREAKDOWNS.find((b) => b.key === breakdown).label}</th>
                <th scope="col" className="num">January–March bill</th>
                <th scope="col" className="num">Extra cost, average</th>
                <th scope="col" className="num">Extra cost, median</th>
                <th scope="col" className="num">Share of the year&apos;s rise</th>
              </tr>
            </thead>
            <tbody>
              {(jm.by[breakdown] || []).map((g) => (
                <tr key={g.group}>
                  <th scope="row">{g.group}</th>
                  <td className="num">{fmt(g.mean_bill)}</td>
                  <td className="num">{fmt(g.mean_extra_cost)}</td>
                  <td className="num">{fmt(g.median_extra_cost)}</td>
                  <td className="num">{pct(g.share_of_year_extra_cost_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
