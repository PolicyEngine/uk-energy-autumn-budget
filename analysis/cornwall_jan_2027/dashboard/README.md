# Energy bills: Cornwall Insight's January 2027 cap forecast

One-page PolicyEngine dashboard: what Cornwall Insight's forecast January–March 2027 price cap (£1,999) would cost households in Great Britain compared with the October–December 2026 cap (£1,723), by income decile, and an illustrative count of people pushed below a fixed poverty line.

Figures come from `src/data/results.json`, a copy of `../results.json` written by `../run.py` (policyengine.py 6.2.7, Microcosm UK 2024-25). Rerun the analysis, then copy the file here.

```bash
cd analysis/cornwall_jan_2027/dashboard
bun install
bun run dev -p 3125   # http://localhost:3125/uk/energy-cap-january-2027
```

Built from the uk-energy-autumn-budget dashboard template (Next.js, @policyengine/ui-kit). Base path `/uk/energy-cap-january-2027`.
