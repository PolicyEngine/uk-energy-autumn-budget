import { useState } from "react";
import results from "../data/results.json";
import "./Dashboard.css";

const thousands = (m) => `${Math.round(m * 1000)},000`;
const fmt = (v) => `£${Math.round(v).toLocaleString("en-GB")}`;
const RISE = "#DD6B20";

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

const LINK = { target: "_blank", rel: "noopener noreferrer" };
const CORNWALL_PR = "https://www.cornwall-insight.com/press-releases/16-price-cap-rise-forecast-in-january/";
const CORNWALL = "https://www.cornwall-insight.com/predictions-and-insights-into-the-default-tariff-cap/";
const OFGEM_OCT = "https://www.ofgem.gov.uk/press-release/energy-price-cap-will-rise-4-october-2026";
const METHOD = "https://github.com/PolicyEngine/uk-energy-autumn-budget/pull/4";
const BUDGET_DASH = "https://uk-energy-autumn-budget.vercel.app/uk/energy-autumn-budget";
const HBAI = "https://www.gov.uk/government/collections/households-below-average-income-hbai--2";

const MEASURES = {
  gbp: { label: "£ per year", y: "£/yr per household", fmt: (v) => fmt(v), exact: (v) => fmt(v) },
  income: { label: "% of net income", y: "% of household net income", fmt: (v) => `${v.toFixed(1)}%`, exact: (v) => `${v.toFixed(2)}%` },
};

export default function Dashboard() {
  const [measure, setMeasure] = useState("gbp");
  const r = results;
  const pov = r.illustrative_poverty;
  const ms = MEASURES[measure];
  const rows = r.deciles.map((d) => ({
    label: `${d.decile}`,
    annual: d.extra_cost_annual,
    quarter: d.extra_cost_jan_mar,
    share: d.share_of_income_pct,
    income: d.mean_net_income,
  }));
  const data = rows.map((d) =>
    measure === "gbp"
      ? { ...d, a: d.annual, tooltip: `${fmt(d.annual)} a year, of which ${fmt(d.quarter)} in January–March` }
      : { ...d, a: d.share, tooltip: `${d.share.toFixed(2)}% of ${fmt(d.income)} mean net income` },
  );
  const series = [{ key: "a", label: measure === "gbp" ? "Extra cost a year" : "Share of net income", color: RISE }];
  const maxVal = Math.max(...data.map((d) => d.a)) * 1.15;
  const d1 = rows[0];
  const d10 = rows[rows.length - 1];

  return (
    <div className="app-shell">
      <header className="title-row">
        <div className="title-row-inner">
          <h1>Energy bills: Cornwall Insight&apos;s January 2027 cap forecast</h1>
        </div>
      </header>

      <main className="main-content">
        <p className="intro-text">
          This dashboard estimates what{" "}
          <a href={CORNWALL} {...LINK}>Cornwall Insight&apos;s forecast</a> January–March 2027 price cap of £1,999 would cost
          households in Great Britain compared with the{" "}
          <a href={OFGEM_OCT} {...LINK}>October–December 2026 cap</a> of £1,723, by income decile, and how many people it
          could push below a fixed poverty line. It uses PolicyEngine UK, with the higher rates held for a year.
        </p>

        <div className="kpi-row">
          <div className="kpi">
            <div className="kpi-label">Average household</div>
            <div className="kpi-value">+{fmt(r.mean_extra_cost_annual)}<span className="kpi-unit">a year</span></div>
            <div className="kpi-sub">Averaged over every household&apos;s own energy use</div>
            <div className="kpi-compare">
              <a href={CORNWALL_PR} {...LINK}>Cornwall Insight</a>: +£276.
            </div>
          </div>
          <div className="kpi">
            <div className="kpi-label">Of which in January–March</div>
            <div className="kpi-value">~{fmt(r.mean_extra_cost_jan_mar)}</div>
            <div className="kpi-sub">The winter quarter, when use is highest</div>
            <div className="kpi-compare">An even spread would put {fmt(r.mean_extra_cost_annual / 4)} in each quarter.</div>
          </div>
          <div className="kpi kpi-neutral">
            <div className="kpi-label">More people below the poverty line</div>
            <div className="kpi-value">{Math.round(pov.bhc.newly_below_m * 1000)}k–{Math.round(pov.ahc.newly_below_m * 1000)}k</div>
            <div className="kpi-sub">If the extra cost came out of household income, with the poverty line unchanged</div>
            <div className="kpi-compare">Lower figure: income before housing costs. Higher: after rent or mortgage.</div>
          </div>
        </div>

        <div className="section-card">
          <h2 className="section-heading">Cost by income decile</h2>
          <p className="section-description box-intro">
            Households in higher deciles pay more in cash because they use more energy; households in lower deciles pay a
            larger share of their income. Net income is{" "}
            <a href={HBAI} {...LINK}>HBAI household net income</a>, before housing costs.
          </p>
          <div className="seg-toggle" role="radiogroup" aria-label="Measure">
            {Object.entries(MEASURES).map(([k, v]) => (
              <button
                key={k}
                type="button"
                role="radio"
                aria-checked={measure === k}
                className={measure === k ? "active" : ""}
                onClick={() => setMeasure(k)}
              >
                {v.label}
              </button>
            ))}
          </div>
          <div className="chart-wrapper">
            <ColumnChart data={data} series={series} maxValue={maxVal} formatValue={ms.fmt} yLabel={ms.y} xLabel="Income decile (1 = lowest)" />
            <p className="chart-sentence">
              The bottom decile pays <strong>{fmt(d1.annual)}</strong> a year more, <strong>{d1.share.toFixed(1)}%</strong> of its
              income; the top decile pays <strong>{fmt(d10.annual)}</strong>, <strong>{d10.share.toFixed(1)}%</strong>.
            </p>
            <ChartValuesTable
              caption="Extra cost by income decile"
              rows={rows}
              columns={[
                { label: "Income decile", value: (d) => d.label },
                { label: "Extra cost a year", value: (d) => fmt(d.annual) },
                { label: "Share of net income", value: (d) => `${d.share.toFixed(1)}%` },
                { label: "Of which, Jan–Mar", value: (d) => fmt(d.quarter) },
                { label: "Mean net income", value: (d) => fmt(d.income) },
              ]}
            />
          </div>
        </div>

        <div className="section-card">
          <h2 className="section-heading">Poverty</h2>
          <dl className="method-grid">
            <div className="method-row"><dt>Official measures</dt><dd>Official poverty statistics count income before energy bills are paid, so the cap rise alone does not change relative poverty. Absolute poverty rises slightly, because its line moves with prices, but only one quarter of higher prices falls in 2026-27.</dd></div>
            <div className="method-row"><dt>Our estimate</dt><dd>We take each household&apos;s extra energy cost out of its income and keep the poverty line where it is. {thousands(pov.bhc.newly_below_m)} more people would then have income below the line, measuring income before housing costs, or {thousands(pov.ahc.newly_below_m)} measuring it after rent or mortgage. This is our own calculation, not an official statistic.</dd></div>
          </dl>
        </div>

        <div className="section-card">
          <h2 className="section-heading">Assumptions</h2>
          <dl className="method-grid">
            <div className="method-row"><dt>Comparison</dt><dd>Cornwall Insight&apos;s January–March 2027 unit rates and standing charges against Ofgem&apos;s October–December 2026 cap. Both have 0% VAT on electricity, so the difference is the cap rise alone.</dd></div>
            <div className="method-row"><dt>Households</dt><dd>Every household is on the capped tariff and uses the same energy as today. No new government support. Great Britain only.</dd></div>
            <div className="method-row"><dt>Data</dt><dd>Microcosm UK 2024-25 on policyengine.py {r.provenance.policyengine_version} (policyengine-uk {r.provenance.model_version}). Method and code: <a href={METHOD} {...LINK}>PolicyEngine/uk-energy-autumn-budget</a>. Wider Budget analysis: <a href={BUDGET_DASH} {...LINK}>energy bills and the Autumn Budget</a>.</dd></div>
          </dl>
        </div>
      </main>
    </div>
  );
}
