import { useState, useEffect, useRef } from "react";
import pricePath from "../data/price_path.json";
import options from "../data/options.json";
import deciles from "../data/deciles.json";
import hhTypes from "../data/hh_types.json";
import regions from "../data/regions.json";
import provenance from "../data/provenance.json";
import { resolvePolicySelection, yearsForOption } from "../lib/policySelection";
import "./Dashboard.css";

const YEAR_OPTIONS = [
  { key: "2026-27", label: "2026-27" },
  { key: "2027-28", label: "2027-28" },
];

const ELEC = "#f59e0b";
const GAS = "#3b82f6";
// Reforms that cover Great Britain only (no Northern Ireland households).
const GB_ONLY = ["rf_targeted_discount", "whd_top_up", "extend_vat_cut", "remove_levies"];
const GB_ONLY_REASON = {
  rf_targeted_discount: "it is designed around the Ofgem price cap, which does not cover Northern Ireland",
  whd_top_up: "the Warm Home Discount is a Great Britain scheme with no Northern Ireland equivalent",
  extend_vat_cut: "the 0% VAT order (SI 2026/987) covers Great Britain only",
  remove_levies: "the Renewables Obligation and Feed-in Tariff levies are Great Britain schemes",
};
const SUPPORT = "#319795";
const PRICE_RISE = "#DD6B20";
const RISE_LABEL = "Forecast price rise";

const fmt = (v) => `£${Math.round(v).toLocaleString("en-GB")}`;

function ExpandablePillRow({ label, options, value, onChange }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const activeLabel = options.find((o) => o.key === value)?.label || value;

  useEffect(() => {
    if (!open) return;
    const handle = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, [open]);

  return (
    <div className="pill-row expandable" ref={ref}>
      <span className="pill-row-label">{label}</span>
      <button className="pill-row-collapsed" onClick={() => setOpen(!open)}>
        <span className="pill-row-active">{activeLabel}</span>
        <span className="pill-row-chevron">{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <div className="pill-row-dropdown">
          {options.map((o) => (
            <button
              key={o.key}
              className={`pill-row-option${value === o.key ? " active" : ""}`}
              onClick={() => { onChange(o.key); setOpen(false); }}
            >
              {o.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function niceTicks(maxValue, count = 5) {
  if (maxValue <= 0) return [0];
  const rough = maxValue / count;
  const mag = Math.pow(10, Math.floor(Math.log10(rough)));
  const residual = rough / mag;
  let step;
  if (residual <= 1.5) step = mag;
  else if (residual <= 3) step = 2 * mag;
  else if (residual <= 7) step = 5 * mag;
  else step = 10 * mag;
  const ticks = [];
  for (let v = 0; v <= maxValue; v += step) {
    ticks.push(Math.round(v * 1000) / 1000);
  }
  return ticks;
}

const Legend = ({ series }) => (
  <div className="col-chart-legend">
    {series.map((s) => <span key={s.key}><span className="col-chart-legend-dot" style={{ background: s.color }} />{s.label}</span>)}
  </div>
);

/** Column chart in the template's style, with one or two series per column. */
function ColumnChart({ data, series, maxValue, formatValue, yLabel, xLabel, onSelect, wrapLabels }) {
  const ticks = niceTicks(maxValue);
  const topTick = ticks[ticks.length - 1] || maxValue;
  const effectiveMax = Math.max(maxValue, topTick);

  return (
    <div className={`col-chart${wrapLabels ? " wrap-labels" : ""}`}>
      {yLabel && <div className="col-chart-y-label">{yLabel}</div>}
      <div className="col-chart-body">
        <div className="col-chart-y-axis">
          {[...ticks].reverse().map((t, i) => (
            <div className="col-chart-y-tick" key={i} style={{ bottom: `${(t / effectiveMax) * 100}%` }}>
              {formatValue(t)}
            </div>
          ))}
        </div>
        <div className="col-chart-area">
          {ticks.map((t, i) => (
            <div className="col-chart-gridline" key={i} style={{ bottom: `${(t / effectiveMax) * 100}%` }} />
          ))}
          <div className="col-chart-bars">
            {data.map((d, i) => {
              const valueText = d.tooltip || series.map((s) => `${s.label}: ${formatValue(d[s.key])}`).join(", ");
              const a11y = onSelect
                ? {
                    role: "button",
                    "aria-pressed": !!d.selected,
                    onKeyDown: (e) => {
                      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(d); }
                    },
                  }
                : { role: "img" };
              return (
              <div
                className="col-chart-col"
                key={i}
                tabIndex={0}
                aria-label={`${xLabel ? `${xLabel} ` : ""}${d.label}. ${valueText}`}
                {...a11y}
                onClick={onSelect ? () => onSelect(d) : undefined}
                style={onSelect ? { cursor: "pointer" } : undefined}
              >
                <div className="col-chart-tooltip" aria-hidden="true">
                  {d.tooltip || series.map((s) => `${s.label}: ${formatValue(d[s.key])}`).join(" | ")}
                </div>
                <div
                  className="col-chart-track"
                  style={series.length > 1 ? { display: "flex", gap: 2, alignItems: "flex-end" } : {}}
                >
                  {series.map((s) => (
                    <div
                      key={s.key}
                      className="col-chart-fill"
                      style={{
                        height: `${(Math.max(0, d[s.key]) / effectiveMax) * 100}%`,
                        background: s.colorFn ? s.colorFn(d) : s.color,
                        ...(series.length > 1 ? { flex: 1 } : {}),
                      }}
                    />
                  ))}
                </div>
                <div className="col-chart-label" aria-hidden="true">{d.label}</div>
              </div>
              );
            })}
          </div>
        </div>
      </div>
      {xLabel && <div className="col-chart-x-label">{xLabel}</div>}
    </div>
  );
}

/** Collapsible table of a chart's exact values, so they can be read without hovering. */
function ChartValuesTable({ caption, columns, rows }) {
  return (
    <details className="expandable-table chart-values">
      <summary>Show values</summary>
      <div className="chart-values-scroll">
        <table className="scenario-table">
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr>
              {columns.map((c, i) => <th key={c.label} scope="col" className={i && !c.text ? "num" : undefined}>{c.label}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, j) => (
              <tr key={j}>
                {columns.map((c, i) =>
                  i === 0
                    ? <th key={c.label} scope="row">{c.value(r)}</th>
                    : <td key={c.label} className={c.text ? "text" : "num"}>{c.value(r)}</td>,
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

const KIND_BANDS = {
  Announced: { fill: "#E6FFFA", text: "#285E61", label: "Announced by Ofgem", short: "Announced" },
  Forecast: { fill: "#FFF7ED", text: "#9A3412", label: "Forecast", short: "Forecast" },
  Assumed: { fill: "#F2F4F7", text: "#4B5563", label: "Assumed", short: "Held" },
};

const shortSource = (r) =>
  r.kind === "Announced" ? "Ofgem"
    : r.source.startsWith("Cornwall") ? "Cornwall Insight"
    : r.source.startsWith("Supplier") ? "Supplier average"
    : r.source.startsWith("OVO") ? "OVO"
    : "Held flat";

/** True when the viewport is at most `px` wide. False on the server and on first render. */
function useNarrow(px = 560) {
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${px}px)`);
    const update = () => setNarrow(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, [px]);
  return narrow;
}

/** Baseline prices over time. Background bands show whether each quarter is announced, forecast or
 * assumed; each quarter is labelled with its source. Lines are solid for announced quarters.
 * On phones the chart uses a narrower canvas with larger text and drops the per-quarter source links
 * (they stay in the "Show values" table). Each quarter is focusable and tappable to show its values. */
function PriceLineChart({ rows, series, formatValue, yLabel }) {
  const narrow = useNarrow();
  const W = narrow ? 420 : 1100, H = narrow ? 360 : 380;
  const ml = narrow ? 50 : 64, mr = narrow ? 6 : 16, mt = 36, mb = narrow ? 48 : 78;
  const fs = narrow ? 14 : 12;
  const all = rows.flatMap((r) => series.map((s) => r[s.key]));
  const hiRaw = Math.max(...all) * 1.1;
  const ticks = niceTicks(hiRaw);
  const hi = Math.max(hiRaw, ticks[ticks.length - 1]);
  const colW = (W - ml - mr) / rows.length;
  const x = (i) => ml + (i + 0.5) * colW;
  const y = (v) => mt + (1 - v / hi) * (H - mt - mb);
  const firstProjected = rows.findIndex((r) => r.kind !== "Announced");
  const [hover, setHover] = useState(null);

  // Contiguous runs of quarters with the same status.
  const bands = [];
  rows.forEach((r, i) => {
    const last = bands[bands.length - 1];
    if (last && last.kind === r.kind) last.end = i;
    else bands.push({ kind: r.kind, start: i, end: i });
  });

  const path = (key, from, to) =>
    rows.slice(from, to + 1).map((r, j) => `${j === 0 ? "M" : "L"}${x(from + j)},${y(r[key])}`).join(" ");

  const describe = (r) =>
    `${r.period}, ${r.kind.toLowerCase()}: ${series.map((s) => `${s.label} ${formatValue(r[s.key])}`).join(", ")}. Source: ${r.source}.`;

  return (
    <div className="col-chart" style={{ position: "relative" }}>
      <div className="col-chart-y-label">{yLabel}</div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="group" aria-label={`Baseline ${yLabel} by quarter`} style={{ overflow: "visible", fontFamily: "inherit" }}>
        {bands.map((b) => {
          const k = KIND_BANDS[b.kind];
          const x0 = ml + b.start * colW;
          const w = (b.end - b.start + 1) * colW;
          return (
            <g key={b.start} aria-hidden="true">
              <rect x={x0} y={mt - 28} width={w} height={H - mb - mt + 28} fill={k.fill} />
              <text
                x={narrow ? x0 + w / 2 : x0 + 10} y={mt - 10} textAnchor={narrow ? "middle" : "start"}
                fontSize={narrow && w < 60 ? 11 : 13} fontWeight="600" fill={k.text}
              >
                {narrow ? k.short : k.label}
              </text>
            </g>
          );
        })}
        {ticks.map((t) => (
          <g key={t} aria-hidden="true">
            <line x1={ml} x2={W - mr} y1={y(t)} y2={y(t)} stroke="#D1D5DB" strokeOpacity="0.7" />
            <text x={ml - 6} y={y(t)} dy="0.35em" textAnchor="end" fontSize={fs} fill="#4B5563">{formatValue(t)}</text>
          </g>
        ))}
        {series.map((s) => (
          <g key={s.key} aria-hidden="true">
            <path d={path(s.key, 0, Math.max(0, firstProjected - 1))} fill="none" stroke={s.color} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
            {firstProjected > 0 && (
              <path d={path(s.key, firstProjected - 1, rows.length - 1)} fill="none" stroke={s.color} strokeWidth="2.5" strokeDasharray="6 5" strokeLinejoin="round" strokeLinecap="round" />
            )}
            {rows.map((r, i) => (
              <g key={i}>
                <circle cx={x(i)} cy={y(r[s.key])} r={hover === i ? 5.5 : 4} fill={s.color} stroke="#fff" strokeWidth="1.5" />
                {series.length === 1 && (
                  <text x={x(i)} y={y(r[s.key]) - 12} textAnchor="middle" fontSize={narrow ? 11 : 12} fontWeight="600" fill="#1F2937">{formatValue(r[s.key])}</text>
                )}
              </g>
            ))}
          </g>
        ))}
        {rows.map((r, i) => {
          const [months, year] = r.period.split(" ");
          const [a, b] = narrow ? [months.split("–")[0], `’${year.slice(2)}`] : [months, year];
          return (
            <g key={r.period}>
              <text aria-hidden="true" x={x(i)} y={H - mb + 18} textAnchor="middle" fontSize={fs} fill="#344054" fontWeight="600">{a}</text>
              <text aria-hidden="true" x={x(i)} y={H - mb + 34} textAnchor="middle" fontSize={fs} fill="#4B5563">{b}</text>
              {!narrow && (
                <a href={r.link} target="_blank" rel="noopener noreferrer">
                  <text x={x(i)} y={H - mb + 56} textAnchor="middle" fontSize="11.5" fill={KIND_BANDS[r.kind].text} textDecoration="underline">{shortSource(r)}</text>
                </a>
              )}
              <rect
                className="price-chart-hit"
                x={x(i) - colW / 2} y={mt - 28} width={colW} height={H - mb - mt + 28} fill="transparent"
                tabIndex={0} role="img" aria-label={describe(r)}
                onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(i)} onBlur={() => setHover(null)}
                onClick={() => setHover(i)}
              />
            </g>
          );
        })}
      </svg>
      {hover != null && (
        <div
          className="col-chart-tooltip price-chart-tooltip"
          aria-hidden="true"
          style={{ left: narrow ? "50%" : `${(x(hover) / W) * 100}%` }}
        >
          <strong>{rows[hover].period}</strong> · {rows[hover].kind}<br />
          {series.map((s) => `${s.label}: ${formatValue(rows[hover][s.key])}`).join(", ")}<br />
          Electricity {rows[hover].elec_unit_p.toFixed(1)}p/kWh, gas {rows[hover].gas_unit_p.toFixed(1)}p/kWh<br />
          Source: {rows[hover].source}
        </div>
      )}
      <div className="col-chart-legend">
        {series.map((s) => (
          <span key={s.key}><span className="col-chart-legend-dot" style={{ background: s.color }} />{s.label}</span>
        ))}
        <span>Solid line: announced. Dashed: forecast or assumed.</span>
      </div>
    </div>
  );
}

function PriceSection() {
  const [metric, setMetric] = useState("bill");
  const rows = pricePath.map((r) => ({ ...r, label: r.period }));

  const withBills = rows.map((r) => ({
    ...r,
    elec_bill: (r.elec_unit_p * 2500 + r.elec_standing_p * 365) / 100,
    gas_bill: (r.gas_unit_p * 9500 + r.gas_standing_p * 365) / 100,
  }));
  const METRICS = {
    bill: {
      label: "Typical bill",
      yLabel: "£/yr, typical dual-fuel direct-debit bill",
      series: [{ key: "typical_bill", label: "Typical bill", color: "#319795" }],
      fmt: (v) => fmt(v),
    },
    split: {
      label: "Electricity and gas bills",
      yLabel: "£/yr, typical bill for each fuel",
      series: [
        { key: "elec_bill", label: "Electricity", color: ELEC },
        { key: "gas_bill", label: "Gas", color: GAS },
      ],
      fmt: (v) => fmt(v),
      columns: true,
    },
    unit: {
      label: "Unit rates",
      yLabel: "pence per kWh",
      series: [
        { key: "elec_unit_p", label: "Electricity", color: ELEC },
        { key: "gas_unit_p", label: "Gas", color: GAS },
      ],
      fmt: (v) => `${v.toFixed(0)}p`,
      exact: (v) => `${v.toFixed(2)}p`,
    },
    standing: {
      label: "Standing charges",
      yLabel: "pence per day",
      series: [
        { key: "elec_standing_p", label: "Electricity", color: ELEC },
        { key: "gas_standing_p", label: "Gas", color: GAS },
      ],
      fmt: (v) => `${v.toFixed(0)}p`,
      exact: (v) => `${v.toFixed(2)}p`,
    },
  };
  const m = METRICS[metric];

  return (
    <div id="baseline">
      <h2 className="section-heading">Baseline: energy prices over time</h2>
      <p className="section-description">
        The baseline is current law at forecast prices. <a href="https://www.ofgem.gov.uk/press-release/energy-price-cap-will-rise-4-october-2026" target="_blank" rel="noopener noreferrer">Ofgem has announced the cap</a> to December 2026
        (<a href="https://www.ofgem.gov.uk/your-energy-supply/your-energy-bill/energy-price-cap-unit-rates-and-standing-charges" target="_blank" rel="noopener noreferrer">unit rates and standing charges</a>); <a href="https://www.cornwall-insight.com/press-releases/16-price-cap-rise-forecast-in-january/" target="_blank" rel="noopener noreferrer">Cornwall Insight forecasts</a> January–March 2027,
        the <a href="https://www.moneysavingexpert.com/utilities/energy-price-cap-prediction/" target="_blank" rel="noopener noreferrer">average of EDF, British Gas and E.ON Next forecasts</a> covers April–September 2027,
        and <a href="https://www.ovoenergy.com/price-cap" target="_blank" rel="noopener noreferrer">OVO's forecast</a> covers October–December 2027. No forecaster publishes January–March 2028,
        so it is held at the October level. OVO quotes £1,846 with electricity VAT-free; under current law VAT returns
        to 5% in April 2027, which takes the bill to £1,890. Typical bills are on Ofgem's{" "}
        <a href="https://www.ofgem.gov.uk/sites/default/files/2026-05/Review%20of%20typical%20domestic%20consumption%20values%20decision.pdf" target="_blank" rel="noopener noreferrer">current typical consumption</a> (2,500 kWh electricity, 9,500 kWh gas).
      </p>

      <div className="section-card">
        <div className="pill-rows">
          <ExpandablePillRow
            label="SHOW"
            options={Object.entries(METRICS).map(([k, v]) => ({ key: k, label: v.label }))}
            value={metric}
            onChange={setMetric}
          />
        </div>
        <div className="chart-wrapper">
          {m.columns ? (
            <>
              <ColumnChart
                data={withBills.map((r) => ({ ...r, label: r.period }))}
                series={m.series}
                maxValue={Math.max(...withBills.map((r) => Math.max(r.elec_bill, r.gas_bill))) * 1.15}
                formatValue={m.fmt}
                yLabel={m.yLabel}
              />
              <div className="col-chart-legend">
                {m.series.map((x) => <span key={x.key}><span className="col-chart-legend-dot" style={{ background: x.color }} />{x.label}</span>)}
              </div>
            </>
          ) : (
            <PriceLineChart rows={withBills} series={m.series} formatValue={m.fmt} yLabel={m.yLabel} />
          )}
          <ChartValuesTable
            caption={`Baseline ${m.yLabel} by quarter`}
            rows={withBills}
            columns={[
              { label: "Quarter", value: (r) => r.period },
              ...m.series.map((s) => ({ label: s.label, value: (r) => (m.exact || m.fmt)(r[s.key]) })),
              { label: "Status", text: true, value: (r) => r.kind },
              { label: "Source", text: true, value: (r) => <a href={r.link} target="_blank" rel="noopener noreferrer">{r.source}</a> },
            ]}
          />
        </div>
      </div>

    </div>
  );
}

const POLICY_INFO = [
  {
    id: "rf_targeted_discount",
    name: "Targeted discount",
    summary: "£175 for lower-income households.",
    eligibility: "Households receiving a means-tested benefit, or whose highest individual income is under £24,000. Great Britain only.",
    how: "A discount on the household's gas and electricity bill, worth £175 a year on average in the flat version. Income is self-declared this winter and checked by HMRC later.",
    source: <>Resolution Foundation, <a href="https://www.resolutionfoundation.org/publications/billing-me-softly/" target="_blank" rel="noopener noreferrer">Billing me softly</a> (August 2026).</>,
    // MODEL-DISCLOSURE (c): simplified flat-payment illustration of RF's unit-rate discount.
    model: <>A simplified illustration, not RF's exact design: a flat £175 to every eligible household, assessed on annual income, with full take-up. RF discounts unit rates, activates by quarter, uses the previous three months' income and expects incomplete take-up. Counted in HBAI income by assumption, by analogy with the <a href="https://www.gov.uk/government/statistics/households-below-average-income-for-financial-years-ending-1995-to-2025/households-below-average-income-background-information-and-methodology-report-fye-2025" target="_blank" rel="noopener noreferrer">Warm Home Discount</a>.</>,
  },
  {
    id: "cost_of_living_payment",
    name: "£300 Cost of Living",
    summary: "One-off £300 on means-tested benefits.",
    eligibility: "Households receiving Universal Credit, Pension Credit, Housing Benefit, income-based JSA or ESA, or tax credits.",
    how: "A cash payment from DWP or HMRC, paid automatically with no application.",
    source: <>Follows the <a href="https://www.gov.uk/guidance/cost-of-living-payments-2023-to-2024" target="_blank" rel="noopener noreferrer">2022-24 Cost of Living Payments</a>.</>,
    model: "PolicyEngine UK's Cost of Living Payment parameter set to £300 for the year.",
  },
  {
    id: "whd_top_up",
    name: "Warm Home +£100",
    summary: "Raises the discount to £250.",
    eligibility: <>Households receiving a means-tested benefit (the Warm Home Discount's qualifying list): DESNZ estimates around 6 million recipient households across Great Britain in winter 2025/26 (<a href="https://assets.publishing.service.gov.uk/media/697b454bf8f4a746d9572efe/continuing-the-warm-home-discount-scheme-government-response.pdf#page=5" target="_blank" rel="noopener noreferrer">DESNZ, January 2026</a>); our 2026-27 proxy reaches about 7.8 million.</>,
    how: <>The <a href="https://www.gov.uk/the-warm-home-discount-scheme" target="_blank" rel="noopener noreferrer">Warm Home Discount</a> takes £150 off electricity bills each winter, funded by a levy on all bills. This adds £100, paid from taxation.</>,
    source: <>Reported as the Treasury's preferred option (<a href="https://www.ft.com/content/cfb7a7a9-90c2-4ed9-8b3b-e8477430d77f" target="_blank" rel="noopener noreferrer">Financial Times</a>, 11 October 2026: about £600m). <a href="https://www.citizensadvice.org.uk/about-us/media-centre/press-releases/more-than-a-third-of-brits-worried-about-affording-energy-bills-this-winter-warns-citizens-advice/" target="_blank" rel="noopener noreferrer">Citizens Advice</a> and <a href="https://www.energy-uk.org.uk/publications/economic-defence-tackling-energy-bills-in-winter-2026-27/" target="_blank" rel="noopener noreferrer">Energy UK</a> call for more support through the scheme.</>,
    // MODEL-DISCLOSURE (e): means-tested-household proxy for actual WHD recipients.
    model: <>£100 to every household where someone receives a listed means-tested benefit during the year. This is a proxy: actual recipients must also meet a qualifying date and have the claimant named on a participating supplier's electricity account (<a href="https://www.gov.uk/the-warm-home-discount-scheme/if-you-live-in-england-and-wales" target="_blank" rel="noopener noreferrer">England and Wales</a>, <a href="https://www.gov.uk/the-warm-home-discount-scheme/if-you-live-in-scotland" target="_blank" rel="noopener noreferrer">Scotland</a>). Counted in HBAI income, as DWP counts the Warm Home Discount.</>,
  },
  {
    id: "remove_levies",
    name: "Remove levies",
    summary: "£120 off a typical bill, all households.",
    eligibility: "Every household in Great Britain that pays for electricity.",
    how: "Moves the remaining policy costs on electricity bills (the last 25% of the Renewables Obligation and Feed-in Tariffs) to general taxation, cutting unit rates for everyone.",
    source: <>Proposed by the energy secretary (<a href="https://www.ft.com/content/cfb7a7a9-90c2-4ed9-8b3b-e8477430d77f" target="_blank" rel="noopener noreferrer">Financial Times</a>, 11 October 2026; the Guardian, 6 October 2026), up to £120 off bills at up to £3.2bn. <a href="https://www.energy-uk.org.uk/publications/economic-defence-tackling-energy-bills-in-winter-2026-27/" target="_blank" rel="noopener noreferrer">Energy UK</a> also calls for it.</>,
    model: "Costed from each household's electricity bill in Great Britain: a 12.6% cut, which takes £120 off the typical 2027-28 electricity bill. 2027-28 only.",
  },
  {
    id: "extend_vat_cut",
    name: "Extend VAT cut",
    summary: "0% VAT on electricity in 2027-28.",
    eligibility: "Every household in Great Britain that pays for electricity.",
    how: <>VAT on domestic electricity is 0% from October 2026 to March 2027 (<a href="https://www.legislation.gov.uk/uksi/2026/987/made" target="_blank" rel="noopener noreferrer">SI 2026/987</a>). This keeps it at 0% for 2027-28 instead of returning to 5%.</>,
    source: <><a href="https://www.gov.uk/government/news/new-pm-cuts-tax-on-household-electricity-bills-to-give-breathing-space-on-cost-of-living" target="_blank" rel="noopener noreferrer">UK Government</a>: longer-term measures to be decided at the Budget.</>,
    model: "Costed from each household's electricity bill in Great Britain (PolicyEngine UK has no domestic electricity VAT parameter). 2027-28 only.",
  },
  {
    id: "flat_400",
    name: "£400 to all",
    summary: "£400 off every household's bill.",
    eligibility: "Every household.",
    how: "A flat credit on the energy bill, paid through suppliers in monthly instalments.",
    source: <>Repeats the 2022 <a href="https://www.gov.uk/government/publications/energy-bills-support/energy-bills-support-factsheet-8-september-2022" target="_blank" rel="noopener noreferrer">Energy Bills Support Scheme</a>.</>,
    model: "PolicyEngine UK's energy bills credit parameter set to £400.",
  },
  {
    id: "cap_freeze",
    name: "Cap freeze",
    summary: "April–June 2026 tariffs restored.",
    eligibility: "Every household on a capped or comparable tariff.",
    how: "Electricity and gas unit rates and standing charges go back to their April–June 2026 levels, when the typical bill was £1,641; the government pays suppliers the difference.",
    source: <>Like the 2022-24 <a href="https://www.gov.uk/government/publications/energy-bills-support/energy-price-guarantee-up-until-30-june-2023" target="_blank" rel="noopener noreferrer">Energy Price Guarantee</a> (set at £2,500). <a href="https://ippr-org.files.svdcdn.com/production/Downloads/Price_caps_and_economic_stability_May26.pdf" target="_blank" rel="noopener noreferrer">IPPR</a> proposes a cap that switches on at £2,000.</>,
    // MODEL-DISCLOSURE (b): unit rates and standing charges held at April–June 2026 levels.
    model: <>Electricity and gas unit rates and standing charges held at their April–June 2026 levels (<a href="https://www.ofgem.gov.uk/your-energy-supply/your-energy-bill/energy-price-cap-unit-rates-and-standing-charges" target="_blank" rel="noopener noreferrer">Ofgem</a>), with the government paying the difference. All households are treated as on capped tariffs.</>,
  },
];

const optionYears = (id) => yearsForOption(options, id);
const policyName = (id) => POLICY_INFO.find((p) => p.id === id)?.name || options.find((o) => o.option_id === id)?.option || id;

/** Shown wherever results are plotted when the selected option has no result in the selected year. */
function FallbackNote({ sel, fy, setFy }) {
  if (!sel.isFallback || !sel.id) return null;
  const years = sel.requestedYears;
  return (
    <div className="policy-note fallback-note" role="status">
      <strong>{policyName(sel.requestedId)} has no result for {fy}</strong>
      {years.length ? <> (it is modelled for {years.join(" and ")} only)</> : null}. The charts and details
      show {policyName(sel.id)} instead.{" "}
      {years.length > 0 && (
        <button type="button" className="link-button" onClick={() => setFy(years[years.length - 1])}>
          Switch to {years[years.length - 1]}
        </button>
      )}
    </div>
  );
}

function PolicyOptionsSection({ sel, setOpt, fy }) {
  const info = POLICY_INFO.find((p) => p.id === sel.id) || POLICY_INFO[0];
  const anyUnavailable = POLICY_INFO.some((p) => !sel.availableIds.includes(p.id));
  return (
    <div id="policies">
      <h2 className="section-heading">The policy options</h2>
      <p className="section-description">
        Seven options drawn from published proposals, reported government plans and past support schemes. Click an option to see who is
        eligible, how it works and where it was proposed; the charts below and on the Household effects tab follow the option you select.
        {anyUnavailable && <> Options marked with a year are modelled for that year only, so cannot be selected for {fy}.</>}
      </p>
      <div className="policy-grid">
        {POLICY_INFO.map((p) => {
          const available = sel.availableIds.includes(p.id);
          const onlyIn = optionYears(p.id);
          return (
            <button
              type="button"
              key={p.id}
              className={`policy-box${p.id === info.id ? " active" : ""}${available ? "" : " unavailable"}`}
              onClick={() => available && setOpt(p.id)}
              aria-pressed={p.id === info.id}
              aria-disabled={!available}
              title={available ? undefined : `No result for ${fy}`}
            >
              <span className="policy-box-name">{p.name}</span>
              <span className="policy-box-summary">{p.summary}</span>
              {!available && onlyIn.length > 0 && <span className="policy-box-tag">{onlyIn.join(", ")} only</span>}
            </button>
          );
        })}
      </div>
      <div className="section-card policy-detail">
        <h3 className="chart-title">{info.name}</h3>
        <table className="scenario-table">
          <tbody>
            <tr><th scope="row">Who is eligible</th><td>{info.eligibility}</td></tr>
            <tr><th scope="row">How it works</th><td>{info.how}</td></tr>
            <tr><th scope="row">Where it was proposed</th><td>{info.source}</td></tr>
            <tr><th scope="row">How we model it</th><td>{info.model}</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

function BudgetSection({ fy, setFy, sel, setOpt }) {
  const [metric, setMetric] = useState("cost");
  const rows = options.filter((o) => o.fy === fy);
  const METRICS = {
    cost: {
      label: "Cost to the Exchequer",
      y: "£bn a year",
      series: [{ key: "cost_bn", label: "Cost" }],
      fmt: (v) => `£${Number(v).toFixed(v < 10 && v % 1 ? 1 : 0)}bn`,
      exact: (v) => `£${Number(v).toFixed(2)}bn`,
      sort: "cost_bn",
    },
    avg: {
      label: "Average gain per household",
      y: "£/yr per household, all households",
      series: [{ key: "avg_per_household", label: "Average gain" }],
      fmt: (v) => fmt(v),
      sort: "avg_per_household",
    },
    reach: {
      label: "Households helped",
      y: "% of households receiving support",
      series: [{ key: "share_receiving_pct", label: "Households helped" }],
      fmt: (v) => `${Math.round(v)}%`,
      exact: (v) => `${Number(v).toFixed(1)}%`,
      sort: "share_receiving_pct",
    },
  };
  const m = METRICS[metric];
  const data = [...rows]
    .sort((a, b) => b[m.sort] - a[m.sort])
    .map((r) => ({ ...r, label: r.option, selected: r.option_id === sel.id }));
  const maxVal = Math.max(...data.flatMap((r) => m.series.map((x) => r[x.key]))) * 1.15;
  const series = [{ ...m.series[0], colorFn: (d) => (d.option_id === sel.id ? SUPPORT : "#94a3b8") }];

  return (
    <div id="budget">
      <h2 className="section-heading">Budget responses: cost and reach</h2>
      <p className="section-description">
        Four options are payments simulated as <a href="https://pypi.org/project/policyengine/" target="_blank" rel="noopener noreferrer">PolicyEngine</a> reforms against the {fy} baseline
        (targeted discount, Cost of Living Payment, Warm Home Discount top-up and £400 credit); their cost is the
        change in household net income summed over all households. Three are price reductions calculated
        directly from each household's bills (cap freeze, VAT extension and levy removal); their cost is the
        total reduction in bills. Gains are averaged per household.
        The selected option is highlighted; select a column to change it.
      </p>

      <div className="section-card">
        <div className="pill-rows">
          <ExpandablePillRow label="FINANCIAL YEAR" options={YEAR_OPTIONS} value={fy} onChange={setFy} />
          <ExpandablePillRow
            label="SHOW"
            options={Object.entries(METRICS).map(([k, v]) => ({ key: k, label: v.label }))}
            value={metric}
            onChange={setMetric}
          />
        </div>
        <FallbackNote sel={sel} fy={fy} setFy={setFy} />
        <div className="chart-wrapper">
          <ColumnChart
            data={data}
            series={series}
            maxValue={maxVal}
            formatValue={m.fmt}
            yLabel={m.y}
            xLabel="Option"
            wrapLabels
            onSelect={(d) => setOpt(d.option_id)}
          />
          <ChartValuesTable
            caption={`${m.label} by option, ${fy}`}
            rows={data}
            columns={[
              { label: "Option", value: (r) => (r.selected ? <>{r.option} (selected)</> : r.option) },
              { label: "Cost", value: (r) => METRICS.cost.exact(r.cost_bn) },
              { label: "Average gain", value: (r) => fmt(r.avg_per_household) },
              { label: "Households helped", value: (r) => METRICS.reach.exact(r.share_receiving_pct) },
            ]}
          />
        </div>
      </div>

    </div>
  );
}

const DECILE_LINK = "https://github.com/PolicyEngine/policyengine-uk/blob/2.125.1/policyengine_uk/variables/household/income/household_income_decile.py";

function HouseholdSection({ fy, setFy, sel, setOpt }) {
  const [measure, setMeasure] = useState("gbp");
  const [breakdown, setBreakdown] = useState("hh_type");
  const rows = options.filter((o) => o.fy === fy);
  const o = rows.find((r) => r.option_id === sel.id) || rows[0];
  const id = o.option_id;
  const info = POLICY_INFO.find((p) => p.id === id);
  const MEASURES = {
    gbp: { label: "£ per year", fmt: (v) => fmt(v), exact: (v) => fmt(v), y: "£/yr per household", val: (d, k = id) => d[k] },
    income: { label: "% of net income", fmt: (v) => `${v.toFixed(2)}%`, exact: (v) => `${v.toFixed(2)}%`, y: "% of household net income", val: (d, k = id) => (d[k] / d.net_income) * 100 },
    bill: { label: "% of energy bill", fmt: (v) => `${v.toFixed(0)}%`, exact: (v) => `${v.toFixed(1)}%`, y: "% of baseline energy bill", val: (d, k = id) => (d[k] / d.bill) * 100 },
  };
  const ms = MEASURES[measure];
  const decRows = deciles.filter((d) => d.fy === fy);
  const dec = decRows.map((d) => ({ label: `${d.decile}`, gain: ms.val(d), rise: ms.val(d, "extra_cost"), raw: d }));
  const seriesPair = [
    { key: "rise", label: `${RISE_LABEL} (baseline)`, color: PRICE_RISE },
    { key: "gain", label: o.option, color: SUPPORT },
  ];
  const groups = (breakdown === "region" ? regions.map((r) => ({ ...r, name: r.region })) : hhTypes.map((h) => ({ ...h, name: h.hh_type })))
    .filter((h) => h.fy === fy)
    .sort((a, b) => b[id] - a[id]);
  const maxVal = Math.max(...dec.flatMap((d) => [d.gain, d.rise])) * 1.15 || 1;
  const notCovered = (h) => h.name === "Northern Ireland" && GB_ONLY.includes(id);

  return (
    <div id="households">
      <h2 className="section-heading">Household effects</h2>
      <p className="section-description">
        The average gain from the selected reform against the {`${fy} baseline`}, by income decile, next to the
        forecast price rise it offsets: how much more the same household pays for the same electricity and gas at
        the {fy} forecast prices than at April–June 2026 prices (see the price chart in Budget responses). The
        comparison assumes April–June 2026 Ofgem cap rates would otherwise have stayed flat for the whole year: no
        inflation trend or alternative price forecast is applied, and each household&apos;s energy use is the same in
        both. Deciles are
        PolicyEngine&apos;s <a href={DECILE_LINK} target="_blank" rel="noopener noreferrer">household income decile</a>:
        households are ranked by equivalised household net income before housing costs, as in DWP&apos;s Households
        Below Average Income statistics, and split into ten groups with equal numbers of people (each household
        counts once per member). Households with negative income are left out of the ten deciles. Each column is
        the average gain per household in that decile, weighting each household once: a household-weighted
        average within person-weighted deciles.
      </p>

      <div className="section-card">
        <div className="pill-rows">
          <ExpandablePillRow label="FINANCIAL YEAR" options={YEAR_OPTIONS} value={fy} onChange={setFy} />
          <ExpandablePillRow
            label="REFORM"
            options={rows.map((r) => ({ key: r.option_id, label: r.option }))}
            value={id}
            onChange={setOpt}
          />
          <ExpandablePillRow
            label="MEASURE"
            options={Object.entries(MEASURES).map(([k, v]) => ({ key: k, label: v.label }))}
            value={measure}
            onChange={setMeasure}
          />
        </div>
        <FallbackNote sel={sel} fy={fy} setFy={setFy} />
        {info && (
          <div className="policy-note">
            <strong>{info.name}:</strong> {info.summary} <span className="policy-note-eligibility">Eligible: {info.eligibility}</span>
          </div>
        )}
        <div className="chart-wrapper">
          <Legend series={seriesPair} />
          <ColumnChart
            data={dec}
            series={seriesPair}
            maxValue={maxVal}
            formatValue={ms.fmt}
            yLabel={ms.y}
            xLabel="Income decile"
          />
          <ChartValuesTable
            caption={`${o.option}: average gain by income decile, ${fy}`}
            rows={dec}
            columns={[
              { label: "Income decile", value: (d) => d.label },
              { label: "Price rise, £/yr", value: (d) => fmt(d.raw.extra_cost) },
              { label: "Gain, £/yr", value: (d) => fmt(d.raw[id]) },
              { label: "% of net income", value: (d) => MEASURES.income.exact(MEASURES.income.val(d.raw)) },
              { label: "% of energy bill", value: (d) => MEASURES.bill.exact(MEASURES.bill.val(d.raw)) },
            ]}
          />
        </div>
      </div>

      <div className="section-card">
        <h3 className="chart-title">{breakdown === "region" ? "By region" : "By household type"}</h3>
        <div className="pill-rows">
          <ExpandablePillRow
            label="BREAKDOWN"
            options={[{ key: "hh_type", label: "Household type" }, { key: "region", label: "Region" }]}
            value={breakdown}
            onChange={setBreakdown}
          />
        </div>
        <div className="chart-wrapper">
          <Legend series={seriesPair} />
          <ColumnChart
            data={groups.map((h) => ({
              label: h.name,
              gain: h[id],
              rise: h.extra_cost,
              tooltip: notCovered(h)
                ? `Price rise ${fmt(h.extra_cost)} a year; not covered: ${o.option} applies in Great Britain only`
                : `Price rise ${fmt(h.extra_cost)} a year; gain ${fmt(h[id])} a year, ${((h[id] / h.bill) * 100).toFixed(0)}% of a ${fmt(h.bill)} baseline energy bill`,
            }))}
            series={seriesPair}
            maxValue={Math.max(...groups.flatMap((h) => [h[id], h.extra_cost])) * 1.15 || 1}
            formatValue={(v) => fmt(v)}
            yLabel="£/yr per household"
            xLabel={breakdown === "region" ? "Region" : "Household type"}
            wrapLabels
          />
          <ChartValuesTable
            caption={`${o.option}: average gain by ${breakdown === "region" ? "region" : "household type"}, ${fy}`}
            rows={groups}
            columns={[
              { label: breakdown === "region" ? "Region" : "Household type", value: (h) => h.name },
              { label: "Price rise, £/yr", value: (h) => fmt(h.extra_cost) },
              { label: "Gain, £/yr", value: (h) => (notCovered(h) ? "£0 (not covered)" : fmt(h[id])) },
              { label: "Baseline bill", value: (h) => fmt(h.bill) },
              { label: "% of bill", value: (h) => `${((h[id] / h.bill) * 100).toFixed(1)}%` },
            ]}
          />
        </div>
        <p className="section-description" style={{ marginTop: 12 }}>
          Average price rise and gain over all households in each group, including those the reform does not reach.

          {" "}Northern Ireland is outside the Ofgem cap, so GB prices are used as a proxy for its bills.
        </p>
        {breakdown === "region" && GB_ONLY.includes(id) && (
          <div className="policy-note" style={{ marginTop: 12 }}>
            <strong>Great Britain only.</strong> {o.option} applies in England, Scotland and Wales, so Northern
            Ireland shows £0: {GB_ONLY_REASON[id]}.
          </div>
        )}
      </div>
    </div>
  );
}


const Fn = ({ n }) => <a href={`#fn-${n}`}><sup>{n}</sup></a>;

const REFERENCES = [
  ["Ofgem, “Energy price cap unit rates and standing charges” and quarterly cap announcements, 2025–2026.", "https://www.ofgem.gov.uk/your-energy-supply/your-energy-bill/energy-price-cap-unit-rates-and-standing-charges"],
  ["Ofgem, “Energy price cap will rise by 4% from October 2026”, 26 August 2026.", "https://www.ofgem.gov.uk/press-release/energy-price-cap-will-rise-4-october-2026"],
  ["Cornwall Insight, “16% price cap rise forecast in January”, 30 September 2026.", "https://www.cornwall-insight.com/press-releases/16-price-cap-rise-forecast-in-january/"],
  ["MoneySavingExpert, average of EDF, British Gas and E.ON Next price cap predictions, 6–7 October 2026.", "https://www.moneysavingexpert.com/utilities/energy-price-cap-prediction/"],
  ["Ofgem, “Review of typical domestic consumption values: decision”, 27 May 2026.", "https://www.ofgem.gov.uk/sites/default/files/2026-05/Review%20of%20typical%20domestic%20consumption%20values%20decision.pdf"],
  ["The Value Added Tax (Supplies of Domestic Electricity) Order 2026, SI 2026/987.", "https://www.legislation.gov.uk/uksi/2026/987/made"],
  ["PolicyEngine Microcosm, issue #1113: the price basis of domestic electricity and gas spending.", "https://github.com/PolicyEngine/microcosm/issues/1113"],
  ["Resolution Foundation, “Billing me softly”, 10 August 2026.", "https://www.resolutionfoundation.org/publications/billing-me-softly/"],
  ["DWP, Households Below Average Income: background information and methodology report, FYE 2025.", "https://www.gov.uk/government/statistics/households-below-average-income-for-financial-years-ending-1995-to-2025/households-below-average-income-background-information-and-methodology-report-fye-2025"],
  ["Priesmann, J. and Praktiknjo, A. (2025), income-specific price elasticities of household energy demand, as used in PolicyEngine's energy price shock analysis.", "https://github.com/PolicyEngine/energy-price-shock"],
  ["Office for Budget Responsibility, “Autumn 2026 forecast date announced”, 31 July 2026.", "https://obr.uk/autumn-2026-forecast-date-announced/"],
  ["policyengine.py release on PyPI.", "https://pypi.org/project/policyengine/"],
  ["OVO, “Energy price cap” forecast table, 7 October 2026.", "https://www.ovoenergy.com/price-cap"],
  ["Ofgem, price cap methodology appendix 4: wholesale costs (winter shares of annual demand, page 6), November 2018.", "https://www.ofgem.gov.uk/sites/default/files/docs/2018/11/appendix_4_-_wholesale_costs.pdf#page=6"],
  ["PolicyEngine UK 2.125.1, household_income_decile variable definition.", "https://github.com/PolicyEngine/policyengine-uk/blob/2.125.1/policyengine_uk/variables/household/income/household_income_decile.py"],
];

/* Sentences marked MODEL-DISCLOSURE (a)–(e) describe the corrected model from the publication review
 * (PolicyEngine/uk-energy-autumn-budget#1). Edit them in one place if the model's final method differs. */
function MethodologySection() {
  const pv = provenance;
  return (
    <div className="tab-content">
      <div className="section-card">
        <h2 className="section-heading">How the model works</h2>
        <p className="section-description">
          We use policyengine.py {pv.policyengine_version} (policyengine-uk {pv.model_version})<Fn n={12} /> on
          Microcosm UK 2024-25, PolicyEngine's calibrated household dataset of 29.3m UK households. The release
          we use ({pv.dataset_release}) is not yet in the policyengine.py certified bundle, so we pin it by its
          SHA-256 hash. Microcosm prices each household's energy use at DESNZ Quarterly Energy Prices for 2024-25
          (regional unit cost plus standing charge), then calibrates household weights to ONS 2025 spending,
          so each household's spending implies its annual kWh.<Fn n={7} />
        </p>
        <p className="section-description">
          The baseline is current law at forecast prices. Ofgem's announced caps set prices to December
          2026,<Fn n={2} /> Cornwall Insight's forecast sets January–March 2027,<Fn n={3} /> the average of
          supplier forecasts sets April–September 2027,<Fn n={4} /> and OVO's forecast sets October–December
          2027.<Fn n={13} /> No forecaster publishes January–March 2028, so it is held at the October level. OVO's
          figures keep electricity VAT-free, so we add the 5% VAT that current law restores in April 2027. Because Ofgem cut its typical consumption
          values on 1 July 2026,<Fn n={5} /> we cost every quarter from its unit rates and standing charges rather
          than from headline cap figures, and take electricity and gas separately. Supplier forecasts give no
          split between the two fuels, so we scale Cornwall Insight's January unit rates to each forecast total.
          VAT on domestic electricity is 0% from October 2026 to March 2027 and returns to 5% from April
          2027.<Fn n={6} />
        </p>
        <p className="section-description">
          {/* MODEL-DISCLOSURE (a): kWh conversion, separate standing charges, seasonal profile. */}
          A bill is a unit rate per kWh plus a fixed daily standing charge, so a price rise changes small and
          large users' bills by different percentages.<Fn n={1} /> We therefore convert each household's
          electricity and gas spending into annual kWh, net of standing charges, at the 2024-25 prices Microcosm
          used, then re-cost that consumption at each quarter's unit rates, adding each quarter's standing charges
          separately. Consumption is spread across quarters with a seasonal demand profile, so winter quarters,
          when gas use and prices are highest, carry more weight; the profile follows Ofgem's published winter
          shares of annual demand.<Fn n={14} /> About 10% of households have electricity spending equal to the
          standing charge in Microcosm, so they have no measured use and only their standing charges change;
          this understates their bill change.
        </p>
        <p className="section-description">
          {/* MODEL-DISCLOSURE (d): all households on capped variable tariffs. */}
          Every household is modelled as paying the capped standard variable tariff. In practice around 35% of
          households are on fixed tariffs and will not see the October 2026 cap rise until their contracts
          end;<Fn n={2} /> we do not model tariff type, payment method or contract expiry. The baseline is
          therefore a scenario in which all households face cap prices, not a forecast of what each household
          will pay.
        </p>
        <p className="section-description">
          The four payment options (targeted discount, Cost of Living Payment, Warm Home Discount top-up and
          £400 credit) are PolicyEngine reforms run against that baseline on the same households; their cost is
          the change in household net income summed over all households. The three price reductions (cap
          freeze, VAT extension and levy removal) are calculated directly from each household's modelled bills,
          outside the PolicyEngine reform engine; their cost is the total reduction in bills. Household gains
          are averaged by income decile or household type. Income deciles are PolicyEngine's household
          income decile:<Fn n={15} /> households ranked by equivalised net income before housing costs and split
          into tenths of people, with negative-income households left out. The Cost of Living Payment and £400
          payment use PolicyEngine UK's own parameters.
          {/* MODEL-DISCLOSURE (b): cap freeze holds unit rates and standing charges. */}
          {" "}The cap freeze holds electricity and gas unit rates and standing charges at their April–June 2026
          levels, when the typical bill was £1,641, and the government pays suppliers the difference from
          forecast prices.
          {/* MODEL-DISCLOSURE (c): RF option is a simplified flat-payment illustration. */}
          {" "}The targeted discount is a simplified illustration of the Resolution Foundation's
          proposal.<Fn n={8} /> RF discounts unit rates, switches on by quarter, assesses the previous three
          months' income and expects incomplete take-up; we instead pay a flat £175, RF's average for eligible
          households, to every household on a means-tested benefit or whose highest individual income is under
          £24,000, assessed on annual income, with full take-up. It is implemented as a PolicyEngine UK reform
          taken from PolicyEngine's uk-energy-reforms repository.
          {/* MODEL-DISCLOSURE (e): WHD option is a means-tested-household proxy. */}
          {" "}The Warm Home Discount top-up pays £100 to every household where someone receives a qualifying
          means-tested benefit during the year. This is a proxy for actual recipients, who must also meet a
          qualifying date and have the claimant named on a participating supplier's electricity account
          (<a href="https://www.gov.uk/the-warm-home-discount-scheme/if-you-live-in-england-and-wales" target="_blank" rel="noopener noreferrer">England and Wales</a>;{" "}
          <a href="https://www.gov.uk/the-warm-home-discount-scheme/if-you-live-in-scotland" target="_blank" rel="noopener noreferrer">Scotland</a> has
          further group and application rules). PolicyEngine UK has no parameter for VAT on domestic
          electricity, so the VAT extension and levy removal are costed directly from each household's
          electricity bill in Great Britain.
        </p>
        <p className="section-description">
          Poverty is relative poverty: people in households below 60% of median equivalised HBAI income, the
          DWP headline measure (PolicyEngine UK's relative poverty variables). Absolute poverty against a fixed
          2024-25 line is also in the published data. HBAI income does not net off energy bills, so bill
          support counts only where it is treated as income. DWP counts the Warm Home Discount, although it is a
          bill credit, as miscellaneous income in HBAI.<Fn n={9} /> By scheme:
        </p>
        <ul className="section-description method-list">
          <li><strong>Warm Home Discount top-up:</strong> counted, as DWP counts the Warm Home Discount.<Fn n={9} /></li>
          <li><strong>£300 Cost of Living Payment:</strong> counted, as a cash benefit payment.</li>
          <li><strong>Targeted discount (RF):</strong> counted by assumption. HBAI has no rule for this new discount;
            we extrapolate from DWP's treatment of the Warm Home Discount.</li>
          <li><strong>£400 bill credit, cap freeze, VAT cut and levy removal:</strong> not counted, so they show no
            change in poverty even when they cut household costs.</li>
        </ul>
        <p className="section-description">
          Microcosm matches official energy spending and household counts
          closely (£42.2bn on electricity and gas in 2025 against the ONS's £41.9bn; 29.0m households in 2024
          against 28.6m), but puts relative poverty after housing costs at 18.3% of people and 23.4% of people under 18
          in 2024-25, against DWP's 20% of people and 27% of children. DWP's child count covers dependent children,
          including some 16–19-year-olds in full-time education, so our under-18 rate is not directly comparable
          with its child headline. PolicyEngine's previous enhanced FRS dataset gives 21.2% and 31.0% (under 18)
          but overstates energy spending at £51bn. We report Microcosm's poverty rates as
          computed and do not use them to rank the options.
        </p>
      </div>

      <div className="section-card">
        <h2 className="section-heading">Behavioural responses</h2>
        <p className="section-description">
          This is a static scenario: households use the same amount of electricity and gas at forecast prices as
          at April–June 2026 prices, and none of the reforms changes how much they use. In practice households
          cut use when prices rise; PolicyEngine's energy price shock analysis estimates short-run price
          elasticities from −0.64 in income decile 1 to −0.11 in income decile 10,<Fn n={10} /> which we do not
          apply. The VAT extension and levy removal are proportional to electricity spending, so 10% less
          electricity spending means 10% lower costs for both. The cap freeze has two parts: a usage part that
          falls in proportion to use, and the change in standing charges, which does not depend on use and can be
          positive or negative. How its cost responds to lower use therefore depends on each household's use, the
          sign of its standing-charge difference and the zero floor. The flat payments (£400 credit, Cost of Living
          Payment, Warm Home Discount top-up and the targeted discount as modelled) do not depend on use. We do
          not treat the baseline bills as an upper bound, because tariff type and contract timing are not
          modelled.
        </p>
        <p className="section-description">
          We also hold incomes and benefits fixed. Higher energy prices raise CPI inflation, which sets the
          following April's benefit uprating; that link is not modelled. Northern Ireland, which the Ofgem cap
          does not cover, uses GB prices as a proxy. The Autumn Budget and the OBR's next forecast are both due on
          28 October 2026;<Fn n={11} /> the OBR's March 2026 forecast closed before energy prices rose.
        </p>

        <div className="chart-title" style={{ marginTop: 24, marginBottom: 12 }}>Sources</div>
        <ol className="ref-list">
          {REFERENCES.map(([text, href], i) => (
            <li id={`fn-${i + 1}`} key={href}>
              {text}{" "}
              <a href={href} target="_blank" rel="noopener noreferrer">{new URL(href).hostname.replace("www.", "")}</a>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

const TAB_OPTIONS = [
  { id: "budget", label: "Budget responses" },
  { id: "households", label: "Household effects" },
  { id: "methodology", label: "Methodology" },
];

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState("budget");
  const [fy, setFy] = useState("2027-28");
  // One requested option shared by both tabs; it lives here so it survives tab switches. It is
  // resolved against the financial year on every render (see src/lib/policySelection.js).
  const [opt, setOpt] = useState("rf_targeted_discount");
  const sel = resolvePolicySelection(opt, fy, options);

  return (
    <div className="app-shell">
      <header className="title-row">
        <div className="title-row-inner">
          <h1>Energy bills and the Autumn Budget 2026</h1>
        </div>
      </header>

      <main className="main-content">
        <p className="intro-text">
          This dashboard uses PolicyEngine to estimate what UK households will pay for gas and electricity in
          2026-27 and 2027-28 at the prices Ofgem has announced and forecasters expect, and what support
          options ahead of the Autumn Budget on 28 October 2026 would cost and who they would reach. The
          baseline is current law at forecast prices, and each option is modelled as a reform against it.
          Proposals include a targeted energy discount (<a href="https://www.resolutionfoundation.org/publications/billing-me-softly/" target="_blank" rel="noopener noreferrer">Resolution Foundation</a>),
          a social tariff with policy costs moved off bills (<a href="https://www.resolutionfoundation.org/publications/power-struggle/" target="_blank" rel="noopener noreferrer">Resolution Foundation</a>),
          a discounted essential block of energy (<a href="https://www.jrf.org.uk/cost-of-living/addressing-the-2026-energy-price-crisis" target="_blank" rel="noopener noreferrer">Joseph Rowntree Foundation</a>),
          a temporary cap on bills (<a href="https://ippr-org.files.svdcdn.com/production/Downloads/Price_caps_and_economic_stability_May26.pdf" target="_blank" rel="noopener noreferrer">IPPR</a>),
          a reformed Warm Home Discount and debt relief (<a href="https://www.citizensadvice.org.uk/about-us/media-centre/press-releases/more-than-a-third-of-brits-worried-about-affording-energy-bills-this-winter-warns-citizens-advice/" target="_blank" rel="noopener noreferrer">Citizens Advice</a>, <a href="https://www.energy-uk.org.uk/publications/economic-defence-tackling-energy-bills-in-winter-2026-27/" target="_blank" rel="noopener noreferrer">Energy UK</a>, <a href="https://www.nea.org.uk/wp-content/uploads/2026/06/Clearing-the-Decks-Tackling-Energy-Debt-to-Lower-Bills-1.pdf" target="_blank" rel="noopener noreferrer">National Energy Action</a>),
          and the government's removal of VAT from electricity bills (<a href="https://www.gov.uk/government/news/new-pm-cuts-tax-on-household-electricity-bills-to-give-breathing-space-on-cost-of-living" target="_blank" rel="noopener noreferrer">UK Government</a>).
          The <strong>Budget responses</strong> tab shows baseline energy prices over time and the cost and
          reach of seven options; <strong>Household effects</strong> shows the
          gain by income decile and household type; and <strong>Methodology</strong> explains the modelling,
          assumptions and sources.
        </p>

        <div className="tab-bar">
          {TAB_OPTIONS.map((tab) => (
            <button
              key={tab.id}
              className={`tab-button ${activeTab === tab.id ? "active" : ""}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {activeTab === "budget" && (
          <div className="tab-content">
            <PriceSection />
            <hr className="section-divider" />
            <PolicyOptionsSection sel={sel} setOpt={setOpt} fy={fy} />
            <hr className="section-divider" />
            <BudgetSection fy={fy} setFy={setFy} sel={sel} setOpt={setOpt} />
          </div>
        )}
        {activeTab === "households" && (
          <div className="tab-content">
            <HouseholdSection fy={fy} setFy={setFy} sel={sel} setOpt={setOpt} />
          </div>
        )}
        {activeTab === "methodology" && <MethodologySection />}

        <footer className="dashboard-footer">
          <p>
            Replication code:{" "}
            <a href="https://github.com/PolicyEngine/uk-energy-autumn-budget" target="_blank" rel="noopener noreferrer">
              PolicyEngine/uk-energy-autumn-budget
            </a>
            {" · "}
            <a href={`https://pypi.org/project/policyengine/${provenance.policyengine_version}/`} target="_blank" rel="noopener noreferrer">
              policyengine.py {provenance.policyengine_version}
            </a>
            {" "}(policyengine-uk {provenance.model_version}) · Microcosm UK {provenance.dataset.replace(".h5", "").replace("microcosm_uk_", "")}
          </p>
        </footer>
      </main>
    </div>
  );
}
