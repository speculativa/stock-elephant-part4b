# Phase 2 — Pre-Event Break Identification
Generated: 2026-04-28 17:55
Data cutoff: 2026-04-20 (pre-Bessent signal)

## Research question
What pre-existing balance-sheet and market conditions preceded the April 22, 2026 Bessent UAE swap line signal?

## Methodological note

Phase 2 is a timing and diagnostic layer. It is not a causal event study. The core evidence comes from Phase 1: CBUAE reserve composition, CLC, BIS dollar-routing, TIC visibility, BTAR, and OFR repo-channel context.

The main Phase 2 object is the sequence of data-driven Phase 1 accounting and liquidity threshold breaks. Legacy structural-break, anomaly, and lead-lag diagnostics are retained as supporting public-market context.

## 1. Phase 1 Threshold Breaks

These are accounting and liquidity threshold breaks derived from fixed Phase 1 output CSVs. They are the primary Phase 2 timing evidence.

| Date | Event | Metric | Threshold | Value | Interpretation |
|---|---|---|---|---:|---|
| 2024-03-31 | 6-month import CLC below 1 in observed CBUAE window | clc_real_6m | < 1 | 0.605 | Cash/deposit-like reserve layer does not cover a 6-month implied import-liquidity floor in the observed CBUAE reserve-composition window. |
| 2025-03-31 | CBUAE cash/deposits share falls below 50% | cash_deposits_share_of_gross_reserves | < 50% | 0.491 | Cash/deposit-like reserve layer loses majority status. |
| 2025-06-30 | BIS global USD liabilities to UAE reach sample high | bis_global_usd_liabilities_to_uae | sample high | 739.9 | Global banking dollar-liability layer to UAE reaches its highest observed value in the BIS sample. |
| 2025-06-30 | 3-month import CLC crosses below 1 | clc_real_3m | < 1 | 0.980 | Cash/deposit-like reserve layer no longer covers a 3-month implied import-liquidity floor. |
| 2025-06-30 | CBUAE foreign investments exceed cash/deposits | foreign_investments_bn > cash_deposits_abroad_bn | foreign investments > cash/deposits | foreign_investments=$137.8B; cash_deposits=$113.9B | Securities/foreign-investment reserve layer becomes larger than cash/deposit-like liquidity. |
| 2025-09-30 | Latest BIS global USD liabilities to UAE | bis_global_usd_liabilities_to_uae | latest observation | 726.0 | Latest observed global BIS USD-liability layer remains large relative to official CBUAE reserves. |
| 2025-09-30 | CBUAE cash/deposits share falls below 35% | cash_deposits_share_of_gross_reserves | < 35% | 0.347 | Cash/deposit-like reserve layer becomes thin relative to gross reserves. |
| 2025-09-30 | Low-scenario UAE-BTAR exceeds 1 for BIS global USD liabilities to UAE | uae_btar | low scenario > 1 | 1.329 | Even the low encumbrance/leverage scenario is larger than observed Fed balance-sheet absorption for this bucket. |
| 2026-02-28 | CBUAE cash/deposits share falls below 25% | cash_deposits_share_of_gross_reserves | < 25% | 0.244 | Cash/deposit-like reserve layer approaches hard liquidity minimum. |

## 2. Legacy Structural Break Dates

These model-fitted structural breaks are retained as public-data diagnostics. They do not replace the Phase 1 threshold-break sequence.

Only break dates are shown here. Segment statistics and percentage changes are saved in `structural_breaks.json`; they are not shown in the main report because percentage changes can become unstable when segment means are near zero.

| Series | # breaks | Break dates |
|---|---:|---|
| UAE Portfolio Investment (annual, USD mn) | 1 | 2023-12-01 |
| UAE FX Reserves level (monthly, USD mn) | 3 | 2005-07-01, 2013-11-01, 2023-01-01 |
| UAE FX Reserves YoY growth (monthly, %) | 9 | 2006-12-01, 2007-10-01, 2008-03-01, 2008-08-01, 2009-11-01, 2011-02-01, 2011-07-01, 2014-11-01, 2023-03-01 |
| UAE M2 Money Supply (monthly, USD mn) | 3 | 2007-04-01, 2013-12-01, 2023-02-01 |
| Belgium Treasury Holdings MoM change (USD bn) | 2 | 2014-11-30, 2015-09-30 |
| Canada Treasury Holdings MoM change (USD bn) | 2 | 2021-02-28, 2025-09-30 |
| UK Treasury Holdings MoM change (USD bn) | 3 | 2021-02-28, 2022-10-31, 2023-03-31 |
| Japan Treasury Holdings MoM change (USD bn) | 2 | 2021-12-31, 2022-10-31 |
| SOFR minus EFFR spread (monthly mean, bp) | 4 | 2016-09-30, 2017-12-31, 2020-01-31, 2024-08-31 |
| Fed Balance Sheet (monthly end, USD mn) | 2 | 2013-10-31, 2020-06-30 |

## 3. Top Treasury Holdings Anomalies (|z| > 2)

| Country | Date | Δ (USD bn) | z-score |
|---|---|---|---|
| Belgium | 2015-03-31 | -92 | -2.98 |
| Aggregate | 2021-06-30 | 374 | 2.98 |
| Belgium | 2021-12-31 | 47 | 2.96 |
| Canada | 2019-07-31 | 37 | 2.83 |
| Canada | 2021-06-30 | 47 | 2.82 |
| Japan | 2013-07-31 | 52 | 2.79 |
| China | 2015-03-31 | 37 | 2.79 |
| Belgium | 2013-01-31 | 47 | 2.72 |
| Canada | 2016-03-31 | 12 | 2.72 |
| UK | 2019-07-31 | 66 | 2.48 |
| Japan | 2022-03-31 | -74 | -2.47 |
| UK | 2018-12-31 | 29 | 2.40 |
| Belgium | 2026-01-31 | -26 | -2.38 |
| Canada | 2025-02-28 | 55 | 2.37 |
| UK | 2013-03-31 | 18 | 2.33 |

## 4. Lead-Lag Cross-Correlations (UAE flows vs US custodial flows)

| UAE series | US country | peak corr | peak lag | interpretation |
|---|---|---|---|---|
| uae_m2_mom | UK | 0.264 | 12 | UAE lags US by 12 months |
| uae_m2_mom | Belgium | 0.250 | 0 | contemporaneous |
| uae_m2_mom | Japan | 0.247 | 1 | UAE lags US by 1 months |
| uae_fx_mom | Japan | -0.221 | 3 | UAE lags US by 3 months |
| uae_m2_mom | China | -0.194 | -10 | UAE leads US by 10 months |
| uae_fx_mom | Canada | 0.187 | 0 | contemporaneous |
| uae_fx_mom | China | 0.186 | 0 | contemporaneous |
| uae_m2_mom | Canada | 0.181 | 8 | UAE lags US by 8 months |
| uae_fx_mom | Belgium | 0.171 | -9 | UAE leads US by 9 months |
| uae_fx_mom | UK | -0.152 | 10 | UAE lags US by 10 months |

## 5. Timeline Synthesis

The unified timeline is the main Phase 2 object. It combines:

- Phase 1 reserve-composition events.
- Phase 1 CLC liquidity-cliff events.
- Phase 1 BIS routing and BTAR events.
- Public-market diagnostics from structural breaks, anomaly detection, and lead-lag checks.
- Policy and market anchors such as the Fed pivot, SOFR stress marker, and Bessent signal.

VAR and Granger tests are intentionally excluded. The fixed Phase 1 stress variables are short, mixed-frequency, and partly reconstructed. A VAR on old monthly UAE FX-reserve changes and public custody proxies is not a defensible test of the Phase 1 thesis.

## 6. Interpretation Guide

**How to read the results:**

- Phase 2 is a timing and diagnostic layer. It is not the core proof of the UAE swap-line thesis.

- The core evidence is Phase 1: CBUAE reserve composition, CLC, BIS dollar-routing, TIC visibility, BTAR, and OFR repo-channel context.

- A structural break in UAE portfolio investment in 2023-2024 identifies when UAE-side external deployment behavior changed. It supports the portfolio-breakout claim, but it does not by itself locate the destination of the funds.

- A later break in SOFR-EFFR spread or foreign Treasury MoM changes is timing-consistent with stress appearing in U.S.-side plumbing. Phase 2 alone cannot attribute that stress to UAE behavior.

- Weak lead-lag results should not be read as falsifying the Phase 1 thesis. They mainly show that simple public UAE FX-reserve changes do not map cleanly into public TIC custody-country movements.

- The timeline chart is now the main Phase 2 object. It orders Phase 1 balance-sheet events, CLC cliff events, BIS routing events, public-market diagnostics, and policy anchors to test whether the sequence is coherent.

## 7. Output files

- Breaks: /content/drive/MyDrive/StockElephant/uae_swap_line_analysis/outputs/stats/structural_breaks.json
- Phase 1 threshold breaks: /content/drive/MyDrive/StockElephant/uae_swap_line_analysis/outputs/stats/phase1_threshold_breaks.csv
- Anomalies: /content/drive/MyDrive/StockElephant/uae_swap_line_analysis/outputs/stats/treasury_anomalies.csv
- Lead-lag: /content/drive/MyDrive/StockElephant/uae_swap_line_analysis/outputs/stats/lead_lag_correlations.csv
- Timeline: /content/drive/MyDrive/StockElephant/uae_swap_line_analysis/outputs/stats/timeline_events.csv
- Timeline plot: /content/drive/MyDrive/StockElephant/uae_swap_line_analysis/outputs/plots/phase2_pre_event_timeline.png
- Anomaly plot: /content/drive/MyDrive/StockElephant/uae_swap_line_analysis/outputs/plots/phase2_anomaly_detection.png