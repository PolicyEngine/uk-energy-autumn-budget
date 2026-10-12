import { useState, useEffect, useRef } from "react";
import pricePath from "../data/price_path.json";
import options from "../data/options.json";
import deciles from "../data/deciles.json";
import hhTypes from "../data/hh_types.json";
import regions from "../data/regions.json";
import provenance from "../data/provenance.json";
import "./Dashboard.css";

const YEAR_OPTIONS = [
  { key: "2026-27", label: "2026-27" },
  { key: "2027-28", label: "2027-28" },
];

const ELEC = "#f59e0b";
const GAS = "#3b82f6";
// Reforms that cover Great Britain only (no Northern Ireland households).
const GB_ONLY = ["rf_targeted_discount", "whd_top_up", "extend_vat_cut"];
const SUPPORT = "#319795";

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
            {data.map((d, i) => (
              <div className="col-chart-col" key={i} onClick={onSelect ? () => onSelect(d) : undefined} style={onSelect ? { cursor: "pointer" } : undefined}>
                <div className="col-chart-tooltip">
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
                <div className="col-chart-label">{d.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
      {xLabel && <div className="col-chart-x-label">{xLabel}</div>}
    </div>
  );
}

const KIND_BANDS = {
  Announced: { fill: "#E6FFFA", text: "#285E61", label: "Announced by Ofgem" },
  Forecast: { fill: "#FFF7ED", text: "#9A3412", label: "Forecast" },
  Assumed: { fill: "#F2F4F7", text: "#4B5563", label: "Assumed" },
};

const shortSource = (r) =>
  r.kind === "Announced" ? "Ofgem"
    : r.source.startsWith("Cornwall") ? "Cornwall Insight"
    : r.source.startsWith("Supplier") ? "Supplier average"
    : r.source.startsWith("OVO") ? "OVO"
    : "Held flat";

/** Baseline prices over time. Background bands show whether each quarter is announced, forecast or
 * assumed; each quarter is labelled with its source. Lines are solid for announced quarters. */
function PriceLineChart({ rows, series, formatValue, yLabel }) {
  const W = 1100, H = 380, ml = 64, mr = 16, mt = 36, mb = 78;
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

  return (
    <div className="col-chart" style={{ position: "relative" }}>
      <div className="col-chart-y-label">{yLabel}</div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={`Baseline ${yLabel} by quarter`} style={{ overflow: "visible", fontFamily: "inherit" }}>
        {bands.map((b) => {
          const k = KIND_BANDS[b.kind];
          const x0 = ml + b.start * colW;
          const w = (b.end - b.start + 1) * colW;
          return (
            <g key={b.start}>
              <rect x={x0} y={mt - 28} width={w} height={H - mb - mt + 28} fill={k.fill} />
              <text x={x0 + 10} y={mt - 10} fontSize="13" fontWeight="600" fill={k.text}>{k.label}</text>
            </g>
          );
        })}
        {ticks.map((t) => (
          <g key={t}>
            <line x1={ml} x2={W - mr} y1={y(t)} y2={y(t)} stroke="#D1D5DB" strokeOpacity="0.7" />
            <text x={ml - 8} y={y(t)} dy="0.35em" textAnchor="end" fontSize="12" fill="#6B7280">{formatValue(t)}</text>
          </g>
        ))}
        {series.map((s) => (
          <g key={s.key}>
            <path d={path(s.key, 0, Math.max(0, firstProjected - 1))} fill="none" stroke={s.color} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
            {firstProjected > 0 && (
              <path d={path(s.key, firstProjected - 1, rows.length - 1)} fill="none" stroke={s.color} strokeWidth="2.5" strokeDasharray="6 5" strokeLinejoin="round" strokeLinecap="round" />
            )}
            {rows.map((r, i) => (
              <g key={i}>
                <circle cx={x(i)} cy={y(r[s.key])} r={hover === i ? 5.5 : 4} fill={s.color} stroke="#fff" strokeWidth="1.5" />
                {series.length === 1 && (
                  <text x={x(i)} y={y(r[s.key]) - 12} textAnchor="middle" fontSize="12" fontWeight="600" fill="#1F2937">{formatValue(r[s.key])}</text>
                )}
              </g>
            ))}
          </g>
        ))}
        {rows.map((r, i) => {
          const [a, b] = r.period.length > 12 ? [r.period.split("–")[0] + "–", r.period.split("–")[1]] : r.period.split(" ");
          return (
            <g key={r.period}>
              <text x={x(i)} y={H - mb + 18} textAnchor="middle" fontSize="12" fill="#344054" fontWeight="600">{a}</text>
              <text x={x(i)} y={H - mb + 34} textAnchor="middle" fontSize="12" fill="#6B7280">{b}</text>
              <a href={r.link} target="_blank" rel="noopener noreferrer">
                <text x={x(i)} y={H - mb + 56} textAnchor="middle" fontSize="11.5" fill={KIND_BANDS[r.kind].text} textDecoration="underline">{shortSource(r)}</text>
              </a>
              <rect x={x(i) - colW / 2} y={mt - 28} width={colW} height={H - mb - mt + 28} fill="transparent"
                onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} />
            </g>
          );
        })}
      </svg>
      {hover != null && (
        <div className="col-chart-tooltip" style={{ opacity: 1, visibility: "visible", left: `${(x(hover) / W) * 100}%`, top: 0, transform: "translateX(-50%)", position: "absolute", pointerEvents: "none", whiteSpace: "normal", width: 240 }}>
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
    },
    standing: {
      label: "Standing charges",
      yLabel: "pence per day",
      series: [
        { key: "elec_standing_p", label: "Electricity", color: ELEC },
        { key: "gas_standing_p", label: "Gas", color: GAS },
      ],
      fmt: (v) => `${v.toFixed(0)}p`,
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
    model: "PolicyEngine UK reform paying £175 to each eligible household; counted as HBAI income, like the Warm Home Discount.",
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
    name: "Warm Home +£150",
    summary: "Doubles the £150 discount.",
    eligibility: "Households receiving a means-tested benefit (the Warm Home Discount's qualifying list).",
    how: <>The <a href="https://www.gov.uk/the-warm-home-discount-scheme" target="_blank" rel="noopener noreferrer">Warm Home Discount</a> takes £150 off electricity bills each winter; this doubles it to £300.</>,
    source: <><a href="https://www.citizensadvice.org.uk/about-us/media-centre/press-releases/more-than-a-third-of-brits-worried-about-affording-energy-bills-this-winter-warns-citizens-advice/" target="_blank" rel="noopener noreferrer">Citizens Advice</a> and <a href="https://www.energy-uk.org.uk/publications/economic-defence-tackling-energy-bills-in-winter-2026-27/" target="_blank" rel="noopener noreferrer">Energy UK</a> call for more support through or on top of the scheme.</>,
    model: "PolicyEngine UK reform paying £150 to households on means-tested benefits.",
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
    name: "Cap freeze at £1,641",
    summary: "Typical bill held at £1,641.",
    eligibility: "Every household on a capped or comparable tariff.",
    how: "The government pays suppliers the difference between forecast prices and prices that give a £1,641 typical bill.",
    source: <>Like the 2022-24 <a href="https://www.gov.uk/government/publications/energy-bills-support/energy-price-guarantee-up-until-30-june-2023" target="_blank" rel="noopener noreferrer">Energy Price Guarantee</a> (set at £2,500). <a href="https://ippr-org.files.svdcdn.com/production/Downloads/Price_caps_and_economic_stability_May26.pdf" target="_blank" rel="noopener noreferrer">IPPR</a> proposes a cap that switches on at £2,000.</>,
    model: "PolicyEngine UK's Energy Price Guarantee switched on with the guarantee at £1,641.",
  },
];

function PolicyOptionsSection({ opt, setOpt }) {
  const sel = POLICY_INFO.find((p) => p.id === opt) || POLICY_INFO[0];
  return (
    <div id="policies">
      <h2 className="section-heading">The policy options</h2>
      <p className="section-description">
        Six options drawn from published proposals and past support schemes. Click an option to see who is
        eligible, how it works and where it was proposed; the charts below follow the option you select.
      </p>
      <div className="policy-grid">
        {POLICY_INFO.map((p) => (
          <button
            type="button"
            key={p.id}
            className={`policy-box${p.id === sel.id ? " active" : ""}`}
            onClick={() => setOpt(p.id)}
            aria-pressed={p.id === sel.id}
          >
            <span className="policy-box-name">{p.name}</span>
            <span className="policy-box-summary">{p.summary}</span>
          </button>
        ))}
      </div>
      <div className="section-card policy-detail">
        <h3 className="chart-title">{sel.name}</h3>
        <table className="scenario-table">
          <tbody>
            <tr><th scope="row">Who is eligible</th><td>{sel.eligibility}</td></tr>
            <tr><th scope="row">How it works</th><td>{sel.how}</td></tr>
            <tr><th scope="row">Where it was proposed</th><td>{sel.source}</td></tr>
            <tr><th scope="row">How we model it</th><td>{sel.model}</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

function BudgetSection({ fy, setFy, opt, setOpt }) {
  const [metric, setMetric] = useState("cost");
  const rows = options.filter((o) => o.fy === fy);
  const METRICS = {
    cost: {
      label: "Cost to the Exchequer",
      y: "£bn a year",
      series: [{ key: "cost_bn", label: "Cost" }],
      fmt: (v) => `£${Number(v).toFixed(v < 10 && v % 1 ? 1 : 0)}bn`,
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
      sort: "share_receiving_pct",
    },
  };
  const m = METRICS[metric];
  const data = [...rows].sort((a, b) => b[m.sort] - a[m.sort]).map((r) => ({ ...r, label: r.option }));
  const maxVal = Math.max(...data.flatMap((r) => m.series.map((x) => r[x.key]))) * 1.15;
  const series = m.series.length > 1 ? m.series : [{ ...m.series[0], colorFn: (d) => (d.option_id === opt ? SUPPORT : "#94a3b8") }];

  return (
    <div id="budget">
      <h2 className="section-heading">Budget responses: cost and reach</h2>
      <p className="section-description">
        Each option is a <a href="https://pypi.org/project/policyengine/" target="_blank" rel="noopener noreferrer">PolicyEngine</a> reform against the {fy} baseline. Cost is the change in
        household net income summed over all households; gains are the same change averaged per household.
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
          {m.series.length > 1 && (
            <div className="col-chart-legend">
              {m.series.map((x) => <span key={x.key}><span className="col-chart-legend-dot" style={{ background: x.color }} />{x.label}</span>)}
            </div>
          )}
        </div>
      </div>

    </div>
  );
}

function HouseholdSection({ fy, setFy }) {
  const [measure, setMeasure] = useState("gbp");
  const [opt, setOpt] = useState("rf_targeted_discount");
  const rows = options.filter((o) => o.fy === fy);
  const o = rows.find((r) => r.option_id === opt) || rows.find((r) => r.option_id === "rf_targeted_discount");
  const info = POLICY_INFO.find((p) => p.id === o.option_id);
  const MEASURES = {
    gbp: { label: "£ per year", fmt: (v) => fmt(v), y: "£/yr per household", val: (d) => d[o.option_id] },
    income: { label: "% of net income", fmt: (v) => `${v.toFixed(2)}%`, y: "% of household net income", val: (d) => (d[o.option_id] / d.net_income) * 100 },
    bill: { label: "% of energy bill", fmt: (v) => `${v.toFixed(0)}%`, y: "% of baseline energy bill", val: (d) => (d[o.option_id] / d.bill) * 100 },
  };
  const ms = MEASURES[measure];
  const dec = deciles.filter((d) => d.fy === fy).map((d) => ({ label: `${d.decile}`, gain: ms.val(d) }));
  const [breakdown, setBreakdown] = useState("hh_type");
  const groups = (breakdown === "region" ? regions.map((r) => ({ ...r, name: r.region })) : hhTypes.map((h) => ({ ...h, name: h.hh_type })))
    .filter((h) => h.fy === fy)
    .sort((a, b) => b[o.option_id] - a[o.option_id]);
  const maxVal = Math.max(...dec.map((d) => d.gain)) * 1.15 || 1;

  return (
    <div id="households">
      <h2 className="section-heading">Household effects</h2>
      <p className="section-description">
        The average gain from the selected reform against the {fy} baseline. Income deciles run from 1 to 10
        in order of household net income.
      </p>

      <div className="section-card">
        <div className="pill-rows">
          <ExpandablePillRow label="FINANCIAL YEAR" options={YEAR_OPTIONS} value={fy} onChange={setFy} />
          <ExpandablePillRow
            label="REFORM"
            options={rows.map((r) => ({ key: r.option_id, label: r.option }))}
            value={o.option_id}
            onChange={setOpt}
          />
          <ExpandablePillRow
            label="MEASURE"
            options={Object.entries(MEASURES).map(([k, v]) => ({ key: k, label: v.label }))}
            value={measure}
            onChange={setMeasure}
          />
        </div>
        {info && (
          <div className="policy-note">
            <strong>{info.name}:</strong> {info.summary} <span className="policy-note-eligibility">Eligible: {info.eligibility}</span>
          </div>
        )}
        <div className="chart-wrapper">
          <ColumnChart
            data={dec}
            series={[{ key: "gain", label: o.option, color: SUPPORT }]}
            maxValue={maxVal}
            formatValue={ms.fmt}
            yLabel={ms.y}
            xLabel="Income decile"
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
          <ColumnChart
            data={groups.map((h) => ({
              label: h.name,
              gain: h[o.option_id],
              tooltip: h.name === "Northern Ireland" && GB_ONLY.includes(o.option_id)
                ? `Not covered: ${o.option} applies in Great Britain only`
                : `${fmt(h[o.option_id])} a year, ${((h[o.option_id] / h.bill) * 100).toFixed(0)}% of a ${fmt(h.bill)} baseline energy bill`,
            }))}
            series={[{ key: "gain", label: o.option, color: SUPPORT }]}
            maxValue={Math.max(...groups.map((h) => h[o.option_id])) * 1.15 || 1}
            formatValue={(v) => fmt(v)}
            yLabel="£/yr per household"
            xLabel={breakdown === "region" ? "Region" : "Household type"}
            wrapLabels
          />
        </div>
        <p className="section-description" style={{ marginTop: 12 }}>
          Average gain over all households in each group, including those the reform does not reach.
          {breakdown === "region" && GB_ONLY.includes(o.option_id) && (
            <> {o.option} covers Great Britain only, so Northern Ireland shows £0.</>
          )}
          {" "}Northern Ireland is outside the Ofgem cap, so GB prices are used as a proxy for its bills.
        </p>
      </div>
    </div>
  );
}

const Fn = ({ n }) => <a href={`#fn-${n}`}><sup>{n}</sup></a>;

const REFERENCES = [
  ["Ofgem, \u201cEnergy price cap unit rates and standing charges\u201d and quarterly cap announcements, 2025\u20132026.", "https://www.ofgem.gov.uk/your-energy-supply/your-energy-bill/energy-price-cap-unit-rates-and-standing-charges"],
  ["Ofgem, \u201cEnergy price cap will rise by 4% from October 2026\u201d, 26 August 2026.", "https://www.ofgem.gov.uk/press-release/energy-price-cap-will-rise-4-october-2026"],
  ["Cornwall Insight, \u201c16% price cap rise forecast in January\u201d, 30 September 2026.", "https://www.cornwall-insight.com/press-releases/16-price-cap-rise-forecast-in-january/"],
  ["MoneySavingExpert, average of EDF, British Gas and E.ON Next price cap predictions, 6\u20137 October 2026.", "https://www.moneysavingexpert.com/utilities/energy-price-cap-prediction/"],
  ["Ofgem, \u201cReview of typical domestic consumption values: decision\u201d, 27 May 2026.", "https://www.ofgem.gov.uk/sites/default/files/2026-05/Review%20of%20typical%20domestic%20consumption%20values%20decision.pdf"],
  ["The Value Added Tax (Reduced Rate) (Domestic Electricity) Order 2026, SI 2026/987.", "https://www.legislation.gov.uk/uksi/2026/987/made"],
  ["PolicyEngine Microcosm, issue #1113: the price basis of domestic electricity and gas spending.", "https://github.com/PolicyEngine/microcosm/issues/1113"],
  ["Resolution Foundation, \u201cBilling me softly\u201d, 10 August 2026.", "https://www.resolutionfoundation.org/publications/billing-me-softly/"],
  ["DWP, Households Below Average Income: quality and methodology information report.", "https://www.gov.uk/government/statistics/households-below-average-income-for-financial-years-ending-1995-to-2024"],
  ["Priesmann, J. and Praktiknjo, A. (2025), income-specific price elasticities of household energy demand, as used in PolicyEngine's energy price shock analysis.", "https://github.com/PolicyEngine/energy-price-shock"],
  ["Office for Budget Responsibility, \u201cAutumn 2026 forecast date announced\u201d, 31 July 2026.", "https://obr.uk/autumn-2026-forecast-date-announced/"],
  ["policyengine.py release on PyPI.", "https://pypi.org/project/policyengine/"],
  ["OVO, \u201cEnergy price cap\u201d forecast table, 7 October 2026.", "https://www.ovoenergy.com/price-cap"],
];

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
          SHA-256 hash. Microcosm sets each household's electricity and gas spending to match ONS 2025
          spending,<Fn n={7} /> so we first move it to April–June 2026 prices: electricity is multiplied
          by {pv.price_rebase_cy2025_to_apr_jun_2026.elec.toFixed(3)} and gas
          by {pv.price_rebase_cy2025_to_apr_jun_2026.gas.toFixed(3)}, the change in Ofgem's typical bill for each
          fuel between calendar 2025 and April–June 2026.<Fn n={1} />
        </p>
        <p className="section-description">
          The baseline is current law at forecast prices. Ofgem's announced caps set prices to December
          2026,<Fn n={2} /> Cornwall Insight's forecast sets January–March 2027,<Fn n={3} /> and the average of
          supplier forecasts sets April–September 2027,<Fn n={4} /> and OVO's forecast sets October–December
          2027.<Fn n={13} /> No forecaster publishes January–March 2028, so it is held at the October level. OVO's
          figures keep electricity VAT-free, so we add the 5% VAT that current law restores in April 2027. Because Ofgem cut its typical consumption
          values on 1 July 2026,<Fn n={5} /> we cost every quarter from its unit rates and standing charges rather
          than from headline cap figures, and take electricity and gas separately. Supplier forecasts give no
          split between the two fuels, so we scale Cornwall Insight's January unit rates to each forecast total.
          VAT on domestic electricity is 0% from October 2026 to March 2027 and returns to 5% from April
          2027.<Fn n={6} /> Each household's electricity and gas spending is raised by its fuel's average price
          change over the financial year and loaded into PolicyEngine. Everything else is current law: the
          Energy Price Guarantee ended in April 2024, so it pays nothing; the cap-freeze option switches it back on
          with bills held at £1,641.
        </p>
        <p className="section-description">
          Each Budget option is a PolicyEngine reform run against that baseline on the same households. Its
          cost is the change in household net income summed over all households; household gains are the same
          change, averaged by income decile or household type. The Cost of Living Payment, £400 payment and
          cap freeze use PolicyEngine UK's own parameters. The targeted discount follows the Resolution
          Foundation's design (£175 to households on means-tested benefits or whose highest individual income
          is under £24,000),<Fn n={8} /> implemented as a PolicyEngine UK reform taken from PolicyEngine's
          uk-energy-reforms repository. The Warm Home Discount top-up uses the same reform with eligibility through means-tested benefits only. PolicyEngine
          UK has no parameter for VAT on domestic electricity, so the VAT extension is costed directly from each
          household's electricity bill in Great Britain.
        </p>
        <p className="section-description">
          Poverty is PolicyEngine's HBAI relative measure.<Fn n={9} /> HBAI income counts cash such as the Cost of
          Living Payment and the Warm Home Discount, but not energy bills or bill support such as credits, rebates,
          price guarantees or VAT cuts. Reforms delivered as bill support therefore show no change in poverty,
          even when they cut household costs. Microcosm matches official energy spending and household counts
          closely (£42.2bn on electricity and gas in 2025 against the ONS's £41.9bn; 29.0m households in 2024
          against 28.6m), but puts relative poverty after housing costs at 15.3% of people and 19.1% of children
          in 2024-25, against DWP's 20% and 27%. PolicyEngine's previous enhanced FRS dataset is closer on poverty
          (20.5% and 29.8%) but overstates energy spending at £51bn. We report Microcosm's poverty rates as
          computed and do not use them to rank the options.
        </p>
      </div>

      <div className="section-card">
        <h2 className="section-heading">Behavioural responses</h2>
        <p className="section-description">
          This analysis applies no behavioural response. Households use the same amount of electricity and gas
          at forecast prices as at April–June 2026 prices, and none of the reforms changes how much energy they
          use. The baseline bills are therefore an upper estimate of what households pay: when prices rise,
          households cut use, and PolicyEngine's energy price shock analysis estimates that cut with
          income-specific short-run price elasticities, from −0.64 in decile 1 to −0.11 in decile 10.<Fn n={10} />
          The reform costs are not affected, because every option pays a fixed amount or, for the cap freeze and
          VAT extension, scales with the baseline bill. Applying those elasticities would lower the cap freeze and
          VAT extension costs a little and leave the others unchanged.
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
  const [opt, setOpt] = useState("rf_targeted_discount");

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
          reach of six options; <strong>Household effects</strong> shows the
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
            <PolicyOptionsSection opt={opt} setOpt={setOpt} />
            <hr className="section-divider" />
            <BudgetSection fy={fy} setFy={setFy} opt={opt} setOpt={setOpt} />
          </div>
        )}
        {activeTab === "households" && (
          <div className="tab-content">
            <HouseholdSection fy={fy} setFy={setFy} />
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
