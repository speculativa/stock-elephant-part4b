# UAE Swap Line Analysis — Phase 1 Summary

Generated: 2026-04-28 20:57

## Core question

Phase 1 asks whether the UAE swap-line issue is a reserve-quantity problem or a reserve-composition problem.

The key distinction is headline reserves versus immediately deployable dollar liquidity.

## UAE CEIC balance-sheet snapshot

| Item | Value | As of |
|---|---:|---|
| FX reserves, ex-gold | $243.7B | 2025-02 |
| Gold reserves | n/a | n/a |
| M1 money supply | $304.7B | 2026-02 |
| M2 money supply | $738.9B | 2025-11 |
| Portfolio investment flow | $54.9B | 2024-12 |

- FX reserves / M1: 80.0%
- FX reserves / M2: 33.0%

## Reserve residuals

| Component | Value |
|---|---:|
| Total FX reserves | $302.4B |
| Channel 8 cash/deposits | $73.6B |
| Channel 1 TIC Treasuries | $95.6B |
| CBUAE liquidity gap | $228.8B |
| National observable residual | $133.2B |

Definitions:

- CBUAE liquidity gap = total FX reserves minus Channel 8 cash/deposits.
- National observable residual = total FX reserves minus Channel 8 cash/deposits minus Channel 1 TIC Treasuries.

## Channel availability

| Channel | Rows | Latest headline value | Latest date |
|---|---:|---:|---|
| Channel_1_TIC_Direct | 18 | $95.6B | 2025-12-31 |
| Channel_2_NonUS_Custody | 16692 | $726.0B (BIS global USD liabilities to UAE) | 2025-09-30 |
| Channel_3_Agency_Corp | 1 | n/a | n/a |
| Channel_4_MMF | 1 | n/a | n/a |
| Channel_5_HedgeFund_LP | 2 | n/a | n/a |
| Channel_6_FICC_Sponsored | 2 | n/a | n/a |
| Channel_7_External_Managers | 1 | n/a | n/a |
| Channel_8_Deposits | 13 | $73.6B | 2026-02-28 |
| Channel_9_FX_Derivatives | 1 | n/a | n/a |

## US-side stress signals

| Signal | Latest value | Date |
|---|---:|---|
| Fed balance sheet | $6,693.9B | 2026-04-08 |
| SOFR-EFFR spread | -7.0 bp | 2026-04-09 |

## FICC analysis

- Total GSD members: 270
- Total omnibus accounts: 72
- Direct UAE matches in GSD: 0
- Direct Gulf matches in GSD: 0
- Total CCIT members: 6

## CBUAE reserve-composition finding

| Component | Latest value | Date |
|---|---:|---|
| Gross reserves | $302.4B | 2026-02-28 |
| Cash/deposits abroad | $73.6B | 2026-02-28 |
| Foreign investments | $207.6B | 2026-02-28 |
| Cash/deposits share of gross reserves | 24.4% | 2026-02-28 |
| Foreign-investments share of gross reserves | 68.7% | 2026-02-28 |

CBUAE data show that the central-bank reserve issue is composition, not scarcity: cash/deposit-like reserves fell sharply as a share of gross reserves while foreign investments became dominant.

## BIS dollar-routing finding

| Measure | Latest value | Date |
|---|---:|---|
| BIS global USD liabilities to UAE | $726.0B | 2025-09-30 |

BIS data indicate that the broader UAE-linked dollar banking footprint is far larger than the CBUAE reserve headline. This is a dollar-routing layer, not proof of basis-trade exposure.

Top BIS-implied reporter USD routing hubs:

| Reporter | Implied USD liabilities to UAE | Share |
|---|---:|---:|
| GB: United Kingdom | $320.4B | 44.1% |
| US: United States | $118.0B | 16.3% |
| FR: France | $93.3B | 12.9% |
| CH: Switzerland | $45.8B | 6.3% |
| JE: Jersey | $23.7B | 3.3% |
| NL: Netherlands | $20.8B | 2.9% |
| LU: Luxembourg | $14.8B | 2.0% |
| HK: Hong Kong SAR | $13.6B | 1.9% |
| CA: Canada | $11.5B | 1.6% |
| ES: Spain | $10.8B | 1.5% |

This reporter-country allocation is implied, not directly reported: global BIS USD liabilities to UAE are distributed by reporter-country all-currency loans/deposits liability shares.

## UAE-BTAR scenario results

| Bucket | Scenario | Gross unwind | Absorption capacity | UAE-BTAR |
|---|---|---:|---:|---:|
| BIS global USD liabilities to UAE | high | $1,089.0B | $109.3B | 9.96 |
| CBUAE liquidity gap | high | $343.1B | $109.3B | 3.14 |
| CBUAE foreign investments | high | $311.5B | $109.3B | 2.85 |
| TIC UAE Treasury holdings | high | $143.4B | $109.3B | 1.31 |
| BIS global USD liabilities to UAE | low | $145.2B | $109.3B | 1.33 |
| CBUAE liquidity gap | low | $45.8B | $109.3B | 0.42 |
| CBUAE foreign investments | low | $41.5B | $109.3B | 0.38 |
| TIC UAE Treasury holdings | low | $19.1B | $109.3B | 0.17 |
| BIS global USD liabilities to UAE | mid | $453.7B | $109.3B | 4.15 |
| CBUAE liquidity gap | mid | $143.0B | $109.3B | 1.31 |
| CBUAE foreign investments | mid | $129.8B | $109.3B | 1.19 |
| TIC UAE Treasury holdings | mid | $59.8B | $109.3B | 0.55 |

Absorption denominator:
- Fed balance-sheet expansion from 2026-01-21 to 2026-04-08

UAE-BTAR is not an attribution claim. It is a leverage-adjusted absorption test: if a small share of UAE-linked dollar buckets is encumbered into leveraged Treasury plumbing, the gross unwind can be large relative to the observed Fed balance-sheet expansion.

## UAE Liquidity Cliff Ratio

| Metric | Latest value | Date |
|---|---:|---|
| Cash/deposits abroad | $73.6B | 2026-02-28 |
| Implied monthly imports | $38.7B | 2026-02-28 |
| 3-month import need | $116.2B | 2026-02-28 |
| 6-month import need | $232.5B | 2026-02-28 |
| CLC real 3m | 0.63 | 2026-02-28 |
| CLC real 6m | 0.32 | 2026-02-28 |

- First recent 3-month import-liquidity cliff crossing since 2024-03-31: 2025-06-30 (CLC real 3m = 0.98).
- 6-month import-liquidity CLC was below one throughout the CBUAE reserve-composition window beginning 2024-03-31.

CLC is the UAE-side hard-constraint metric. It measures whether immediately deployable cash/deposit liquidity covers near-term real-economy dollar needs. CLC below one means cash/deposits alone do not cover the selected import-liquidity floor.

Caveat: implied monthly imports are reconstructed from CEIC FX reserves and FX-reserves-in-months-of-imports. Where CEIC import-cover data lag CBUAE reserve data, the latest available CEIC import-cover observation is carried forward.

## Cross-border repo market context

OFR's April 2026 cross-border repo analysis strengthens the mechanism behind BTAR. It does not identify UAE-specific repo exposure, but it shows that cross-border repo is a large, dollar-heavy transmission channel.

| OFR finding | Relevance to this analysis |
|---|---|
| Cross-border repos are about one-third of the U.S. repo market. | Foreign dollar nodes can transmit stress into U.S. repo and Treasury collateral markets. |
| Daily average U.S. repo outstanding was about $12.75T from July 2025 to February 2026. | The relevant market plumbing is multi-trillion scale. |
| In NCCBR, foreign companies borrowed around $1.2T and lent around $1.3T. | The opaque bilateral segment is a major cross-border funding channel. |
| Banks, dealers, and hedge funds are typical cross-border repo participants; hedge funds are mostly cash borrowers. | This supports the leveraged Treasury-plumbing mechanism used in BTAR. |
| About 74% of cross-border repos are U.S.-dollar-denominated and typically backed by U.S. collateral. | The channel is directly relevant to dollar funding and Treasury collateral stress. |

Interpretation: OFR validates the transmission channel, not UAE attribution. The evidence says the cross-border repo pipe is large and dollar-heavy; UAE-specific exposure still has to be inferred from CBUAE, BIS, TIC, FICC, and scenario analysis.

Source: OFR, 'Sizing the U.S. Cross-Border Repo Market,' published April 9, 2026: https://www.financialresearch.gov/the-ofr-blog/2026/04/09/sizing-the-us-cross-border-repo-market/

## Policy implication

The U.S. incentive to provide a swap or liquidity backstop is structural: it can be cheaper to liquefy a foreign dollar node than to allow disorderly selling through Treasury and repo markets. But this also reinforces the dollar system's Dutch-disease problem: global surplus keeps routing into U.S. financial assets, the U.S. backstops the plumbing in stress, and the financial sink grows larger relative to the tradable real economy.

## Interpretation

Phase 1 should not be read as proof that UAE was short of reserves.

The stronger interpretation is that UAE may be reserve-rich while the immediately deployable cash/deposit layer is smaller than headline reserves imply.

The unresolved research question is where the securities-like and externally routed dollar stock sits: TIC-visible Treasuries, TIC non-Treasury securities, BIS banking/custody channels, external managers, MMFs, hedge funds, sponsored repo, or FX derivatives.
