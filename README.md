# Stock Elephant -- Part IVB Empirical Data
@Vinodh_Rag / Speculativa

Empirical data and scripts supporting **The Stock Elephant, Part IVB: When Dollar Wealth Is Not Liquidity**.

Published at: https://speculativa.substack.com

---

## Key Findings

### CBUAE Reserve Composition (2026-02-28)
- Gross reserves: $302.4B
- Cash and deposits abroad: $73.6B (24.4% of gross)
- Foreign investments: $207.6B (68.7% of gross)
- Composition shift: cash share has fallen as foreign investments dominate

### UAE Liquidity Cliff (CLC)
- 3-month CLC: 0.63 (cash/deposit layer covers 63% of three months of imports)
- 6-month CLC: 0.32
- First recent 3m CLC crossing below 1: 2025-06-30
- Implied monthly imports: $38.7B (CEIC reconstruction)

### BIS Locational Banking Statistics
- Global USD liabilities to UAE counterparties: $726.0B (2025-Q3)
- Sample peak: $739.9B (2025-Q2)
- Top implied reporter hub: United Kingdom ($320.4B, 44.1%)

### Sovereign Investment Context
- UAE sovereign / quasi-sovereign AUM in scope: $1.94T
- Estimated USD-denominated exposure: $1.29T
- AUM / CBUAE gross reserves: 6.4x

### BTAR Scale Test
- CBUAE foreign investments, mid scenario (2.5% encumbered, 25x leverage): BTAR = 1.19
- BIS USD liabilities, low scenario (1.0% encumbered, 20x leverage): BTAR = 1.33
- Scale discipline applied to observable UAE-linked layers, not an attribution claim

### Pre-event Threshold Sequence
- 2024-Q1: 6m CLC < 1
- 2025-Q1 to Q3: reserve composition shifts; 3m CLC < 1; BIS USD liabilities elevated
- 2025-Q3: Low BTAR > 1
- 2026-Q2: Bessent signal (policy marker)

---

## Repository Structure

    data/      -- Source data (CBUAE, BIS, FICC, country panel)
    outputs/   -- Analysis outputs
      stats/   -- Numerical results (CSV/JSON)
      plots/   -- Generated figures
      reports/ -- Synthesis writeups
      csv/     -- Reproducible CSV outputs
    scripts/   -- Analysis scripts

---

## Data Sources

- CBUAE Statistical Bulletin, Table 6 (https://www.centralbank.ae)
- BIS Locational Banking Statistics (https://www.bis.org/statistics/bankstats.htm)
- CEIC reserves-in-months-of-imports
- US Treasury TIC Major Foreign Holders
- IMF SDDS (UAE template, https://dsbb.imf.org)
- FRED (WALCL, EFFR, SOFR, IORB)
- OFR Cross-Border Repo (https://www.financialresearch.gov)
- FICC GSD Member Directory (DTCC)

---

## Citation

Raghunathan, V. (2026). "The Stock Elephant, Part IVB: When Dollar Wealth Is Not Liquidity."
Speculativa. https://speculativa.substack.com

---

*Data last updated: 2026-04-28*
