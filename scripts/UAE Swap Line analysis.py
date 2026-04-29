"""
PATCH FILE for Phase 1 — fixes crash + data pull issues.
Paste this as a NEW Cell AFTER the Phase 1 cell, then re-run main().

Fixes:
  1. Channel_6_FICC_Sponsored DataFrame construction bug (mismatched list lengths)
  2. BIS LBS / Debt filter: tolerate alternate column naming
  3. TIC SHL/SHC: fall back to older year if newest not released
  4. TIC MFH: parse multi-line header correctly
  5. Primary dealer Excel: specify engine
"""

import os
import io
import zipfile
from pathlib import Path
import numpy as np
import pandas as pd
import requests
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter

BASE = Path('/content/drive/MyDrive/StockElephant/uae_swap_line_analysis')
DATA_DIR = BASE / 'data'
OUT_DIR = BASE / 'outputs'
OUT_CSV = OUT_DIR / 'csv'
OUT_PLOTS = OUT_DIR / 'plots'
OUT_REPORTS = OUT_DIR / 'reports'

def load_ficc_gsd():
    f = DATA_DIR / 'Mem-GOV-by-name.xlsx'
    df = pd.read_excel(f, sheet_name=0, header=8)
    df.columns = ['Member_Number', 'Member_Name', 'Services']
    df = df.dropna(subset=['Member_Name'])
    df['Member_Name'] = df['Member_Name'].astype(str).str.strip()
    return df


def load_ficc_ccit():
    f = DATA_DIR / 'FICC-GSD-Member-Directory-CCIT.xlsx'
    df = pd.read_excel(f, sheet_name=0)
    df.columns = ['Member_ID', 'Member_Name']
    df = df.iloc[1:].reset_index(drop=True)
    df['Member_Name'] = df['Member_Name'].astype(str).str.strip()
    return df

def extract_stress_signals(te_us):
    """Extract US-side stress signals from Trading Economics data."""
    sigs = {}

    fed_bs = te_us[te_us['Category'] == 'Central Bank Balance Sheet'].copy()
    fed_bs = fed_bs[['DateTime', 'Value']].rename(
        columns={'DateTime': 'date', 'Value': 'value'}
    )
    fed_bs['value_bn'] = fed_bs['value'] / 1000
    sigs['fed_bs'] = fed_bs

    sofr = te_us[te_us['Category'] == 'Secured Overnight Financing Rate'].copy()
    sofr = sofr[['DateTime', 'Value']].rename(
        columns={'DateTime': 'date', 'Value': 'rate'}
    )
    sigs['sofr'] = sofr

    effr = te_us[te_us['Category'] == 'Effective Federal Funds Rate'].copy()
    effr = effr[['DateTime', 'Value']].rename(
        columns={'DateTime': 'date', 'Value': 'rate'}
    )
    sigs['effr'] = effr

    spread = pd.merge_asof(
        sofr.sort_values('date'),
        effr.sort_values('date').rename(columns={'rate': 'effr'}),
        on='date',
        direction='backward'
    )
    spread['sofr_minus_effr_bp'] = (spread['rate'] - spread['effr']) * 100
    sigs['sofr_effr_spread'] = spread

    for country, cat in [
        ('aggregate', 'Foreign Treasury Holdings'),
        ('UK', 'Foreign Treasury Holdings UK'),
        ('Belgium', 'Foreign Treasury Holdings Belgium'),
        ('Canada', 'Foreign Treasury Holdings Canada'),
        ('Japan', 'Foreign Treasury Holdings Japan'),
        ('China', 'Foreign Treasury Holdings China'),
    ]:
        df = te_us[te_us['Category'] == cat].copy()
        df = df[['DateTime', 'Value']].rename(
            columns={'DateTime': 'date', 'Value': 'value_bn'}
        )
        sigs[f'treasury_{country}'] = df

    return sigs

def ficc_analysis(gsd, ccit):
    """Analyze FICC directories for UAE/Gulf presence and sponsor universe."""
    out = {}

    uae_keywords = [
        'UAE',
        'UNITED ARAB',
        'EMIRATES',
        'ABU DHABI',
        'DUBAI',
        'ADGM',
        'MUBADALA',
        'ADIA',
        'ADQ',
        'EMIRATES NBD',
        'MASHREQ',
        'FAB',
        'FIRST ABU DHABI',
        'ADCB',
        'DUBAI ISLAMIC',
        'SHARJAH',
        'CBUAE',
    ]

    gulf_keywords = [
        'QATAR',
        'KUWAIT',
        'SAUDI',
        'BAHRAIN',
        'OMAN',
        'PIF',
        'QIA',
        'GIC',
        'TEMASEK',
        'NORGES',
    ]

    sponsor_bank_keywords = [
        'JPMORGAN',
        'J.P. MORGAN',
        'CITI',
        'CITIBANK',
        'BANK OF AMERICA',
        'BOFA',
        'HSBC',
        'STANDARD CHARTERED',
        'BNY',
        'BANK OF NEW YORK',
        'STATE STREET',
        'NORTHERN TRUST',
        'BNP PARIBAS',
        'SOCIETE GENERALE',
        'DEUTSCHE BANK',
        'BARCLAYS',
        'GOLDMAN',
        'MORGAN STANLEY',
    ]

    uae_direct = pd.DataFrame()
    for kw in uae_keywords:
        hit = gsd[gsd['Member_Name'].str.upper().str.contains(kw, na=False)]
        hit = hit[~hit['Member_Name'].str.upper().str.contains('CANADIAN', na=False)]
        if len(hit) > 0:
            uae_direct = pd.concat([uae_direct, hit], ignore_index=True).drop_duplicates()

    gulf_direct = pd.DataFrame()
    for kw in gulf_keywords:
        hit = gsd[gsd['Member_Name'].str.upper().str.contains(kw, na=False)]
        if len(hit) > 0:
            gulf_direct = pd.concat([gulf_direct, hit], ignore_index=True).drop_duplicates()

    omnibus = gsd[gsd['Member_Name'].str.upper().str.contains('OMNIBUS', na=False)].copy()

    sponsors = pd.DataFrame()
    for kw in sponsor_bank_keywords:
        hit = gsd[gsd['Member_Name'].str.upper().str.contains(kw, na=False)]
        if len(hit) > 0:
            sponsors = pd.concat([sponsors, hit], ignore_index=True).drop_duplicates()

    potential_uae_sponsors = sponsors[
        sponsors['Member_Name'].str.upper().str.contains('OMNIBUS', na=False)
    ].copy()

    out['total_gsd_members'] = int(len(gsd))
    out['total_omnibus_accounts'] = int(len(omnibus))
    out['uae_direct_matches'] = int(len(uae_direct))
    out['gulf_direct_matches'] = int(len(gulf_direct))
    out['total_ccit_members'] = int(len(ccit))

    out['uae_direct'] = uae_direct
    out['gulf_direct'] = gulf_direct
    out['omnibus'] = omnibus
    out['potential_uae_sponsoring_omnibus'] = potential_uae_sponsors
    out['ccit'] = ccit

    uae_direct.to_csv(OUT_CSV / 'ficc_uae_direct_matches.csv', index=False)
    gulf_direct.to_csv(OUT_CSV / 'ficc_gulf_direct_matches.csv', index=False)
    omnibus.to_csv(OUT_CSV / 'ficc_omnibus_accounts.csv', index=False)
    potential_uae_sponsors.to_csv(OUT_CSV / 'ficc_potential_uae_sponsoring_omnibus.csv', index=False)
    ccit.to_csv(OUT_CSV / 'ficc_ccit_members.csv', index=False)

    print(f"  Total GSD members: {out['total_gsd_members']}")
    print(f"  Total omnibus accounts: {out['total_omnibus_accounts']}")
    print(f"  Direct UAE matches in GSD: {out['uae_direct_matches']}")
    print(f"  Direct Gulf matches in GSD: {out['gulf_direct_matches']}")
    print(f"  Total CCIT members: {out['total_ccit_members']}")
    print(f"  Saved FICC analysis CSVs to {OUT_CSV}")

    return out

def compute_uae_reserve_residual(uae_master, channels):
    """
    Compute UAE reserve residuals using official CBUAE reserve-composition data.

    Base source:
      CBUAE Statistical Bulletin February 2026,
      Table 6: Central Bank International Reserves.

    Primary residual:
      cbuae_liquidity_gap_bn
      = gross_reserves_bn - cash_deposits_abroad_bn

    Secondary residual:
      national_observable_residual_bn
      = gross_reserves_bn - cash_deposits_abroad_bn - ch1_tic_treasury_bn

    The primary residual is the Setser/Etra reserve-composition object.
    The secondary residual is a narrow observed-channel comparison.
    """
    cbuae_path = OUT_CSV / 'cbuae_reserve_composition.csv'

    if not cbuae_path.exists():
        raise RuntimeError(
            "Cannot compute CBUAE residuals because reserve-composition file is missing: "
            + str(cbuae_path)
            + ". Run load_cbuae_reserve_composition() before compute_uae_reserve_residual()."
        )

    cbuae = pd.read_csv(cbuae_path)

    required_cols = [
        'date',
        'gross_reserves_bn',
        'cash_deposits_abroad_bn',
        'foreign_investments_bn',
        'imf_sdr_bn',
        'other_foreign_assets_bn',
        'foreign_liabilities_bn',
        'net_international_reserves_bn',
        'cash_deposits_share_of_gross_reserves',
        'foreign_investments_share_of_gross_reserves',
    ]

    missing_cols = [col for col in required_cols if col not in cbuae.columns]
    if missing_cols:
        raise RuntimeError(
            "CBUAE reserve-composition file missing required columns: "
            + ", ".join(missing_cols)
        )

    merged = cbuae[required_cols].copy()
    merged['date'] = pd.to_datetime(merged['date'])

    for col in required_cols:
        if col != 'date':
            merged[col] = pd.to_numeric(merged[col], errors='coerce')

    merged = merged.dropna(subset=['date', 'gross_reserves_bn', 'cash_deposits_abroad_bn'])
    merged = merged.sort_values('date').reset_index(drop=True)

    ch1 = channels['Channel_1_TIC_Direct'][['date', 'value_usd_bn']].copy()
    ch1['date'] = pd.to_datetime(ch1['date'])
    ch1['value_usd_bn'] = pd.to_numeric(ch1['value_usd_bn'], errors='coerce')
    ch1 = ch1.rename(columns={'value_usd_bn': 'ch1_tic_treasury_bn'})
    ch1 = ch1.dropna(subset=['date']).sort_values('date')

    merged = pd.merge_asof(
        merged.sort_values('date'),
        ch1,
        on='date',
        direction='backward'
    )

    merged['ch1_tic_treasury_bn'] = merged['ch1_tic_treasury_bn'].fillna(0.0)

    merged['total_reserves_bn'] = merged['gross_reserves_bn']
    merged['ch8_cash_deposits_bn'] = merged['cash_deposits_abroad_bn']

    merged['cbuae_liquidity_gap_bn'] = (
        merged['gross_reserves_bn'] - merged['cash_deposits_abroad_bn']
    )

    merged['national_observable_bn'] = (
        merged['ch1_tic_treasury_bn'] + merged['cash_deposits_abroad_bn']
    )

    merged['national_observable_residual_bn'] = (
        merged['gross_reserves_bn'] - merged['national_observable_bn']
    )

    merged['observable_bn'] = merged['cash_deposits_abroad_bn']
    merged['residual_bn'] = merged['cbuae_liquidity_gap_bn']

    merged['residual_definition'] = (
        'CBUAE base. residual_bn = gross_reserves_bn - cash_deposits_abroad_bn; '
        'national_observable_residual_bn = gross_reserves_bn - cash_deposits_abroad_bn - ch1_tic_treasury_bn'
    )

    output_cols = [
        'date',
        'gross_reserves_bn',
        'total_reserves_bn',
        'cash_deposits_abroad_bn',
        'ch8_cash_deposits_bn',
        'foreign_investments_bn',
        'imf_sdr_bn',
        'other_foreign_assets_bn',
        'foreign_liabilities_bn',
        'net_international_reserves_bn',
        'cash_deposits_share_of_gross_reserves',
        'foreign_investments_share_of_gross_reserves',
        'ch1_tic_treasury_bn',
        'cbuae_liquidity_gap_bn',
        'national_observable_bn',
        'national_observable_residual_bn',
        'observable_bn',
        'residual_bn',
        'residual_definition',
    ]

    return merged[output_cols].tail(36)

def compute_uae_btar_scenarios(residual_df, channels, sigs):
    """
    Compute UAE-BTAR scenarios.

    UAE-BTAR is not an attribution claim.
    It estimates how large a gross Treasury-market unwind could become if a small
    share of UAE-linked dollar buckets is encumbered into leveraged Treasury plumbing.

    Formula:
      gross_unwind_bn = bucket_size_bn * encumbrance_share * leverage
      UAE_BTAR = gross_unwind_bn / absorption_capacity_bn
    """
    OUT_CSV.mkdir(parents=True, exist_ok=True)

    buckets = []

    if residual_df is not None and len(residual_df) > 0:
        r = residual_df.copy()
        r['date'] = pd.to_datetime(r['date'])
        r = r.sort_values('date')
        latest_resid = r.iloc[-1]

        buckets.append({
            'bucket': 'CBUAE foreign investments',
            'date': latest_resid['date'],
            'bucket_size_bn': float(latest_resid['foreign_investments_bn']),
            'source': 'CBUAE reserve composition'
        })

        buckets.append({
            'bucket': 'CBUAE liquidity gap',
            'date': latest_resid['date'],
            'bucket_size_bn': float(latest_resid['cbuae_liquidity_gap_bn']),
            'source': 'CBUAE gross reserves minus cash/deposits abroad'
        })

    if 'Channel_1_TIC_Direct' in channels and len(channels['Channel_1_TIC_Direct']) > 0:
        ch1 = channels['Channel_1_TIC_Direct'].copy()
        ch1['date'] = pd.to_datetime(ch1['date'])
        ch1['value_usd_bn'] = pd.to_numeric(ch1['value_usd_bn'], errors='coerce')
        ch1 = ch1.dropna(subset=['date', 'value_usd_bn']).sort_values('date')
        if len(ch1) > 0:
            latest_ch1 = ch1.iloc[-1]
            buckets.append({
                'bucket': 'TIC UAE Treasury holdings',
                'date': latest_ch1['date'],
                'bucket_size_bn': float(latest_ch1['value_usd_bn']),
                'source': latest_ch1.get('source', 'TIC MFH / supplemental reference')
            })

    bis_usd_path = OUT_CSV / 'channel_Channel_2_BIS_global_usd_liabilities.csv'
    if bis_usd_path.exists():
        bis_usd = pd.read_csv(bis_usd_path)
        bis_usd['date'] = pd.to_datetime(bis_usd['date'])
        bis_usd['value_usd_bn'] = pd.to_numeric(bis_usd['value_usd_bn'], errors='coerce')
        bis_usd = bis_usd.dropna(subset=['date', 'value_usd_bn']).sort_values('date')
        if len(bis_usd) > 0:
            latest_bis = bis_usd.iloc[-1]
            buckets.append({
                'bucket': 'BIS global USD liabilities to UAE',
                'date': latest_bis['date'],
                'bucket_size_bn': float(latest_bis['value_usd_bn']),
                'source': 'BIS LBS all reporting countries USD liabilities to UAE'
            })

    if not buckets:
        raise RuntimeError("No valid buckets available for UAE-BTAR calculation.")

    bucket_df = pd.DataFrame(buckets)

    fed_absorption_bn = np.nan
    absorption_source = 'Unavailable'

    fed_pivot_date = pd.Timestamp('2026-01-21')

    if sigs is not None and 'fed_bs' in sigs and len(sigs['fed_bs']) > 0:
        fed = sigs['fed_bs'].copy()
        fed['date'] = pd.to_datetime(fed['date'])
        fed['value_bn'] = pd.to_numeric(fed['value_bn'], errors='coerce')
        fed = fed.dropna(subset=['date', 'value_bn']).sort_values('date')

        after_pivot = fed[fed['date'] >= fed_pivot_date].copy()

        if len(after_pivot) >= 2:
            fed_start_date = after_pivot['date'].iloc[0]
            fed_end_date = after_pivot['date'].iloc[-1]
            fed_start_bn = float(after_pivot['value_bn'].iloc[0])
            fed_end_bn = float(after_pivot['value_bn'].iloc[-1])
            fed_absorption_bn = fed_end_bn - fed_start_bn

            absorption_source = (
                'Fed balance-sheet expansion from '
                + fed_start_date.strftime('%Y-%m-%d')
                + ' to '
                + fed_end_date.strftime('%Y-%m-%d')
            )

    if pd.isna(fed_absorption_bn) or fed_absorption_bn <= 0:
        fed_absorption_bn = 109.291
        absorption_source = (
            'Fallback: verified Fed balance-sheet expansion from 2026-01-21 to 2026-04-08'
        )

    scenarios = [
        {
            'scenario': 'low',
            'encumbrance_share': 0.01,
            'leverage_multiplier': 20.0,
        },
        {
            'scenario': 'mid',
            'encumbrance_share': 0.025,
            'leverage_multiplier': 25.0,
        },
        {
            'scenario': 'high',
            'encumbrance_share': 0.05,
            'leverage_multiplier': 30.0,
        },
    ]

    rows = []

    for _, b in bucket_df.iterrows():
        for s in scenarios:
            gross_unwind_bn = (
                float(b['bucket_size_bn'])
                * s['encumbrance_share']
                * s['leverage_multiplier']
            )

            rows.append({
                'bucket': b['bucket'],
                'bucket_date': b['date'],
                'bucket_size_bn': float(b['bucket_size_bn']),
                'scenario': s['scenario'],
                'encumbrance_share': s['encumbrance_share'],
                'leverage_multiplier': s['leverage_multiplier'],
                'gross_unwind_bn': gross_unwind_bn,
                'absorption_capacity_bn': fed_absorption_bn,
                'absorption_source': absorption_source,
                'uae_btar': gross_unwind_bn / fed_absorption_bn,
                'bucket_source': b['source'],
            })

    btar = pd.DataFrame(rows)

    btar_out = OUT_CSV / 'uae_btar_scenarios.csv'
    bucket_out = OUT_CSV / 'uae_btar_buckets.csv'

    btar.to_csv(btar_out, index=False)
    bucket_df.to_csv(bucket_out, index=False)

    print(f"  Saved UAE-BTAR scenarios to {btar_out}")
    print(f"  Saved UAE-BTAR buckets to {bucket_out}")
    print(btar.sort_values(['scenario', 'uae_btar'], ascending=[True, False]).to_string(index=False))

    return btar


def compute_uae_import_liquidity_clc(uae_master):
    """
    Compute real-economy UAE Liquidity Cliff Ratio using CEIC import-cover data.

    CEIC provides:
      - forex_reserves_monthly
      - fx_reserves_months_import

    Implied monthly imports:
      forex_reserves_monthly_bn / fx_reserves_months_import

    CBUAE provides:
      - cash_deposits_abroad_bn

    Real-economy CLC:
      CLC_real_3m = cash_deposits_abroad_bn / (3 * implied_monthly_imports_bn)
      CLC_real_6m = cash_deposits_abroad_bn / (6 * implied_monthly_imports_bn)
    """
    OUT_CSV.mkdir(parents=True, exist_ok=True)

    fx = uae_master[uae_master['series'] == 'forex_reserves_monthly'].copy()
    fx['date'] = pd.to_datetime(fx['date'])
    fx['fx_reserves_bn'] = pd.to_numeric(fx['value'], errors='coerce') / 1000
    fx = fx[['date', 'fx_reserves_bn']].dropna(subset=['date', 'fx_reserves_bn'])
    fx = fx.sort_values('date')

    cover = uae_master[uae_master['series'] == 'fx_reserves_months_import'].copy()
    cover['date'] = pd.to_datetime(cover['date'])
    cover['fx_reserves_months_import'] = pd.to_numeric(cover['value'], errors='coerce')
    cover = cover[['date', 'fx_reserves_months_import']].dropna(
        subset=['date', 'fx_reserves_months_import']
    )
    cover = cover.sort_values('date')

    ceic = pd.merge_asof(
        fx.sort_values('date'),
        cover.sort_values('date'),
        on='date',
        direction='backward'
    )

    ceic = ceic.dropna(subset=['fx_reserves_bn', 'fx_reserves_months_import'])
    ceic = ceic[ceic['fx_reserves_months_import'] > 0].copy()

    ceic['implied_monthly_imports_bn'] = (
        ceic['fx_reserves_bn'] / ceic['fx_reserves_months_import']
    )

    cbuae_path = OUT_CSV / 'cbuae_reserve_composition.csv'

    if not cbuae_path.exists():
        raise RuntimeError(
            "Cannot compute import CLC because CBUAE reserve-composition file is missing: "
            + str(cbuae_path)
        )

    cbuae = pd.read_csv(cbuae_path)
    cbuae['date'] = pd.to_datetime(cbuae['date'])
    cbuae['cash_deposits_abroad_bn'] = pd.to_numeric(
        cbuae['cash_deposits_abroad_bn'],
        errors='coerce'
    )
    cbuae = cbuae[['date', 'cash_deposits_abroad_bn']].dropna(
        subset=['date', 'cash_deposits_abroad_bn']
    )
    cbuae = cbuae.sort_values('date')

    merged = pd.merge_asof(
        cbuae.sort_values('date'),
        ceic.sort_values('date'),
        on='date',
        direction='backward'
    )

    merged = merged.dropna(subset=[
        'cash_deposits_abroad_bn',
        'implied_monthly_imports_bn',
    ])

    merged['import_need_3m_bn'] = 3.0 * merged['implied_monthly_imports_bn']
    merged['import_need_6m_bn'] = 6.0 * merged['implied_monthly_imports_bn']

    merged['clc_real_3m'] = (
        merged['cash_deposits_abroad_bn'] / merged['import_need_3m_bn']
    )

    merged['clc_real_6m'] = (
        merged['cash_deposits_abroad_bn'] / merged['import_need_6m_bn']
    )

    merged['clc_real_3m_state'] = np.where(
        merged['clc_real_3m'] >= 1.0,
        'above_cliff',
        'below_cliff'
    )

    merged['clc_real_6m_state'] = np.where(
        merged['clc_real_6m'] >= 1.0,
        'above_cliff',
        'below_cliff'
    )

    merged['source'] = (
        'CEIC implied imports from FX reserves/months of imports; '
        'CBUAE cash/deposits abroad from Table 6'
    )

    out = OUT_CSV / 'uae_import_liquidity_clc.csv'
    merged.to_csv(out, index=False)

    print(f"  Saved UAE import-liquidity CLC to {out}")
    print(merged.tail(10).to_string(index=False))

    return merged

def plot_uae_portfolio_breakout(uae_master):
    """Plot UAE annual portfolio investment flow."""
    pi = uae_master[uae_master['series'] == 'portfolio_investment'].copy()
    pi['date'] = pd.to_datetime(pi['date'])
    pi['value_usd_bn'] = pd.to_numeric(pi['value'], errors='coerce') / 1000
    pi = pi.dropna(subset=['date', 'value_usd_bn']).sort_values('date')

    if len(pi) == 0:
        print("  Skipping portfolio breakout plot: no portfolio_investment rows.")
        return None

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(pi['date'], pi['value_usd_bn'], width=250)

    ax.axhline(0, linewidth=0.8)
    ax.set_title('UAE Portfolio Investment Flow')
    ax.set_ylabel('USD bn')
    ax.set_xlabel('')

    if len(pi[pi['date'].dt.year == 2024]) > 0:
        y2024 = pi[pi['date'].dt.year == 2024].iloc[-1]
        ax.annotate(
            f"2024: ${y2024['value_usd_bn']:.1f}B",
            xy=(y2024['date'], y2024['value_usd_bn']),
            xytext=(y2024['date'], y2024['value_usd_bn'] * 1.05),
            ha='center'
        )

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    OUT_PLOTS.mkdir(parents=True, exist_ok=True)
    out = OUT_PLOTS / 'uae_portfolio_investment_breakout.png'
    plt.tight_layout()
    plt.savefig(out, bbox_inches='tight')
    plt.close()

    print(f"  Saved: {out}")
    return out
def plot_fed_bs_pivot(sigs):
    """Plot Fed balance sheet from 2012 onward."""
    if 'fed_bs' not in sigs:
        print("  Skipping Fed balance sheet plot: sigs['fed_bs'] missing.")
        return None

    fed = sigs['fed_bs'].copy()
    fed['date'] = pd.to_datetime(fed['date'])
    fed['value_bn'] = pd.to_numeric(fed['value_bn'], errors='coerce')
    fed = fed.dropna(subset=['date', 'value_bn']).sort_values('date')

    start_date = pd.Timestamp('2012-01-01')
    view = fed[fed['date'] >= start_date].copy()

    if len(view) == 0:
        print("  Skipping Fed balance sheet plot: no valid Fed balance sheet rows after 2012.")
        return None

    pivot = pd.Timestamp('2026-01-21')

    fig, ax = plt.subplots(figsize=(11.5, 6.0))

    ax.plot(
        view['date'],
        view['value_bn'],
        linewidth=2.4,
        color='#1f5a92',
        solid_capstyle='round'
    )

    ax.axvline(
        pivot,
        color='#b42318',
        linestyle='--',
        linewidth=1.4
    )

    if len(view[view['date'] >= pivot]) > 0:
        pivot_y = view.loc[view['date'] >= pivot, 'value_bn'].iloc[0]
        ax.annotate(
            'Fed pivot',
            xy=(pivot, pivot_y),
            xytext=(pd.Timestamp('2025-05-01'), view['value_bn'].min() + 0.15 * (view['value_bn'].max() - view['value_bn'].min())),
            fontsize=10,
            color='#b42318',
            arrowprops=dict(arrowstyle='-', color='#b42318', linewidth=0.8)
        )

    latest = view.iloc[-1]
    ax.text(
        latest['date'] + pd.Timedelta(days=70),
        latest['value_bn'],
        f"{latest['value_bn']:,.0f} bn",
        color='#1f5a92',
        fontsize=10,
        va='center'
    )

    ax.set_title(
        'Federal Reserve balance sheet',
        loc='left',
        fontsize=17,
        fontweight='bold',
        pad=18
    )

    ax.text(
        0.0,
        1.02,
        'Central bank balance sheet, weekly, USD bn',
        transform=ax.transAxes,
        fontsize=11,
        color='#444444',
        ha='left',
        va='bottom'
    )

    ax.set_ylabel('USD bn')
    ax.set_xlabel('')

    ax.grid(True, axis='y', color='#dddddd', linewidth=0.8)
    ax.grid(False, axis='x')

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.tick_params(axis='both', length=0)

    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, pos: f'{x:,.0f}'))

    ax.set_xlim(pd.Timestamp('2012-01-01'), view['date'].max() + pd.Timedelta(days=365))

    fig.text(
        0.08,
        0.025,
        'Source: Trading Economics / Federal Reserve',
        ha='left',
        va='bottom',
        fontsize=9,
        color='#555555'
    )

    OUT_PLOTS.mkdir(parents=True, exist_ok=True)
    out = OUT_PLOTS / 'fed_balance_sheet_pivot.png'

    fig.subplots_adjust(left=0.08, right=0.94, bottom=0.13, top=0.84)
    plt.savefig(out, dpi=300, facecolor='white')
    plt.close()

    print(f"  Saved: {out}")
    return out

def plot_sofr_effr_spread(sigs):
    """Plot SOFR minus EFFR spread in basis points."""
    if 'sofr_effr_spread' not in sigs:
        print("  Skipping SOFR-EFFR plot: sigs['sofr_effr_spread'] missing.")
        return None

    spread = sigs['sofr_effr_spread'].copy()
    spread['date'] = pd.to_datetime(spread['date'])
    spread['sofr_minus_effr_bp'] = pd.to_numeric(
        spread['sofr_minus_effr_bp'],
        errors='coerce'
    )
    spread = spread.dropna(subset=['date', 'sofr_minus_effr_bp']).sort_values('date')

    if len(spread) == 0:
        print("  Skipping SOFR-EFFR plot: no valid spread rows.")
        return None

    recent = spread[spread['date'] >= pd.Timestamp('2024-01-01')].copy()
    if len(recent) == 0:
        recent = spread.copy()

    fig, ax = plt.subplots(figsize=(10, 5))

    ax.plot(
        recent['date'],
        recent['sofr_minus_effr_bp'],
        linewidth=1.5
    )

    ax.axhline(0, linewidth=0.8)

    peak_idx = recent['sofr_minus_effr_bp'].idxmax()
    peak_date = recent.loc[peak_idx, 'date']
    peak_val = recent.loc[peak_idx, 'sofr_minus_effr_bp']

    ax.scatter(
        [peak_date],
        [peak_val],
        s=45,
        zorder=5
    )

    ax.annotate(
        f"Peak: {peak_val:.0f} bp",
        xy=(peak_date, peak_val),
        xytext=(peak_date - pd.Timedelta(days=120), peak_val * 0.85),
        ha='right',
        va='center',
        arrowprops=dict(arrowstyle='-', linewidth=0.8)
    )

    ax.set_title('SOFR minus EFFR Spread')
    ax.set_ylabel('Basis points')
    ax.set_xlabel('')

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    OUT_PLOTS.mkdir(parents=True, exist_ok=True)
    out = OUT_PLOTS / 'sofr_effr_spread.png'
    plt.tight_layout()
    plt.savefig(out, bbox_inches='tight')
    plt.close()

    print(f"  Saved: {out}")
    return out


def plot_custodial_reshuffle(sigs):
    """Publication figure: foreign Treasury holdings by major custodial countries."""
    required = [
        'treasury_Japan',
        'treasury_China',
        'treasury_UK',
        'treasury_Belgium',
        'treasury_Canada',
    ]

    missing = [name for name in required if name not in sigs]
    if missing:
        print("  Skipping custodial reshuffle plot. Missing series: " + ", ".join(missing))
        return None

    colors = {
        'Japan': '#c76e00',
        'China': '#6f4aa8',
        'UK': '#1f5a92',
        'Belgium': '#c42017',
        'Canada': '#1f7a4d',
    }

    fig, ax = plt.subplots(figsize=(11.8, 6.2))

    label_offsets = {
        'Japan': 0,
        'China': 0,
        'UK': 0,
        'Belgium': 0,
        'Canada': -6,
    }

    for name in required:
        df = sigs[name].copy()
        df['date'] = pd.to_datetime(df['date'])
        df['value_bn'] = pd.to_numeric(df['value_bn'], errors='coerce')
        df = df.dropna(subset=['date', 'value_bn']).sort_values('date')

        recent = df[df['date'] >= pd.Timestamp('2022-01-01')].copy()
        if len(recent) == 0:
            recent = df.copy()

        label = name.replace('treasury_', '')
        color = colors[label]

        ax.plot(
            recent['date'],
            recent['value_bn'],
            linewidth=2.5,
            color=color,
            solid_capstyle='round'
        )

        last = recent.iloc[-1]
        ax.text(
            last['date'] + pd.Timedelta(days=25),
            last['value_bn'] + label_offsets.get(label, 0),
            f"{label}  {last['value_bn']:.0f}",
            color=color,
            fontsize=10,
            va='center'
        )

    ax.set_title(
        'Foreign Treasury holdings by custodial country',
        loc='left',
        fontsize=17,
        fontweight='bold',
        pad=18
    )
    ax.text(
        0.0,
        1.02,
        'Selected custodial jurisdictions, monthly, USD bn',
        transform=ax.transAxes,
        fontsize=11,
        color='#444444',
        ha='left',
        va='bottom'
    )

    ax.set_ylabel('USD bn')
    ax.set_xlabel('')

    ax.grid(True, axis='y', color='#dddddd', linewidth=0.8)
    ax.grid(False, axis='x')

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.tick_params(axis='both', length=0)

    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=4))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, pos: f'{x:,.0f}'))

    all_dates = []
    for name in required:
        tmp = sigs[name].copy()
        tmp['date'] = pd.to_datetime(tmp['date'])
        tmp = tmp[tmp['date'] >= pd.Timestamp('2022-01-01')]
        if len(tmp) > 0:
            all_dates.append(tmp['date'].max())

    if all_dates:
        ax.set_xlim(pd.Timestamp('2022-01-01'), max(all_dates) + pd.Timedelta(days=120))

    fig.text(
        0.125,
        0.02,
        'Source: US Treasury TIC',
        ha='left',
        va='bottom',
        fontsize=9,
        color='#555555'
    )

    OUT_PLOTS.mkdir(parents=True, exist_ok=True)
    out = OUT_PLOTS / 'custodial_reshuffle.png'
    fig.subplots_adjust(left=0.08, right=0.90, bottom=0.14, top=0.84)
    plt.savefig(out, bbox_inches='tight', dpi=300, facecolor='white')
    plt.close()

    print(f"  Saved: {out}")
    return out

def plot_uae_reserves_buildup(uae_master):
    """
    Publication figure: UAE FX reserves and M2.

    Uses CEIC FX reserves where available and extends the FX reserve line
    with CBUAE gross reserves from the reserve-composition table.
    """
    fx = uae_master[uae_master['series'].astype(str).eq('forex_reserves_monthly')].copy()
    m2 = uae_master[uae_master['series'].astype(str).eq('M2')].copy()

    fx['date'] = pd.to_datetime(fx['date'])
    m2['date'] = pd.to_datetime(m2['date'])

    fx['value_usd_bn'] = pd.to_numeric(fx['value'], errors='coerce') / 1000.0
    m2['value_usd_bn'] = pd.to_numeric(m2['value'], errors='coerce') / 1000.0

    fx = (
        fx.dropna(subset=['date', 'value_usd_bn'])
          .sort_values('date')
          .groupby('date', as_index=False)['value_usd_bn']
          .last()
    )

    m2 = (
        m2.dropna(subset=['date', 'value_usd_bn'])
          .sort_values('date')
          .groupby('date', as_index=False)['value_usd_bn']
          .last()
    )

    cbuae_path = OUT_CSV / 'cbuae_reserve_composition.csv'
    if cbuae_path.exists():
        cbuae = pd.read_csv(cbuae_path)
        cbuae['date'] = pd.to_datetime(cbuae['date'])
        cbuae['value_usd_bn'] = pd.to_numeric(cbuae['gross_reserves_bn'], errors='coerce')
        cbuae = cbuae[['date', 'value_usd_bn']].dropna().sort_values('date')

        last_fx_date = fx['date'].max() if len(fx) > 0 else pd.Timestamp('1900-01-01')
        cbuae_extension = cbuae[cbuae['date'] > last_fx_date].copy()

        if len(cbuae_extension) > 0:
            fx = pd.concat([fx, cbuae_extension], ignore_index=True)
            fx = fx.sort_values('date').drop_duplicates(subset=['date'], keep='last')

    start = pd.Timestamp('2022-01-01')
    fx = fx[fx['date'] >= start].copy()
    m2 = m2[m2['date'] >= start].copy()

    if len(fx) == 0:
        print("  Skipping UAE reserves buildup plot: no FX reserve rows.")
        return None

    fig = plt.figure(figsize=(11.5, 6.2))
    ax = fig.add_axes([0.08, 0.16, 0.82, 0.66])

    ax.plot(
        fx['date'],
        fx['value_usd_bn'],
        linewidth=2.8,
        color='#1f5a92',
        solid_capstyle='round'
    )

    if len(m2) > 0:
        ax.plot(
            m2['date'],
            m2['value_usd_bn'],
            linewidth=2.8,
            color='#1f7a4d',
            solid_capstyle='round'
        )

    fig.text(
        0.08,
        0.965,
        'UAE FX reserves and domestic money base',
        ha='left',
        va='top',
        fontsize=19,
        fontweight='bold',
        color='#111111'
    )

    fig.text(
        0.08,
        0.918,
        'Monthly stock, USD bn',
        ha='left',
        va='top',
        fontsize=11.5,
        color='#444444'
    )

    ax.set_ylabel('USD bn')
    ax.set_xlabel('')

    ax.grid(True, axis='y', color='#dddddd', linewidth=0.8)
    ax.grid(False, axis='x')

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.tick_params(axis='both', length=0)

    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, pos: f'{x:,.0f}'))

    xmax = max(fx['date'].max(), m2['date'].max() if len(m2) > 0 else fx['date'].max())
    ax.set_xlim(start, xmax + pd.Timedelta(days=130))

    ymax = max(
        fx['value_usd_bn'].max(),
        m2['value_usd_bn'].max() if len(m2) > 0 else 0
    )
    ax.set_ylim(0, ymax * 1.10)

    fx_last = fx.iloc[-1]
    ax.text(
        fx_last['date'] + pd.Timedelta(days=30),
        fx_last['value_usd_bn'],
        f"FX reserves  {fx_last['value_usd_bn']:.0f}",
        color='#1f5a92',
        fontsize=10,
        va='center'
    )

    if len(m2) > 0:
        m2_last = m2.iloc[-1]
        ax.text(
            m2_last['date'] + pd.Timedelta(days=30),
            m2_last['value_usd_bn'],
            f"M2  {m2_last['value_usd_bn']:.0f}",
            color='#1f7a4d',
            fontsize=10,
            va='center'
        )

    fig.text(
        0.08,
        0.035,
        'Source: CEIC / CBUAE',
        ha='left',
        va='bottom',
        fontsize=9,
        color='#555555'
    )

    OUT_PLOTS.mkdir(parents=True, exist_ok=True)
    out = OUT_PLOTS / 'uae_fx_reserves_and_m2.png'
    plt.savefig(out, dpi=300, facecolor='white')
    plt.close()

    print(f"  Saved: {out}")
    return out

def plot_residual_gap(residual_df):
    """Publication figure: reserve composition and residual gap."""
    cbuae_path = OUT_CSV / 'cbuae_reserve_composition.csv'

    if not cbuae_path.exists():
        print(f"  Skipping residual gap plot: missing {cbuae_path}")
        return None

    comp = pd.read_csv(cbuae_path)
    comp['date'] = pd.to_datetime(comp['date'])
    comp = comp.sort_values('date').reset_index(drop=True)

    for col in [
        'gross_reserves_bn',
        'cash_deposits_abroad_bn',
        'foreign_investments_bn',
        'other_foreign_assets_bn',
        'imf_sdr_bn',
    ]:
        if col in comp.columns:
            comp[col] = pd.to_numeric(comp[col], errors='coerce')

    df = residual_df.copy()
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)

    residual_col = None
    for cand in [
        'national_observable_residual_bn',
        'cbuae_liquidity_gap_bn',
        'residual_bn',
    ]:
        if cand in df.columns:
            residual_col = cand
            break

    if residual_col is None:
        print("  Skipping residual gap panel: residual column not found.")
        return None

    df[residual_col] = pd.to_numeric(df[residual_col], errors='coerce')

    if len(comp) >= 2:
        gap_days = comp['date'].diff().dropna().dt.days
        bar_width = max(20, int(gap_days.median() * 0.70))
    else:
        bar_width = 45

    fig = plt.figure(figsize=(13.2, 7.2))

    fig.text(
        0.07,
        0.965,
        'UAE reserve composition and residual gap',
        ha='left',
        va='top',
        fontsize=19,
        fontweight='bold',
        color='#111111'
    )

    fig.text(
        0.07,
        0.918,
        'Reserve mix shifts toward foreign investments while the observable gap remains material',
        ha='left',
        va='top',
        fontsize=11.5,
        color='#444444'
    )

    ax = fig.add_axes([0.07, 0.16, 0.41, 0.60])
    ax2 = fig.add_axes([0.56, 0.16, 0.40, 0.60])

    bottom = np.zeros(len(comp))

    layers = [
        ('cash_deposits_abroad_bn', 'Cash and deposits', '#1f5a92'),
        ('foreign_investments_bn', 'Foreign investments', '#1f7a4d'),
        ('other_foreign_assets_bn', 'Other foreign assets', '#c76e00'),
        ('imf_sdr_bn', 'IMF / SDR', '#6f4aa8'),
    ]

    for col, label, color in layers:
        if col in comp.columns:
            vals = comp[col].fillna(0).values
            ax.bar(
                comp['date'],
                vals,
                bottom=bottom,
                width=bar_width,
                color=color,
                label=label
            )
            bottom = bottom + vals

    if 'gross_reserves_bn' in comp.columns:
        ax.plot(
            comp['date'],
            comp['gross_reserves_bn'],
            color='#111111',
            linewidth=2.4,
            label='Gross reserves'
        )

    ax.set_title(
        'Reserve composition',
        loc='left',
        fontsize=13,
        fontweight='bold',
        pad=10
    )

    ax.set_ylabel('USD bn')
    ax.set_xlabel('')
    ax.grid(True, axis='y', color='#dddddd', linewidth=0.8)
    ax.grid(False, axis='x')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.tick_params(axis='both', length=0)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, pos: f'{x:,.0f}'))

    handles, labels = ax.get_legend_handles_labels()
    order = {
        'Gross reserves': 0,
        'Cash and deposits': 1,
        'Foreign investments': 2,
        'Other foreign assets': 3,
        'IMF / SDR': 4,
    }
    ordered = sorted(zip(handles, labels), key=lambda x: order.get(x[1], 999))

    ax.legend(
        [h for h, _ in ordered],
        [l for _, l in ordered],
        frameon=False,
        loc='upper left',
        bbox_to_anchor=(0.00, 0.98),
        borderaxespad=0.0
    )

    bar_colors = np.where(df[residual_col] >= 0, '#c42017', '#9e9e9e')

    ax2.bar(
        df['date'],
        df[residual_col],
        width=bar_width,
        color=bar_colors
    )

    ax2.axhline(0, color='#666666', linewidth=1.0, linestyle='--')

    ax2.set_title(
        'Residual gap',
        loc='left',
        fontsize=13,
        fontweight='bold',
        pad=10
    )

    ax2.set_ylabel('USD bn')
    ax2.set_xlabel('')
    ax2.grid(True, axis='y', color='#dddddd', linewidth=0.8)
    ax2.grid(False, axis='x')
    ax2.spines['top'].set_visible(False)
    ax2.spines['right'].set_visible(False)
    ax2.tick_params(axis='both', length=0)
    ax2.xaxis.set_major_locator(mdates.YearLocator())
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda x, pos: f'{x:,.0f}'))

    xmin = min(comp['date'].min(), df['date'].min()) - pd.Timedelta(days=45)
    xmax = max(comp['date'].max(), df['date'].max()) + pd.Timedelta(days=45)

    ax.set_xlim(xmin, xmax)
    ax2.set_xlim(xmin, xmax)

    fig.text(
        0.07,
        0.035,
        'Source: CBUAE, TIC, BIS LBS, author calculations',
        ha='left',
        va='bottom',
        fontsize=9,
        color='#555555'
    )

    OUT_PLOTS.mkdir(parents=True, exist_ok=True)
    out = OUT_PLOTS / 'uae_residual_gap.png'
    plt.savefig(out, dpi=300, facecolor='white')
    plt.close()

    print(f"  Saved: {out}")
    return out

def write_summary_report(channels, sigs, ficc_out, residual_df, uae_master):
    """Write Phase 1 summary report."""
    OUT_REPORTS.mkdir(parents=True, exist_ok=True)

    def latest_series_value(series_name):
        df = uae_master[uae_master['series'] == series_name].copy()
        if len(df) == 0:
            return None, None
        df['date'] = pd.to_datetime(df['date'])
        df['value'] = pd.to_numeric(df['value'], errors='coerce')
        df = df.dropna(subset=['date', 'value']).sort_values('date')
        if len(df) == 0:
            return None, None
        row = df.iloc[-1]
        return float(row['value']) / 1000, row['date'].strftime('%Y-%m')

    fx_bn, fx_date = latest_series_value('forex_reserves_monthly')
    gold_bn, gold_date = latest_series_value('gold_reserves')
    m1_bn, m1_date = latest_series_value('M1')
    m2_bn, m2_date = latest_series_value('M2')
    pi_bn, pi_date = latest_series_value('portfolio_investment')

    latest_resid = None
    if residual_df is not None and len(residual_df) > 0:
        r = residual_df.copy()
        r['date'] = pd.to_datetime(r['date'])
        r = r.sort_values('date')
        latest_resid = r.iloc[-1]

    def fmt_bn(x):
        if x is None or pd.isna(x):
            return "n/a"
        return f"${float(x):,.1f}B"

    def fmt_pct(x):
        if x is None or pd.isna(x):
            return "n/a"
        return f"{float(x):,.1f}%"

    fed_latest = None
    if 'fed_bs' in sigs and len(sigs['fed_bs']) > 0:
        fed = sigs['fed_bs'].copy()
        fed['date'] = pd.to_datetime(fed['date'])
        fed = fed.sort_values('date')
        fed_latest = fed.iloc[-1]

    spread_latest = None
    if 'sofr_effr_spread' in sigs and len(sigs['sofr_effr_spread']) > 0:
        spread = sigs['sofr_effr_spread'].copy()
        spread['date'] = pd.to_datetime(spread['date'])
        spread = spread.dropna(subset=['sofr_minus_effr_bp']).sort_values('date')
        if len(spread) > 0:
            spread_latest = spread.iloc[-1]

    report = []
    report.append("# UAE Swap Line Analysis — Phase 1 Summary")
    report.append("")
    report.append(f"Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
    report.append("")
    report.append("## Core question")
    report.append("")
    report.append("Phase 1 asks whether the UAE swap-line issue is a reserve-quantity problem or a reserve-composition problem.")
    report.append("")
    report.append("The key distinction is headline reserves versus immediately deployable dollar liquidity.")
    report.append("")
    report.append("## UAE CEIC balance-sheet snapshot")
    report.append("")
    report.append("| Item | Value | As of |")
    report.append("|---|---:|---|")
    report.append(f"| FX reserves, ex-gold | {fmt_bn(fx_bn)} | {fx_date or 'n/a'} |")
    report.append(f"| Gold reserves | {fmt_bn(gold_bn)} | {gold_date or 'n/a'} |")
    report.append(f"| M1 money supply | {fmt_bn(m1_bn)} | {m1_date or 'n/a'} |")
    report.append(f"| M2 money supply | {fmt_bn(m2_bn)} | {m2_date or 'n/a'} |")
    report.append(f"| Portfolio investment flow | {fmt_bn(pi_bn)} | {pi_date or 'n/a'} |")
    report.append("")

    if fx_bn is not None and m1_bn is not None and m1_bn != 0:
        report.append(f"- FX reserves / M1: {fmt_pct(100 * fx_bn / m1_bn)}")
    if fx_bn is not None and m2_bn is not None and m2_bn != 0:
        report.append(f"- FX reserves / M2: {fmt_pct(100 * fx_bn / m2_bn)}")
    report.append("")

    report.append("## Reserve residuals")
    report.append("")
    if latest_resid is not None:
        report.append("| Component | Value |")
        report.append("|---|---:|")
        report.append(f"| Total FX reserves | {fmt_bn(latest_resid.get('total_reserves_bn'))} |")
        report.append(f"| Channel 8 cash/deposits | {fmt_bn(latest_resid.get('ch8_cash_deposits_bn'))} |")
        report.append(f"| Channel 1 TIC Treasuries | {fmt_bn(latest_resid.get('ch1_tic_treasury_bn'))} |")
        report.append(f"| CBUAE liquidity gap | {fmt_bn(latest_resid.get('cbuae_liquidity_gap_bn'))} |")
        report.append(f"| National observable residual | {fmt_bn(latest_resid.get('national_observable_residual_bn'))} |")
        report.append("")
        report.append("Definitions:")
        report.append("")
        report.append("- CBUAE liquidity gap = total FX reserves minus Channel 8 cash/deposits.")
        report.append("- National observable residual = total FX reserves minus Channel 8 cash/deposits minus Channel 1 TIC Treasuries.")
    else:
        report.append("Residual table was not available.")
    report.append("")

    report.append("## Channel availability")
    report.append("")
    report.append("| Channel | Rows | Latest headline value | Latest date |")
    report.append("|---|---:|---:|---|")

    bis_global_path = OUT_CSV / 'channel_Channel_2_BIS_global_usd_liabilities.csv'
    bis_global_latest_value = None
    bis_global_latest_date = None

    if bis_global_path.exists():
        bis_global = pd.read_csv(bis_global_path)
        bis_global['date'] = pd.to_datetime(bis_global['date'])
        bis_global['value_usd_bn'] = pd.to_numeric(bis_global['value_usd_bn'], errors='coerce')
        bis_global = bis_global.dropna(subset=['date', 'value_usd_bn']).sort_values('date')

        if len(bis_global) > 0:
            latest_bis_row = bis_global.iloc[-1]
            bis_global_latest_value = latest_bis_row['value_usd_bn']
            bis_global_latest_date = latest_bis_row['date'].strftime('%Y-%m-%d')

    for name, df in channels.items():
        latest_val = None
        latest_date = None
        latest_note = None

        if name == 'Channel_2_NonUS_Custody':
            latest_val = bis_global_latest_value
            latest_date = bis_global_latest_date
            latest_note = 'BIS global USD liabilities to UAE'
        elif df is not None and len(df) > 0 and 'date' in df.columns and 'value_usd_bn' in df.columns:
            tmp = df.copy()
            tmp['date'] = pd.to_datetime(tmp['date'])
            tmp['value_usd_bn'] = pd.to_numeric(tmp['value_usd_bn'], errors='coerce')
            tmp = tmp.dropna(subset=['date']).sort_values('date')
            non_null = tmp.dropna(subset=['value_usd_bn'])

            if len(non_null) > 0:
                row = non_null.iloc[-1]
                latest_val = row['value_usd_bn']
                latest_date = row['date'].strftime('%Y-%m-%d')

        display_value = fmt_bn(latest_val)

        if latest_note is not None and display_value != 'n/a':
            display_value = display_value + f" ({latest_note})"

        report.append(
            f"| {name} | {0 if df is None else len(df)} | {display_value} | {latest_date or 'n/a'} |"
        )

    report.append("")

    report.append("## US-side stress signals")
    report.append("")
    report.append("| Signal | Latest value | Date |")
    report.append("|---|---:|---|")
    if fed_latest is not None:
        report.append(f"| Fed balance sheet | {fmt_bn(fed_latest.get('value_bn'))} | {pd.to_datetime(fed_latest.get('date')).strftime('%Y-%m-%d')} |")
    if spread_latest is not None:
        report.append(f"| SOFR-EFFR spread | {float(spread_latest.get('sofr_minus_effr_bp')):,.1f} bp | {pd.to_datetime(spread_latest.get('date')).strftime('%Y-%m-%d')} |")
    report.append("")

    report.append("## FICC analysis")
    report.append("")
    report.append(f"- Total GSD members: {ficc_out.get('total_gsd_members', 'n/a')}")
    report.append(f"- Total omnibus accounts: {ficc_out.get('total_omnibus_accounts', 'n/a')}")
    report.append(f"- Direct UAE matches in GSD: {ficc_out.get('uae_direct_matches', 'n/a')}")
    report.append(f"- Direct Gulf matches in GSD: {ficc_out.get('gulf_direct_matches', 'n/a')}")
    report.append(f"- Total CCIT members: {ficc_out.get('total_ccit_members', 'n/a')}")
    report.append("")

    report.append("## CBUAE reserve-composition finding")
    report.append("")

    cbuae_path = OUT_CSV / 'cbuae_reserve_composition.csv'
    if cbuae_path.exists():
        cbuae = pd.read_csv(cbuae_path)
        cbuae['date'] = pd.to_datetime(cbuae['date'])
        cbuae = cbuae.sort_values('date')

        if len(cbuae) > 0:
            latest_cb = cbuae.iloc[-1]

            report.append("| Component | Latest value | Date |")
            report.append("|---|---:|---|")
            report.append(
                f"| Gross reserves | {fmt_bn(latest_cb.get('gross_reserves_bn'))} | "
                f"{pd.to_datetime(latest_cb.get('date')).strftime('%Y-%m-%d')} |"
            )
            report.append(
                f"| Cash/deposits abroad | {fmt_bn(latest_cb.get('cash_deposits_abroad_bn'))} | "
                f"{pd.to_datetime(latest_cb.get('date')).strftime('%Y-%m-%d')} |"
            )
            report.append(
                f"| Foreign investments | {fmt_bn(latest_cb.get('foreign_investments_bn'))} | "
                f"{pd.to_datetime(latest_cb.get('date')).strftime('%Y-%m-%d')} |"
            )
            report.append(
                f"| Cash/deposits share of gross reserves | "
                f"{fmt_pct(100 * latest_cb.get('cash_deposits_share_of_gross_reserves'))} | "
                f"{pd.to_datetime(latest_cb.get('date')).strftime('%Y-%m-%d')} |"
            )
            report.append(
                f"| Foreign-investments share of gross reserves | "
                f"{fmt_pct(100 * latest_cb.get('foreign_investments_share_of_gross_reserves'))} | "
                f"{pd.to_datetime(latest_cb.get('date')).strftime('%Y-%m-%d')} |"
            )
            report.append("")
            report.append(
                "CBUAE data show that the central-bank reserve issue is composition, not scarcity: "
                "cash/deposit-like reserves fell sharply as a share of gross reserves while foreign investments became dominant."
            )
    else:
        report.append("CBUAE reserve-composition table was not available.")
    report.append("")

    report.append("## BIS dollar-routing finding")
    report.append("")

    bis_global_path = OUT_CSV / 'channel_Channel_2_BIS_global_usd_liabilities.csv'
    if bis_global_path.exists():
        bis_global = pd.read_csv(bis_global_path)
        bis_global['date'] = pd.to_datetime(bis_global['date'])
        bis_global['value_usd_bn'] = pd.to_numeric(bis_global['value_usd_bn'], errors='coerce')
        bis_global = bis_global.dropna(subset=['date', 'value_usd_bn']).sort_values('date')

        if len(bis_global) > 0:
            latest_bis = bis_global.iloc[-1]
            report.append("| Measure | Latest value | Date |")
            report.append("|---|---:|---|")
            report.append(
                f"| BIS global USD liabilities to UAE | {fmt_bn(latest_bis.get('value_usd_bn'))} | "
                f"{pd.to_datetime(latest_bis.get('date')).strftime('%Y-%m-%d')} |"
            )
            report.append("")
            report.append(
                "BIS data indicate that the broader UAE-linked dollar banking footprint is far larger than the CBUAE reserve headline. "
                "This is a dollar-routing layer, not proof of basis-trade exposure."
            )
    else:
        report.append("BIS global USD liabilities file was not available.")
    report.append("")

    implied_path = OUT_CSV / 'channel_Channel_2_BIS_implied_reporter_usd_deposit_liabilities.csv'
    if implied_path.exists():
        implied = pd.read_csv(implied_path)
        implied['date'] = pd.to_datetime(implied['date'])
        implied['implied_reporter_usd_deposit_liabilities_bn'] = pd.to_numeric(
            implied['implied_reporter_usd_deposit_liabilities_bn'],
            errors='coerce'
        )
        implied = implied.dropna(subset=['date', 'implied_reporter_usd_deposit_liabilities_bn'])

        if len(implied) > 0:
            latest_date = implied['date'].max()
            latest_implied = implied[implied['date'] == latest_date].copy()
            latest_implied = latest_implied.sort_values(
                'implied_reporter_usd_deposit_liabilities_bn',
                ascending=False
            )

            report.append("Top BIS-implied reporter USD routing hubs:")
            report.append("")
            report.append("| Reporter | Implied USD liabilities to UAE | Share |")
            report.append("|---|---:|---:|")

            for _, row in latest_implied.head(10).iterrows():
                share = row.get('reporter_share_of_all_currency_liabilities')
                report.append(
                    f"| {row.get('reporter_country')} | "
                    f"{fmt_bn(row.get('implied_reporter_usd_deposit_liabilities_bn'))} | "
                    f"{fmt_pct(100 * share) if pd.notna(share) else 'n/a'} |"
                )

            report.append("")
            report.append(
                "This reporter-country allocation is implied, not directly reported: "
                "global BIS USD liabilities to UAE are distributed by reporter-country all-currency loans/deposits liability shares."
            )
    else:
        report.append("BIS-implied reporter USD allocation file was not available.")
    report.append("")

    report.append("## UAE-BTAR scenario results")
    report.append("")

    btar_path = OUT_CSV / 'uae_btar_scenarios.csv'
    if btar_path.exists():
        btar = pd.read_csv(btar_path)
        btar['uae_btar'] = pd.to_numeric(btar['uae_btar'], errors='coerce')
        btar['gross_unwind_bn'] = pd.to_numeric(btar['gross_unwind_bn'], errors='coerce')
        btar['absorption_capacity_bn'] = pd.to_numeric(btar['absorption_capacity_bn'], errors='coerce')

        if len(btar) > 0:
            report.append("| Bucket | Scenario | Gross unwind | Absorption capacity | UAE-BTAR |")
            report.append("|---|---|---:|---:|---:|")

            btar_display = btar.sort_values(['scenario', 'uae_btar'], ascending=[True, False])

            for _, row in btar_display.iterrows():
                report.append(
                    f"| {row.get('bucket')} | {row.get('scenario')} | "
                    f"{fmt_bn(row.get('gross_unwind_bn'))} | "
                    f"{fmt_bn(row.get('absorption_capacity_bn'))} | "
                    f"{float(row.get('uae_btar')):,.2f} |"
                )

            absorption_sources = btar['absorption_source'].dropna().astype(str).drop_duplicates().tolist()
            if absorption_sources:
                report.append("")
                report.append("Absorption denominator:")
                for src in absorption_sources:
                    report.append(f"- {src}")

            report.append("")
            report.append(
                "UAE-BTAR is not an attribution claim. It is a leverage-adjusted absorption test: "
                "if a small share of UAE-linked dollar buckets is encumbered into leveraged Treasury plumbing, "
                "the gross unwind can be large relative to the observed Fed balance-sheet expansion."
            )
    else:
        report.append("UAE-BTAR scenario table was not available.")
    report.append("")

    report.append("## UAE Liquidity Cliff Ratio")
    report.append("")

    clc_path = OUT_CSV / 'uae_import_liquidity_clc.csv'

    if clc_path.exists():
        clc = pd.read_csv(clc_path)
        clc['date'] = pd.to_datetime(clc['date'])

        numeric_cols = [
            'cash_deposits_abroad_bn',
            'implied_monthly_imports_bn',
            'import_need_3m_bn',
            'import_need_6m_bn',
            'clc_real_3m',
            'clc_real_6m',
        ]

        for col in numeric_cols:
            if col in clc.columns:
                clc[col] = pd.to_numeric(clc[col], errors='coerce')

        clc = clc.dropna(subset=['date']).sort_values('date')

        if len(clc) > 0:
            latest_clc = clc.iloc[-1]

            report.append("| Metric | Latest value | Date |")
            report.append("|---|---:|---|")
            report.append(
                f"| Cash/deposits abroad | {fmt_bn(latest_clc.get('cash_deposits_abroad_bn'))} | "
                f"{pd.to_datetime(latest_clc.get('date')).strftime('%Y-%m-%d')} |"
            )
            report.append(
                f"| Implied monthly imports | {fmt_bn(latest_clc.get('implied_monthly_imports_bn'))} | "
                f"{pd.to_datetime(latest_clc.get('date')).strftime('%Y-%m-%d')} |"
            )
            report.append(
                f"| 3-month import need | {fmt_bn(latest_clc.get('import_need_3m_bn'))} | "
                f"{pd.to_datetime(latest_clc.get('date')).strftime('%Y-%m-%d')} |"
            )
            report.append(
                f"| 6-month import need | {fmt_bn(latest_clc.get('import_need_6m_bn'))} | "
                f"{pd.to_datetime(latest_clc.get('date')).strftime('%Y-%m-%d')} |"
            )
            report.append(
                f"| CLC real 3m | {float(latest_clc.get('clc_real_3m')):,.2f} | "
                f"{pd.to_datetime(latest_clc.get('date')).strftime('%Y-%m-%d')} |"
            )
            report.append(
                f"| CLC real 6m | {float(latest_clc.get('clc_real_6m')):,.2f} | "
                f"{pd.to_datetime(latest_clc.get('date')).strftime('%Y-%m-%d')} |"
            )
            report.append("")

            cbuae_window_start = pd.Timestamp('2024-03-31')
            clc_window = clc[clc['date'] >= cbuae_window_start].copy()

            below_3m = clc_window[clc_window['clc_real_3m'] < 1.0].copy()
            below_6m = clc_window[clc_window['clc_real_6m'] < 1.0].copy()

            if len(below_3m) > 0:
                first_3m = below_3m.iloc[0]
                report.append(
                    f"- First recent 3-month import-liquidity cliff crossing since "
                    f"{cbuae_window_start.strftime('%Y-%m-%d')}: "
                    f"{pd.to_datetime(first_3m.get('date')).strftime('%Y-%m-%d')} "
                    f"(CLC real 3m = {float(first_3m.get('clc_real_3m')):,.2f})."
                )
            else:
                report.append(
                    f"- 3-month import-liquidity CLC stayed above one throughout the "
                    f"CBUAE reserve-composition window beginning {cbuae_window_start.strftime('%Y-%m-%d')}."
                )

            if len(clc_window) > 0 and (clc_window['clc_real_6m'] < 1.0).all():
                report.append(
                    f"- 6-month import-liquidity CLC was below one throughout the "
                    f"CBUAE reserve-composition window beginning {cbuae_window_start.strftime('%Y-%m-%d')}."
                )
            elif len(below_6m) > 0:
                first_6m = below_6m.iloc[0]
                report.append(
                    f"- First recent 6-month import-liquidity cliff crossing since "
                    f"{cbuae_window_start.strftime('%Y-%m-%d')}: "
                    f"{pd.to_datetime(first_6m.get('date')).strftime('%Y-%m-%d')} "
                    f"(CLC real 6m = {float(first_6m.get('clc_real_6m')):,.2f})."
                )
            else:
                report.append(
                    f"- 6-month import-liquidity CLC stayed above one throughout the "
                    f"CBUAE reserve-composition window beginning {cbuae_window_start.strftime('%Y-%m-%d')}."
                )

            report.append("")
            report.append(
                "CLC is the UAE-side hard-constraint metric. It measures whether immediately deployable "
                "cash/deposit liquidity covers near-term real-economy dollar needs. CLC below one means "
                "cash/deposits alone do not cover the selected import-liquidity floor."
            )
            report.append("")
            report.append(
                "Caveat: implied monthly imports are reconstructed from CEIC FX reserves and "
                "FX-reserves-in-months-of-imports. Where CEIC import-cover data lag CBUAE reserve data, "
                "the latest available CEIC import-cover observation is carried forward."
            )
    else:
        report.append("UAE import-liquidity CLC table was not available.")
    report.append("")

    report.append("## Cross-border repo market context")
    report.append("")
    report.append(
        "OFR's April 2026 cross-border repo analysis strengthens the mechanism behind BTAR. "
        "It does not identify UAE-specific repo exposure, but it shows that cross-border repo is a large, dollar-heavy transmission channel."
    )
    report.append("")
    report.append("| OFR finding | Relevance to this analysis |")
    report.append("|---|---|")
    report.append(
        "| Cross-border repos are about one-third of the U.S. repo market. | "
        "Foreign dollar nodes can transmit stress into U.S. repo and Treasury collateral markets. |"
    )
    report.append(
        "| Daily average U.S. repo outstanding was about $12.75T from July 2025 to February 2026. | "
        "The relevant market plumbing is multi-trillion scale. |"
    )
    report.append(
        "| In NCCBR, foreign companies borrowed around $1.2T and lent around $1.3T. | "
        "The opaque bilateral segment is a major cross-border funding channel. |"
    )
    report.append(
        "| Banks, dealers, and hedge funds are typical cross-border repo participants; hedge funds are mostly cash borrowers. | "
        "This supports the leveraged Treasury-plumbing mechanism used in BTAR. |"
    )
    report.append(
        "| About 74% of cross-border repos are U.S.-dollar-denominated and typically backed by U.S. collateral. | "
        "The channel is directly relevant to dollar funding and Treasury collateral stress. |"
    )
    report.append("")
    report.append(
        "Interpretation: OFR validates the transmission channel, not UAE attribution. "
        "The evidence says the cross-border repo pipe is large and dollar-heavy; UAE-specific exposure still has to be inferred from CBUAE, BIS, TIC, FICC, and scenario analysis."
    )
    report.append("")
    report.append(
        "Source: OFR, 'Sizing the U.S. Cross-Border Repo Market,' published April 9, 2026: "
        "https://www.financialresearch.gov/the-ofr-blog/2026/04/09/sizing-the-us-cross-border-repo-market/"
    )
    report.append("")

    report.append("## Policy implication")
    report.append("")
    report.append(
        "The U.S. incentive to provide a swap or liquidity backstop is structural: "
        "it can be cheaper to liquefy a foreign dollar node than to allow disorderly selling through Treasury and repo markets. "
        "But this also reinforces the dollar system's Dutch-disease problem: global surplus keeps routing into U.S. financial assets, "
        "the U.S. backstops the plumbing in stress, and the financial sink grows larger relative to the tradable real economy."
    )
    report.append("")

    report.append("## Interpretation")
    report.append("")
    report.append("Phase 1 should not be read as proof that UAE was short of reserves.")
    report.append("")
    report.append("The stronger interpretation is that UAE may be reserve-rich while the immediately deployable cash/deposit layer is smaller than headline reserves imply.")
    report.append("")
    report.append("The unresolved research question is where the securities-like and externally routed dollar stock sits: TIC-visible Treasuries, TIC non-Treasury securities, BIS banking/custody channels, external managers, MMFs, hedge funds, sponsored repo, or FX derivatives.")
    report.append("")

    out = OUT_REPORTS / 'phase1_summary.md'
    out.write_text("\n".join(report))

    print(f"  Saved summary report: {out}")
    return out


# =============================================================================
# FIX 1: Robust BIS LBS puller
# =============================================================================
def pull_bis_lbs_uae_v2(force_refetch=False):
    """
    Exact-anchor BIS LBS pull for UAE counterparty rows.

    This function does not use fuzzy column matching.

    Required BIS flat-file anchors:
      - L_CP_COUNTRY:Counterparty country
      - L_REP_CTY:Reporting country
      - L_POSITION:Balance sheet position
      - L_INSTR:Type of instruments
      - L_DENOM:Currency denomination
      - TIME_PERIOD:Time period or range
      - OBS_VALUE:Observation Value
      - UNIT_MULT:Unit Multiplier

    Filter:
      - L_CP_COUNTRY:Counterparty country == 'AE'

    Output:
      - Keeps the original BIS columns.
      - Adds normalized helper columns for later Channel 2 and Channel 8 aggregation.
    """
    OUT_CSV.mkdir(parents=True, exist_ok=True)

    cache = OUT_CSV / 'bis_lbs_uae_filtered.csv'
    zip_cache = OUT_CSV / 'bis_lbs_bulk.zip'
    zip_cache_max_age_days = 7

    required_columns = [
        'L_CP_COUNTRY:Counterparty country',
        'L_REP_CTY:Reporting country',
        'L_POSITION:Balance sheet position',
        'L_INSTR:Type of instruments',
        'L_DENOM:Currency denomination',
        'TIME_PERIOD:Time period or range',
        'OBS_VALUE:Observation Value',
        'UNIT_MULT:Unit Multiplier',
    ]

    normalized_columns = [
        'date',
        'obs_value',
        'unit_mult',
        'value_usd_bn',
        'reporter_country',
        'counterparty_country',
        'position',
        'instrument',
        'denomination',
    ]

    if cache.exists() and not force_refetch:
        cached = pd.read_csv(cache, low_memory=False)

        if all(col in cached.columns for col in normalized_columns) and len(cached) > 0:
            cached['date'] = pd.to_datetime(cached['date'])
            print(f"  Using cached normalized BIS LBS: {cache}")
            return cached

        if all(col in cached.columns for col in normalized_columns) and len(cached) == 0:
            print(f"  Existing BIS LBS cache is normalized but empty; rebuilding: {cache}")
        else:
            print(f"  Existing BIS LBS cache is not normalized; rebuilding: {cache}")

    url = 'https://data.bis.org/static/bulk/WS_LBS_D_PUB_csv_flat.zip'

    use_cached_zip = False
    if zip_cache.exists() and not force_refetch:
        zip_age_seconds = pd.Timestamp.now().timestamp() - zip_cache.stat().st_mtime
        zip_age_days = zip_age_seconds / 86400
        if zip_age_days <= zip_cache_max_age_days:
            use_cached_zip = True
            print(f"  Using cached BIS LBS bulk ZIP: {zip_cache} ({zip_age_days:.1f} days old)")
        else:
            print(f"  Cached BIS LBS bulk ZIP is stale: {zip_cache} ({zip_age_days:.1f} days old)")

    if use_cached_zip:
        zip_bytes = io.BytesIO(zip_cache.read_bytes())
    else:
        print("  Downloading BIS LBS bulk ZIP...")
        try:
            r = requests.get(url, timeout=600, stream=True)
            r.raise_for_status()
        except Exception as e:
            raise RuntimeError(f"BIS LBS download failed: {e}")

        zip_cache.write_bytes(r.content)
        print(f"  Saved BIS LBS bulk ZIP cache: {zip_cache}")
        zip_bytes = io.BytesIO(r.content)

    with zipfile.ZipFile(zip_bytes) as z:
        csv_files = [n for n in z.namelist() if n.endswith('.csv')]

        if len(csv_files) != 1:
            raise RuntimeError(
                f"BIS LBS ZIP expected exactly 1 CSV file, found {len(csv_files)}: {csv_files}"
            )

        csv_name = csv_files[0]

        with z.open(csv_name) as f:
            header = pd.read_csv(f, nrows=0, low_memory=False)

        missing = [col for col in required_columns if col not in header.columns]

        if missing:
            sample_path = OUT_CSV / 'bis_lbs_sample.csv'
            with z.open(csv_name) as f:
                sample = pd.read_csv(f, nrows=100, low_memory=False)
            sample.to_csv(sample_path, index=False)

            raise RuntimeError(
                "BIS LBS exact required columns missing: "
                + ", ".join(missing)
                + f". Saved 100-row sample to {sample_path}"
            )

        print("  BIS LBS exact anchors verified.")

    def parse_bis_time_period(x):
        s = str(x).strip()

        if len(s) == 7 and s[4:6] == '-Q':
            year = int(s[:4])
            quarter = int(s[-1])
            month = quarter * 3
            return pd.Timestamp(year, month, 1) + pd.offsets.MonthEnd(0)

        if len(s) == 7 and s[4] == '-':
            return pd.to_datetime(s + '-01') + pd.offsets.MonthEnd(0)

        if len(s) == 4 and s.isdigit():
            return pd.Timestamp(int(s), 12, 31)

        return pd.to_datetime(s, errors='coerce')

    chunks = []
    zip_bytes = io.BytesIO(r.content)

    with zipfile.ZipFile(zip_bytes) as z:
        with z.open(csv_name) as f:
            for chunk in pd.read_csv(f, chunksize=500000, low_memory=False):

                cp_code = (
                    chunk['L_CP_COUNTRY:Counterparty country']
                    .astype(str)
                    .str.split(':', n=1)
                    .str[0]
                    .str.strip()
                )

                valid_obs = (
                    chunk['TIME_PERIOD:Time period or range'].notna()
                    & chunk['OBS_VALUE:Observation Value'].notna()
                )

                sub = chunk[cp_code.eq('AE') & valid_obs].copy()

                if len(sub) > 0:
                    chunks.append(sub)

    if not chunks:
        sample_path = OUT_CSV / 'bis_lbs_sample.csv'
        zip_bytes = io.BytesIO(r.content)

        with zipfile.ZipFile(zip_bytes) as z:
            with z.open(csv_name) as f:
                sample = pd.read_csv(f, nrows=100, low_memory=False)

        sample.to_csv(sample_path, index=False)

        raise RuntimeError(
            "BIS LBS exact filter found zero rows where the code prefix of "
            "'L_CP_COUNTRY:Counterparty country' == 'AE'. "
            f"Saved 100-row sample to {sample_path}"
        )

    df = pd.concat(chunks, ignore_index=True)

    df['date'] = df['TIME_PERIOD:Time period or range'].apply(parse_bis_time_period)
    df['obs_value'] = pd.to_numeric(df['OBS_VALUE:Observation Value'], errors='coerce')

    df['unit_mult'] = pd.to_numeric(
        df['UNIT_MULT:Unit Multiplier']
        .astype(str)
        .str.split(':', n=1)
        .str[0]
        .str.strip(),
        errors='coerce'
    )
    df['value_usd_bn'] = df['obs_value'] * (10 ** df['unit_mult']) / 1_000_000_000

    df['reporter_country'] = df['L_REP_CTY:Reporting country'].astype(str).str.strip()

    df['counterparty_country'] = df['L_CP_COUNTRY:Counterparty country'].astype(str).str.strip()
    df['counterparty_country_code'] = (
        df['L_CP_COUNTRY:Counterparty country']
        .astype(str)
        .str.split(':', n=1)
        .str[0]
        .str.strip()
    )


    df['position'] = df['L_POSITION:Balance sheet position'].astype(str).str.strip()
    df['instrument'] = df['L_INSTR:Type of instruments'].astype(str).str.strip()
    df['denomination'] = df['L_DENOM:Currency denomination'].astype(str).str.strip()

    print("  BIS UAE rows before final normalization drop:", len(df))
    print("  Non-null date:", df['date'].notna().sum())
    print("  Non-null obs_value:", df['obs_value'].notna().sum())
    print("  Non-null unit_mult:", df['unit_mult'].notna().sum())
    print("  Non-null value_usd_bn:", df['value_usd_bn'].notna().sum())

    df = df.dropna(subset=['date', 'obs_value', 'unit_mult', 'value_usd_bn'])

    df.to_csv(cache, index=False)

    print(f"  Saved {len(df)} normalized UAE BIS LBS records to {cache}")
    print("  BIS LBS normalized columns ready for Channel 2 and Channel 8 aggregation.")

    return df

# =============================================================================
# FIX 2: TIC MFH parser
# =============================================================================
def pull_tic_mfh_v2():
    """
    Parse TIC MFH current table into clean long format.

    The current MFH text file uses:
      line 8: month labels
      line 9: Country + year labels

    Outputs:
      - tic_mfh_monthly.csv: all parsed countries in long format
      - tic_mfh_uae.csv: UAE row in wide format
      - tic_mfh_uae_long.csv: UAE holdings in long format
    """
    import re

    url = 'https://ticdata.treasury.gov/Publish/mfh.txt'
    print(f"  Pulling TIC MFH from {url}...")

    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
    except Exception as e:
        print(f"  MFH fetch failed: {e}")
        return None

    text = r.text
    OUT_CSV.mkdir(parents=True, exist_ok=True)

    cache_raw = OUT_CSV / 'tic_mfh_raw.txt'
    cache_raw.write_text(text)

    lines = text.splitlines()

    month_line_idx = None
    year_line_idx = None

    for i, line in enumerate(lines):
        month_tokens_candidate = re.findall(
            r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b',
            line
        )

        if len(month_tokens_candidate) >= 12 and i + 1 < len(lines) and 'Country' in lines[i + 1]:
            month_line_idx = i
            year_line_idx = i + 1
            break

    if month_line_idx is None or year_line_idx is None:
        raise RuntimeError(
            "Could not locate TIC MFH month/year header lines in mfh.txt. "
            f"Raw file saved to {cache_raw}"
        )

    month_tokens = re.findall(
        r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b',
        lines[month_line_idx]
    )

    year_tokens = re.findall(r'\b\d{4}\b', lines[year_line_idx])

    if len(month_tokens) != len(year_tokens):
        raise RuntimeError(
            "TIC MFH month/year header length mismatch: "
            f"{len(month_tokens)} months vs {len(year_tokens)} years. "
            f"Raw file saved to {cache_raw}"
        )

    date_labels = []
    for month_name, year_text in zip(month_tokens, year_tokens):
        dt = pd.to_datetime(f"{year_text}-{month_name}-01") + pd.offsets.MonthEnd(0)
        date_labels.append(dt)

    parsed_rows = []

    country_line_pattern = re.compile(
        r'^(?P<country>[A-Za-z][A-Za-z0-9\s\.\,\-\&\(\)\/]+?)\s+'
        r'(?P<values>-?\d+(?:\.\d+)?(?:\s+-?\d+(?:\.\d+)?){12})\s*$'
    )

    for line in lines[year_line_idx + 1:]:
        s = line.strip()

        if not s:
            continue

        if s.startswith('------'):
            continue

        if s in ['Of which:', 'Department of the Treasury/Federal Reserve Board']:
            break

        m = country_line_pattern.match(s)

        if not m:
            continue

        country = m.group('country').strip()
        values = [float(x) for x in m.group('values').split()]

        if len(values) != len(date_labels):
            continue

        for dt, value in zip(date_labels, values):
            parsed_rows.append({
                'date': dt,
                'country': country,
                'value_usd_bn': value,
                'source': 'TIC MFH current table'
            })

    if not parsed_rows:
        raise RuntimeError(
            "TIC MFH parser produced zero rows. "
            f"Raw file saved to {cache_raw}"
        )

    df_long = pd.DataFrame(parsed_rows)
    df_long = df_long.sort_values(['country', 'date']).reset_index(drop=True)

    out_long = OUT_CSV / 'tic_mfh_monthly.csv'
    df_long.to_csv(out_long, index=False)
    print(f"  Saved TIC MFH long table to {out_long} with shape {df_long.shape}")

    uae_long = df_long[
        df_long['country'].astype(str).str.fullmatch('United Arab Emirates', case=False, na=False)
    ].copy()

    if len(uae_long) == 0:
        raise RuntimeError(
            "TIC MFH parser did not find United Arab Emirates row. "
            f"Parsed long table saved to {out_long}"
        )

    uae_long = uae_long.sort_values('date').reset_index(drop=True)

    out_uae_long = OUT_CSV / 'tic_mfh_uae_long.csv'
    uae_long.to_csv(out_uae_long, index=False)

    uae_wide = uae_long.pivot_table(
        index='country',
        columns='date',
        values='value_usd_bn',
        aggfunc='first'
    ).reset_index()

    out_uae = OUT_CSV / 'tic_mfh_uae.csv'
    uae_wide.to_csv(out_uae, index=False)

    print(f"  Saved UAE TIC MFH long row to {out_uae_long}")
    print(uae_long.to_string(index=False))

    return df_long

def load_cbuae_reserve_composition():
    """
    Load CBUAE reserve-composition table from the February 2026 statistical bulletin.

    Source file:
      outputs/csv/cbuae_statistical_bulletin_february_2026.xlsx

    Sheet:
      '6 CB Intnl Res'

    Units in source:
      AED millions

    Output units:
      USD billions, using AED/USD peg 3.6725
    """
    cbuae_path = OUT_CSV / 'cbuae_statistical_bulletin_february_2026.xlsx'

    if not cbuae_path.exists():
        url = 'https://www.centralbank.ae/media/54ag1oqv/statistical-bulletin-february-2026.xlsx'
        print(f"  Downloading CBUAE bulletin from {url}...")
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        cbuae_path.write_bytes(r.content)
        print(f"  Saved CBUAE bulletin to {cbuae_path}")

    df = pd.read_excel(cbuae_path, sheet_name='6 CB Intnl Res', header=None)

    date_row = df.iloc[4]
    date_cells = date_row.iloc[3:16].tolist()

    dates = []
    for x in date_cells:
        s = str(x).strip()
        s = s.replace('*', '').strip()

        if not s:
            dates.append(pd.NaT)
            continue

        dates.append(pd.to_datetime(s, errors='coerce') + pd.offsets.MonthEnd(0))

    row_map = {
        'gross_reserves_bn': 5,
        'cash_deposits_abroad_bn': 6,
        'foreign_investments_bn': 7,
        'imf_sdr_bn': 8,
        'other_foreign_assets_bn': 9,
        'foreign_liabilities_bn': 10,
        'net_international_reserves_bn': 11,
    }

    out = pd.DataFrame({'date': dates})

    AED_PER_USD = 3.6725

    for col_name, row_idx in row_map.items():
        values_aed_mn = pd.to_numeric(df.iloc[row_idx, 3:16], errors='coerce')
        out[col_name] = values_aed_mn.values / AED_PER_USD / 1000

    out = out.dropna(subset=['date']).sort_values('date').reset_index(drop=True)

    out['cash_deposits_share_of_gross_reserves'] = (
        out['cash_deposits_abroad_bn'] / out['gross_reserves_bn']
    )

    out['foreign_investments_share_of_gross_reserves'] = (
        out['foreign_investments_bn'] / out['gross_reserves_bn']
    )

    out['source'] = 'CBUAE Statistical Bulletin February 2026, Table 6 Central Bank International Reserves'

    out_path = OUT_CSV / 'cbuae_reserve_composition.csv'
    out.to_csv(out_path, index=False)

    print(f"  Saved CBUAE reserve composition to {out_path}")
    print(out.tail(6).to_string(index=False))

    return out



# =============================================================================
# FIX 3: TIC SHL with year fallback
# =============================================================================

def pull_tic_shl_v2(preferred_year=2024):
    """Try multiple years and URL patterns for TIC SHL annual."""
    base = 'https://ticdata.treasury.gov/Publish'
    candidates = [
        f'{base}/shl{preferred_year}r.xls',
        f'{base}/shl{preferred_year}_final.xls',
        f'{base}/shla{preferred_year}r.xls',
        f'{base}/shl{preferred_year-1}r.xls',
        f'{base}/shla{preferred_year-1}r.xls',
        f'{base}/shl{preferred_year-2}r.xls',
        f'{base}/shla{preferred_year-2}r.xls',
    ]
    for url in candidates:
        try:
            r = requests.get(url, timeout=60)
            if r.status_code == 200 and len(r.content) > 10000:
                # Store and return
                yr = url.split('shl')[-1].split('r.xls')[0].replace('a', '').replace('_final', '')
                cache = OUT_CSV / f'tic_shl_{yr}.xls'
                cache.write_bytes(r.content)
                print(f"  Got TIC SHL from {url}")
                try:
                    sheets = pd.read_excel(cache, sheet_name=None, engine='xlrd', header=None)
                except Exception:
                    try:
                        sheets = pd.read_excel(cache, sheet_name=None, engine='openpyxl', header=None)
                    except Exception as e:
                        print(f"  Could not parse: {e}")
                        return None
                return sheets
        except Exception:
            continue
    print(f"  TIC SHL: no file found for recent years. Treasury may not have released.")
    return None

def pull_tic_shc_v2(preferred_year=2024):
    base = 'https://ticdata.treasury.gov/Publish'
    candidates = [
        f'{base}/shc{preferred_year}r.xls',
        f'{base}/shc{preferred_year}_final.xls',
        f'{base}/shc{preferred_year-1}r.xls',
        f'{base}/shc{preferred_year-2}r.xls',
    ]
    for url in candidates:
        try:
            r = requests.get(url, timeout=60)
            if r.status_code == 200 and len(r.content) > 10000:
                yr = url.split('shc')[-1].split('r.xls')[0].replace('_final', '')
                cache = OUT_CSV / f'tic_shc_{yr}.xls'
                cache.write_bytes(r.content)
                print(f"  Got TIC SHC from {url}")
                try:
                    sheets = pd.read_excel(cache, sheet_name=None, engine='xlrd', header=None)
                except Exception:
                    sheets = pd.read_excel(cache, sheet_name=None, engine='openpyxl', header=None)
                return sheets
        except Exception:
            continue
    print(f"  TIC SHC: no file found for recent years.")
    return None


# =============================================================================
# FIX 4: Primary dealer Excel with explicit engine
# =============================================================================

def pull_primary_dealer_v2():
    url = 'https://www.newyorkfed.org/medialibrary/media/markets/pdpos.xlsx'
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
    except Exception as e:
        print(f"  PD pull failed: {e}")
        return None
    cache = OUT_CSV / 'ny_fed_primary_dealer_positions.xlsx'
    cache.write_bytes(r.content)
    # Try both engines
    for engine in ['openpyxl', 'xlrd']:
        try:
            sheets = pd.read_excel(cache, sheet_name=None, engine=engine)
            print(f"  Parsed primary dealer with engine={engine}, {len(sheets)} sheets")
            return sheets
        except Exception as e:
            continue
    print(f"  Could not parse primary dealer file. It may be an older .xls served as .xlsx.")
    return None


# =============================================================================
# FIX 5: Rewrite build_channel_frame to fix the length mismatch bug
# =============================================================================

def build_channel_frame_v2(uae_master, te_us, bis_lbs, tic_mfh):
    """Corrected: ensure all DataFrame constructor lists have equal length."""
    channels = {}


    # Channel 1: TIC Direct Treasury holdings
    #
    # Primary source: parsed TIC MFH UAE long-format table from pull_tic_mfh_v2().
    # Supplemental points preserve later observations already used in the project
    # when the currently downloaded MFH file only contains an older 13-month window.
    ch1_parts = []

    tic_uae_long_path = OUT_CSV / 'tic_mfh_uae_long.csv'

    if tic_uae_long_path.exists():
        tic_uae_long = pd.read_csv(tic_uae_long_path)
        required_tic_cols = ['date', 'value_usd_bn']

        missing_tic_cols = [col for col in required_tic_cols if col not in tic_uae_long.columns]

        if missing_tic_cols:
            raise RuntimeError(
                "Cannot build Channel 1 from TIC MFH long file because columns are missing: "
                + ", ".join(missing_tic_cols)
            )

        tic_uae_long = tic_uae_long[['date', 'value_usd_bn']].copy()
        tic_uae_long['date'] = pd.to_datetime(tic_uae_long['date'])
        tic_uae_long['value_usd_bn'] = pd.to_numeric(tic_uae_long['value_usd_bn'], errors='coerce')
        tic_uae_long = tic_uae_long.dropna(subset=['date', 'value_usd_bn'])
        tic_uae_long['source'] = 'TIC MFH parsed UAE row'

        if len(tic_uae_long) > 0:
            ch1_parts.append(tic_uae_long)

    ch1_reference = pd.DataFrame({
        'date': pd.to_datetime([
            '2023-12-31',
            '2024-06-30',
            '2024-12-31',
            '2025-06-30',
            '2025-12-31',
        ]),
        'value_usd_bn': [
            64.9,
            78.0,
            88.5,
            92.0,
            95.6,
        ],
        'source': [
            'Supplemental TIC MFH UAE Treasury reference point',
            'Supplemental TIC MFH UAE Treasury reference point',
            'Supplemental TIC MFH UAE Treasury reference point',
            'Supplemental TIC MFH UAE Treasury reference point',
            'Supplemental TIC MFH UAE Treasury reference point',
        ],
    })

    ch1_parts.append(ch1_reference)

    ch1 = pd.concat(ch1_parts, ignore_index=True)
    ch1 = ch1.sort_values(['date', 'source']).drop_duplicates(subset=['date'], keep='first')
    ch1 = ch1.sort_values('date').reset_index(drop=True)

    channels['Channel_1_TIC_Direct'] = ch1


    # Channel 2: BIS LBS cross-border bank/custody channel
    ch2 = pd.DataFrame(columns=[
        'date',
        'reporter_country_code',
        'reporter_country',
        'position',
        'instrument',
        'denomination',
        'value_usd_bn',
        'source'
    ])

    if bis_lbs is not None and len(bis_lbs) > 0:
        required_bis_cols = [
            'date',
            'value_usd_bn',
            'reporter_country',
            'position',
            'instrument',
            'denomination',
        ]

        missing_bis_cols = [col for col in required_bis_cols if col not in bis_lbs.columns]

        if missing_bis_cols:
            raise RuntimeError(
                "Cannot populate Channel 2 because normalized BIS LBS columns are missing: "
                + ", ".join(missing_bis_cols)
            )

        tmp = bis_lbs[required_bis_cols].copy()
        tmp['date'] = pd.to_datetime(tmp['date'])
        tmp['value_usd_bn'] = pd.to_numeric(tmp['value_usd_bn'], errors='coerce')

        tmp['reporter_country'] = tmp['reporter_country'].astype(str).str.strip()
        tmp['reporter_country_code'] = (
            tmp['reporter_country']
            .str.split(':', n=1)
            .str[0]
            .str.strip()
        )

        tmp['position'] = tmp['position'].astype(str).str.strip()
        tmp['instrument'] = tmp['instrument'].astype(str).str.strip()
        tmp['denomination'] = tmp['denomination'].astype(str).str.strip()

        tmp = tmp.dropna(subset=['date', 'value_usd_bn'])

        if len(tmp) > 0:
            ch2 = (
                tmp.groupby(
                    [
                        'date',
                        'reporter_country_code',
                        'reporter_country',
                        'position',
                        'instrument',
                        'denomination',
                    ],
                    as_index=False
                )['value_usd_bn']
                .sum()
                .sort_values(
                    [
                        'date',
                        'reporter_country_code',
                        'position',
                        'instrument',
                        'denomination',
                    ]
                )
            )

            ch2['source'] = 'BIS LBS exact UAE counterparty rows aggregated by reporter, position, instrument, denomination'

            ch2_global_usd_claims = ch2[
                ch2['reporter_country_code'].eq('5A')
                & ch2['position'].eq('C: Total claims')
                & ch2['instrument'].eq('A: All instruments')
                & ch2['denomination'].eq('USD: US dollar')
            ].copy()

            ch2_global_usd_claims = (
                ch2_global_usd_claims[
                    ['date', 'value_usd_bn']
                ]
                .sort_values('date')
                .reset_index(drop=True)
            )
            ch2_global_usd_claims['source'] = (
                'BIS LBS: all reporting countries, USD total claims on UAE, all instruments'
            )
            ch2_global_usd_claims.to_csv(
                OUT_CSV / 'channel_Channel_2_BIS_global_usd_claims.csv',
                index=False
            )

            ch2_global_usd_liabilities = ch2[
                ch2['reporter_country_code'].eq('5A')
                & ch2['position'].eq('L: Total liabilities')
                & ch2['instrument'].eq('A: All instruments')
                & ch2['denomination'].eq('USD: US dollar')
            ].copy()

            ch2_global_usd_liabilities = (
                ch2_global_usd_liabilities[
                    ['date', 'value_usd_bn']
                ]
                .sort_values('date')
                .reset_index(drop=True)
            )
            ch2_global_usd_liabilities['source'] = (
                'BIS LBS: all reporting countries, USD total liabilities to UAE, all instruments'
            )
            ch2_global_usd_liabilities.to_csv(
                OUT_CSV / 'channel_Channel_2_BIS_global_usd_liabilities.csv',
                index=False
            )

            ch2_reporter_usd_deposit_liabilities = ch2[
                ~ch2['reporter_country_code'].eq('5A')
                & ch2['position'].eq('L: Total liabilities')
                & ch2['instrument'].eq('G: Loans and deposits')
                & ch2['denomination'].eq('USD: US dollar')
            ].copy()

            ch2_reporter_usd_deposit_liabilities = (
                ch2_reporter_usd_deposit_liabilities[
                    [
                        'date',
                        'reporter_country_code',
                        'reporter_country',
                        'value_usd_bn',
                    ]
                ]
                .sort_values(['date', 'reporter_country_code'])
                .reset_index(drop=True)
            )
            ch2_reporter_usd_deposit_liabilities['source'] = (
                'BIS LBS: reporter-country USD loans/deposits liabilities to UAE'
            )
            ch2_reporter_usd_deposit_liabilities.to_csv(
                OUT_CSV / 'channel_Channel_2_BIS_reporter_usd_deposit_liabilities.csv',
                index=False
            )

            ch2_reporter_all_currency_deposit_claims = ch2[
                ~ch2['reporter_country_code'].eq('5A')
                & ch2['position'].eq('C: Total claims')
                & ch2['instrument'].eq('G: Loans and deposits')
                & ch2['denomination'].eq('TO1: All currencies')
            ].copy()

            ch2_reporter_all_currency_deposit_claims = (
                ch2_reporter_all_currency_deposit_claims[
                    [
                        'date',
                        'reporter_country_code',
                        'reporter_country',
                        'value_usd_bn',
                    ]
                ]
                .sort_values(['date', 'reporter_country_code'])
                .reset_index(drop=True)
            )
            ch2_reporter_all_currency_deposit_claims['source'] = (
                'BIS LBS: reporter-country all-currency loans/deposits claims on UAE'
            )
            ch2_reporter_all_currency_deposit_claims.to_csv(
                OUT_CSV / 'channel_Channel_2_BIS_reporter_all_currency_deposit_claims.csv',
                index=False
            )

            ch2_reporter_all_currency_deposit_liabilities = ch2[
                ~ch2['reporter_country_code'].eq('5A')
                & ch2['position'].eq('L: Total liabilities')
                & ch2['instrument'].eq('G: Loans and deposits')
                & ch2['denomination'].eq('TO1: All currencies')
            ].copy()

            ch2_reporter_all_currency_deposit_liabilities = (
                ch2_reporter_all_currency_deposit_liabilities[
                    [
                        'date',
                        'reporter_country_code',
                        'reporter_country',
                        'value_usd_bn',
                    ]
                ]
                .sort_values(['date', 'reporter_country_code'])
                .reset_index(drop=True)
            )
            ch2_reporter_all_currency_deposit_liabilities['source'] = (
                'BIS LBS: reporter-country all-currency loans/deposits liabilities to UAE'
            )
            ch2_reporter_all_currency_deposit_liabilities.to_csv(
                OUT_CSV / 'channel_Channel_2_BIS_reporter_all_currency_deposit_liabilities.csv',
                index=False
            )

            print(
                "  Channel 2 BIS filtered summaries saved: "
                f"global_usd_claims={len(ch2_global_usd_claims)}, "
                f"global_usd_liabilities={len(ch2_global_usd_liabilities)}, "
                f"reporter_usd_deposit_liabilities={len(ch2_reporter_usd_deposit_liabilities)}, "
                f"reporter_all_currency_deposit_claims={len(ch2_reporter_all_currency_deposit_claims)}, "
                f"reporter_all_currency_deposit_liabilities={len(ch2_reporter_all_currency_deposit_liabilities)}"
            )

            # BIS-implied reporter USD allocation.
            #
            # BIS gives two complementary views:
            #   1. 5A aggregate rows provide USD liabilities to UAE.
            #   2. Reporter-country rows provide all-currency loans/deposits liabilities to UAE.
            #
            # This allocation estimates reporter-country USD liabilities by applying
            # reporter all-currency liability shares to the 5A global USD liability total.
            # It is an estimate, not a directly reported reporter-country USD series.

            usd_total = ch2_global_usd_liabilities[['date', 'value_usd_bn']].copy()
            usd_total = usd_total.rename(columns={'value_usd_bn': 'global_usd_liabilities_bn'})
            usd_total['date'] = pd.to_datetime(usd_total['date'])

            reporter_liab = ch2_reporter_all_currency_deposit_liabilities[
                [
                    'date',
                    'reporter_country_code',
                    'reporter_country',
                    'value_usd_bn',
                ]
            ].copy()
            reporter_liab = reporter_liab.rename(
                columns={'value_usd_bn': 'reporter_all_currency_deposit_liabilities_bn'}
            )
            reporter_liab['date'] = pd.to_datetime(reporter_liab['date'])

            reporter_total = (
                reporter_liab
                .groupby('date', as_index=False)['reporter_all_currency_deposit_liabilities_bn']
                .sum()
                .rename(columns={
                    'reporter_all_currency_deposit_liabilities_bn': 'reporter_all_currency_total_bn'
                })
            )

            implied = reporter_liab.merge(reporter_total, on='date', how='left')
            implied = implied.merge(usd_total, on='date', how='left')

            implied['reporter_share_of_all_currency_liabilities'] = (
                implied['reporter_all_currency_deposit_liabilities_bn']
                / implied['reporter_all_currency_total_bn']
            )

            implied['implied_reporter_usd_deposit_liabilities_bn'] = (
                implied['reporter_share_of_all_currency_liabilities']
                * implied['global_usd_liabilities_bn']
            )

            implied = implied.dropna(subset=[
                'reporter_share_of_all_currency_liabilities',
                'global_usd_liabilities_bn',
                'implied_reporter_usd_deposit_liabilities_bn',
            ])

            implied['source'] = (
                'BIS-implied reporter USD allocation: '
                'global 5A USD liabilities to UAE allocated by reporter all-currency '
                'loans/deposits liability shares'
            )

            implied = implied.sort_values([
                'date',
                'implied_reporter_usd_deposit_liabilities_bn',
            ], ascending=[True, False])

            implied.to_csv(
                OUT_CSV / 'channel_Channel_2_BIS_implied_reporter_usd_deposit_liabilities.csv',
                index=False
            )

            implied_top_latest = implied.sort_values('date').groupby('date').tail(20)
            implied_top_latest.to_csv(
                OUT_CSV / 'channel_Channel_2_BIS_implied_reporter_usd_deposit_liabilities_top20_by_date.csv',
                index=False
            )

            print(
                "  Channel 2 BIS implied reporter USD allocation saved: "
                f"rows={len(implied)}"
            )


    channels['Channel_2_NonUS_Custody'] = ch2

    # Channel 3: Agency/Corp via US custodians (from TIC SHL — TBD)
    channels['Channel_3_Agency_Corp'] = pd.DataFrame({
        'date': [pd.Timestamp('2024-12-31')],
        'value_usd_bn': [np.nan],
        'source': ['TIC SHL UAE non-Treasury holdings (pending)'],
    })

    # Channel 4: MMF shares
    channels['Channel_4_MMF'] = pd.DataFrame({
        'date': [pd.Timestamp('2025-12-31')],
        'value_usd_bn': [np.nan],
        'source': ['MMF holdings by UAE domicile — not publicly observable'],
    })

    # Channel 5: Hedge fund LP positions
    channels['Channel_5_HedgeFund_LP'] = pd.DataFrame({
        'date': [pd.Timestamp('2024-01-01'), pd.Timestamp('2025-12-31')],
        'value_usd_bn': [np.nan, np.nan],
        'source': ['Lunate minority stake in Brevan Howard (2024)',
                   'Other LP positions in basis-trade funds not disclosed'],
    })

    # Channel 6: FICC Sponsored — FIXED: length 2 for each column
    channels['Channel_6_FICC_Sponsored'] = pd.DataFrame({
        'date': [pd.Timestamp('2025-02-10'), pd.Timestamp('2026-03-30')],
        'value_usd_bn': [np.nan, np.nan],
        'source': ['Sponsored Member list moved behind MyDTCC login',
                   'UAE on Approved FICC Jurisdictions list (effective Mar 30 2026)'],
    })

    # Channel 7: External managers
    channels['Channel_7_External_Managers'] = pd.DataFrame({
        'date': [pd.Timestamp('2025-12-31')],
        'value_usd_bn': [np.nan],
        'source': ['ADIA/Mubadala/ADQ external manager allocations (~$1T estimated)'],
    })

    # Channel 8: CBUAE cash/deposit-like reserve liquidity
    #
    # Source:
    #   CBUAE Statistical Bulletin February 2026,
    #   Table 6: Central Bank International Reserves
    #
    # This is the cash/deposit-like reserve layer:
    #   Current Account Balances & Deposits with Banks Abroad
    cbuae_reserve_path = OUT_CSV / 'cbuae_reserve_composition.csv'

    if cbuae_reserve_path.exists():
        cbuae_reserves = pd.read_csv(cbuae_reserve_path)

        required_cbuae_cols = [
            'date',
            'cash_deposits_abroad_bn',
            'gross_reserves_bn',
            'foreign_investments_bn',
        ]

        missing_cbuae_cols = [
            col for col in required_cbuae_cols
            if col not in cbuae_reserves.columns
        ]

        if missing_cbuae_cols:
            raise RuntimeError(
                "Cannot build Channel 8 from CBUAE reserve composition because columns are missing: "
                + ", ".join(missing_cbuae_cols)
            )

        ch8 = cbuae_reserves[
            [
                'date',
                'cash_deposits_abroad_bn',
                'gross_reserves_bn',
                'foreign_investments_bn',
            ]
        ].copy()

        ch8['date'] = pd.to_datetime(ch8['date'])
        ch8['value_usd_bn'] = pd.to_numeric(
            ch8['cash_deposits_abroad_bn'],
            errors='coerce'
        )

        ch8['gross_reserves_bn'] = pd.to_numeric(
            ch8['gross_reserves_bn'],
            errors='coerce'
        )

        ch8['foreign_investments_bn'] = pd.to_numeric(
            ch8['foreign_investments_bn'],
            errors='coerce'
        )

        ch8 = ch8.dropna(subset=['date', 'value_usd_bn'])
        ch8 = ch8.sort_values('date').reset_index(drop=True)

        ch8['source'] = (
            'CBUAE Statistical Bulletin February 2026 Table 6: '
            'Current Account Balances & Deposits with Banks Abroad'
        )

        channels['Channel_8_Deposits'] = ch8[
            [
                'date',
                'value_usd_bn',
                'gross_reserves_bn',
                'foreign_investments_bn',
                'source',
            ]
        ].copy()

    else:
        raise RuntimeError(
            "Cannot build Channel 8 because CBUAE reserve-composition file is missing: "
            + str(cbuae_reserve_path)
            + ". Run load_cbuae_reserve_composition() before build_channel_frame_v2()."
        )

    # Channel 9: FX derivatives
    channels['Channel_9_FX_Derivatives'] = pd.DataFrame({
        'date': [pd.Timestamp('2025-06-30')],
        'value_usd_bn': [np.nan],
        'source': ['BIS OTC derivatives aggregate + inference from UAE dollar-debt stock'],
    })

    return channels
# =============================================================================
# RESUME PHASE 1 from step 4 using the fixed functions
# =============================================================================

def resume_phase1():
    """Resume Phase 1 from Step 4 using the corrected functions."""
    # You already have uae_master and te_us in memory from the first cell.
    # If Colab kernel was not reset, just re-use them. Otherwise re-load.

    print("Mounting Google Drive and verifying Phase 1 input files...")

    try:
        from google.colab import drive
        drive.mount('/content/drive', force_remount=True)
    except ModuleNotFoundError:
        print("  google.colab not available; assuming local filesystem is already mounted.")
    except Exception as e:
        raise RuntimeError(f"Google Drive mount failed: {e}")

    for d in [OUT_DIR, OUT_CSV, OUT_PLOTS, OUT_REPORTS]:
        d.mkdir(parents=True, exist_ok=True)

    expected_files = [
        DATA_DIR / 'uae_master.csv',
        DATA_DIR / 'all_countries_all_series.csv',
        DATA_DIR / 'Mem-GOV-by-name.xlsx',
        DATA_DIR / 'FICC-GSD-Member-Directory-CCIT.xlsx',
    ]

    missing_files = [p for p in expected_files if not p.exists()]

    if missing_files:
        base_listing = []
        data_listing = []

        if BASE.exists():
            base_listing = sorted([p.name for p in BASE.iterdir()])

        if DATA_DIR.exists():
            data_listing = sorted([p.name for p in DATA_DIR.iterdir()])

        raise FileNotFoundError(
            "Required Phase 1 input files are missing from DATA_DIR.\n"
            f"BASE = {BASE}\n"
            f"DATA_DIR = {DATA_DIR}\n"
            "Missing files:\n"
            + "\n".join(str(p) for p in missing_files)
            + "\n\nVisible files in BASE:\n"
            + "\n".join(base_listing)
            + "\n\nVisible files in DATA_DIR:\n"
            + "\n".join(data_listing)
        )

    print("  Phase 1 input files verified:")
    for p in expected_files:
        print(f"    {p}")

    print("Re-loading data (in case kernel state changed)...")
    uae_master = pd.read_csv(DATA_DIR / 'uae_master.csv')
    uae_master['date'] = pd.to_datetime(
        uae_master['year'].astype(str) + '-' + uae_master['month'].astype(str).str.zfill(2) + '-01')
    te_us = pd.read_csv(DATA_DIR / 'all_countries_all_series.csv', low_memory=False)
    te_us['DateTime'] = pd.to_datetime(te_us['DateTime'])

    # Re-attempt the failed pulls with fixes
    print("\nRe-attempting BIS LBS with robust parser...")
    bis_lbs = pull_bis_lbs_uae_v2()
    print("\nRe-attempting TIC MFH...")
    tic_mfh = pull_tic_mfh_v2()

    print("\nRe-attempting TIC SHL...")
    tic_shl = pull_tic_shl_v2()

    print("\nRe-attempting TIC SHC...")
    tic_shc = pull_tic_shc_v2()

    print("\nRe-attempting primary dealer positions...")
    pd_pos = pull_primary_dealer_v2()

    print("\nLoading CBUAE reserve composition...")
    cbuae_reserves = load_cbuae_reserve_composition()

    print("\nBuilding channel frames (fixed)...")
    channels = build_channel_frame_v2(uae_master, te_us, bis_lbs, tic_mfh)

    # Save all channel CSVs
    for name, df in channels.items():
        df.to_csv(OUT_CSV / f'channel_{name}.csv', index=False)
    print(f"Saved channel CSVs to {OUT_CSV}")

    # Now proceed with the rest of Phase 1.
    # In Colab, these functions already live in notebook memory if the original
    # Phase 1 cell was run. Do NOT import uae_swap_line_analysis as a module.
    required_funcs = [
        'extract_stress_signals', 'ficc_analysis', 'load_ficc_gsd', 'load_ficc_ccit',
        'compute_uae_reserve_residual', 'plot_uae_portfolio_breakout',
        'plot_fed_bs_pivot', 'plot_sofr_effr_spread', 'plot_custodial_reshuffle',
        'plot_uae_reserves_buildup', 'plot_residual_gap', 'write_summary_report',
    ]

    missing = [name for name in required_funcs if name not in globals()]
    if missing:
        raise RuntimeError(
            "Missing original Phase 1 functions in notebook memory: "
            + ", ".join(missing)
            + "\nRe-run the original Phase 1 cell first, then run this patch cell."
        )

    extract_stress_signals = globals()['extract_stress_signals']
    ficc_analysis = globals()['ficc_analysis']
    load_ficc_gsd = globals()['load_ficc_gsd']
    load_ficc_ccit = globals()['load_ficc_ccit']
    compute_uae_reserve_residual = globals()['compute_uae_reserve_residual']
    plot_uae_portfolio_breakout = globals()['plot_uae_portfolio_breakout']
    plot_fed_bs_pivot = globals()['plot_fed_bs_pivot']
    plot_sofr_effr_spread = globals()['plot_sofr_effr_spread']
    plot_custodial_reshuffle = globals()['plot_custodial_reshuffle']
    plot_uae_reserves_buildup = globals()['plot_uae_reserves_buildup']
    plot_residual_gap = globals()['plot_residual_gap']
    write_summary_report = globals()['write_summary_report']

    print("\nExtracting stress signals...")
    sigs = extract_stress_signals(te_us)

    print("\nFICC analysis...")
    gsd = load_ficc_gsd()
    ccit = load_ficc_ccit()
    ficc_out = ficc_analysis(gsd, ccit)

    print("\nComputing residual gap...")
    residual_df = compute_uae_reserve_residual(uae_master, channels)
    residual_df.to_csv(OUT_CSV / 'uae_residual_gap.csv', index=False)

    print("\nGenerating plots...")
    plot_uae_portfolio_breakout(uae_master)
    plot_fed_bs_pivot(sigs)
    plot_sofr_effr_spread(sigs)
    plot_custodial_reshuffle(sigs)
    plot_uae_reserves_buildup(uae_master)
    plot_residual_gap(residual_df)

    print("\nComputing UAE-BTAR scenarios...")
    btar_df = compute_uae_btar_scenarios(residual_df, channels, sigs)

    print("\nComputing UAE import-liquidity CLC...")
    clc_import_df = compute_uae_import_liquidity_clc(uae_master)

    print("\nWriting summary report...")

    write_summary_report(channels, sigs, ficc_out, residual_df, uae_master)

    print("\n" + "=" * 70)
    print("PHASE 1 RESUMED AND COMPLETED")
    print("=" * 70)
    return channels, sigs, ficc_out, residual_df
# =============================================================================
# UAE Swap Line Analysis — Phase 2: Pre-Event Break Identification
# =============================================================================
#
# Goal: Identify when UAE dollar balance sheet stress started developing,
# working backwards from the April 22, 2026 Bessent swap line signal.
#
# Philosophy: This is NOT an event study. We want to find the pre-event
# conditions that made the swap line necessary. All data is cut at
# April 20, 2026 to avoid post-signal contamination.
#
# Five analyses:
#   1. Structural break tests (ruptures / Bai-Perron style) on key series
#   2. Rolling anomaly detection (z-score outliers)
#   3. Lead-lag cross-correlation (UAE flows vs US custodial stocks)
#   4. VAR + Granger + IRF (diagnostic — we decide if useful based on output)
#   5. Unified timeline chart — dated breaks across all series
#
# Run this AFTER Phase 1 has produced its outputs.
# =============================================================================

import os
import json
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

warnings.filterwarnings('ignore')

# =============================================================================
# CONFIG
# =============================================================================

BASE = Path('/content/drive/MyDrive/StockElephant/uae_swap_line_analysis')
DATA_DIR = BASE / 'data'
OUT_DIR = BASE / 'outputs'
OUT_CSV = OUT_DIR / 'csv'
OUT_PLOTS = OUT_DIR / 'plots'
OUT_REPORTS = OUT_DIR / 'reports'
STATS_DIR = OUT_DIR / 'stats'
STATS_DIR.mkdir(parents=True, exist_ok=True)

# Hard data cutoff to avoid post-signal contamination
DATA_CUTOFF = pd.Timestamp('2026-04-20')

# Policy event anchors (for visual reference only, NOT used for windowing)
BESSENT_DATE = pd.Timestamp('2026-04-22')
FED_PIVOT = pd.Timestamp('2026-01-21')
FICC_SPONSORED_DARK = pd.Timestamp('2025-02-10')
SOFR_SPIKE = pd.Timestamp('2026-03-16')
PART4_PUBLISHED = pd.Timestamp('2026-04-13')

plt.style.use('seaborn-v0_8-whitegrid')
plt.rcParams['figure.dpi'] = 110
plt.rcParams['savefig.dpi'] = 150
plt.rcParams['font.size'] = 10


# =============================================================================
# UTILITIES
# =============================================================================

def mount_drive():
    try:
        from google.colab import drive
        drive.mount('/content/drive')
    except ImportError:
        pass


def ensure_packages():
    """Install required packages."""
    import subprocess
    for pkg in ['ruptures']:
        try:
            __import__(pkg)
        except ImportError:
            print(f"Installing {pkg}...")
            subprocess.check_call(['pip', 'install', '-q', pkg])

def load_master():
    df = pd.read_csv(DATA_DIR / 'uae_master.csv')
    df['date'] = pd.to_datetime(df['year'].astype(str) + '-'
                                + df['month'].astype(str).str.zfill(2) + '-01')
    df = df[df['date'] <= DATA_CUTOFF].copy()
    return df


def load_te_us():
    df = pd.read_csv(DATA_DIR / 'all_countries_all_series.csv', low_memory=False)
    df['DateTime'] = pd.to_datetime(df['DateTime'])
    df = df[df['DateTime'] <= DATA_CUTOFF].copy()
    return df

def load_phase1_outputs():
    """
    Load fixed Phase 1 outputs for Phase 2 timeline reconciliation.

    Phase 2 should not rely only on legacy CEIC FX/M2 and TIC custody proxies.
    These Phase 1 outputs contain the actual reserve-composition, CLC, BIS routing,
    and BTAR stress objects.
    """
    outputs = {}

    phase1_files = {
        'cbuae_reserve_composition': OUT_CSV / 'cbuae_reserve_composition.csv',
        'uae_import_liquidity_clc': OUT_CSV / 'uae_import_liquidity_clc.csv',
        'uae_btar_scenarios': OUT_CSV / 'uae_btar_scenarios.csv',
        'uae_btar_buckets': OUT_CSV / 'uae_btar_buckets.csv',
        'bis_global_usd_liabilities': OUT_CSV / 'channel_Channel_2_BIS_global_usd_liabilities.csv',
        'bis_implied_reporter_usd': OUT_CSV / 'channel_Channel_2_BIS_implied_reporter_usd_deposit_liabilities.csv',
        'channel_1_tic_direct': OUT_CSV / 'channel_Channel_1_TIC_Direct.csv',
        'uae_residual_gap': OUT_CSV / 'uae_residual_gap.csv',
    }

    for name, path in phase1_files.items():
        if path.exists():
            df = pd.read_csv(path)

            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df = df[df['date'] <= DATA_CUTOFF].copy()

            if 'bucket_date' in df.columns:
                df['bucket_date'] = pd.to_datetime(df['bucket_date'])
                df = df[df['bucket_date'] <= DATA_CUTOFF].copy()

            outputs[name] = df
            print(f"  Loaded Phase 1 output: {name} ({len(df)} rows)")
        else:
            outputs[name] = None
            print(f"  Missing Phase 1 output: {name} at {path}")

    return outputs

def derive_phase1_timeline_events(phase1_outputs):
    """
    Derive Phase 1 timeline events from Phase 1 output CSVs.

    No hard-coded event dates are used here. Dates are computed from the data.
    """
    events = []

    def first_crossing(df, condition, series, event_type, description_fn):
        if df is None or len(df) == 0:
            return

        tmp = df.copy()
        if 'date' not in tmp.columns:
            return

        tmp['date'] = pd.to_datetime(tmp['date'])
        tmp = tmp.dropna(subset=['date']).sort_values('date')
        hit = tmp[condition(tmp)].copy()

        if len(hit) == 0:
            return

        row = hit.iloc[0]
        events.append({
            'date': pd.Timestamp(row['date']),
            'series': series,
            'type': event_type,
            'description': description_fn(row),
        })

    def latest_event(df, series, event_type, description_fn):
        if df is None or len(df) == 0:
            return

        tmp = df.copy()
        if 'date' in tmp.columns:
            date_col = 'date'
        elif 'bucket_date' in tmp.columns:
            date_col = 'bucket_date'
        else:
            return

        tmp[date_col] = pd.to_datetime(tmp[date_col])
        tmp = tmp.dropna(subset=[date_col]).sort_values(date_col)

        if len(tmp) == 0:
            return

        row = tmp.iloc[-1]
        events.append({
            'date': pd.Timestamp(row[date_col]),
            'series': series,
            'type': event_type,
            'description': description_fn(row),
        })

    cbuae = phase1_outputs.get('cbuae_reserve_composition')
    if cbuae is not None and len(cbuae) > 0:
        for col in [
            'cash_deposits_share_of_gross_reserves',
            'foreign_investments_share_of_gross_reserves',
            'foreign_investments_bn',
            'cash_deposits_abroad_bn',
        ]:
            if col in cbuae.columns:
                cbuae[col] = pd.to_numeric(cbuae[col], errors='coerce')

        first_crossing(
            cbuae,
            lambda d: d['cash_deposits_share_of_gross_reserves'] < 0.50,
            'Phase1_CBUAE_reserve_composition',
            'phase1_balance_sheet_event',
            lambda r: (
                'CBUAE cash/deposits share falls below 50% '
                f"({r['cash_deposits_share_of_gross_reserves']:.1%})"
            )
        )

        first_crossing(
            cbuae,
            lambda d: d['foreign_investments_bn'] > d['cash_deposits_abroad_bn'],
            'Phase1_CBUAE_reserve_composition',
            'phase1_balance_sheet_event',
            lambda r: (
                'CBUAE foreign investments exceed cash/deposits '
                f"(${r['foreign_investments_bn']:.1f}B vs ${r['cash_deposits_abroad_bn']:.1f}B)"
            )
        )

        first_crossing(
            cbuae,
            lambda d: d['cash_deposits_share_of_gross_reserves'] < 0.35,
            'Phase1_CBUAE_reserve_composition',
            'phase1_balance_sheet_event',
            lambda r: (
                'CBUAE cash/deposits share falls below 35% '
                f"({r['cash_deposits_share_of_gross_reserves']:.1%})"
            )
        )

        first_crossing(
            cbuae,
            lambda d: d['cash_deposits_share_of_gross_reserves'] < 0.25,
            'Phase1_CBUAE_reserve_composition',
            'phase1_balance_sheet_event',
            lambda r: (
                'CBUAE cash/deposits share falls below 25% '
                f"({r['cash_deposits_share_of_gross_reserves']:.1%})"
            )
        )

    clc = phase1_outputs.get('uae_import_liquidity_clc')
    if clc is not None and len(clc) > 0:
        clc = clc.copy()
        if 'date' in clc.columns:
            clc['date'] = pd.to_datetime(clc['date'])
            clc = clc[clc['date'] >= pd.Timestamp('2024-03-31')].copy()

        for col in ['clc_real_3m', 'clc_real_6m']:
            if col in clc.columns:
                clc[col] = pd.to_numeric(clc[col], errors='coerce')

        first_crossing(
            clc,
            lambda d: d['clc_real_3m'] < 1.0,
            'Phase1_CLC',
            'phase1_liquidity_cliff_event',
            lambda r: f"3-month import CLC crosses below 1 ({r['clc_real_3m']:.2f})"
        )

        first_crossing(
            clc,
            lambda d: d['clc_real_6m'] < 1.0,
            'Phase1_CLC',
            'phase1_liquidity_cliff_event',
            lambda r: f"6-month import CLC below 1 in CBUAE window ({r['clc_real_6m']:.2f})"
        )

    bis_usd = phase1_outputs.get('bis_global_usd_liabilities')
    if bis_usd is not None and len(bis_usd) > 0:
        bis_usd = bis_usd.copy()
        bis_usd['date'] = pd.to_datetime(bis_usd['date'])
        bis_usd['value_usd_bn'] = pd.to_numeric(bis_usd['value_usd_bn'], errors='coerce')
        bis_usd = bis_usd.dropna(subset=['date', 'value_usd_bn']).sort_values('date')

        if len(bis_usd) > 0:
            max_row = bis_usd.loc[bis_usd['value_usd_bn'].idxmax()]
            events.append({
                'date': pd.Timestamp(max_row['date']),
                'series': 'Phase1_BIS_USD_liabilities',
                'type': 'phase1_routing_event',
                'description': (
                    'BIS global USD liabilities to UAE reach sample high '
                    f"(${max_row['value_usd_bn']:.1f}B)"
                ),
            })

            latest_row = bis_usd.iloc[-1]
            events.append({
                'date': pd.Timestamp(latest_row['date']),
                'series': 'Phase1_BIS_USD_liabilities',
                'type': 'phase1_routing_event',
                'description': (
                    'Latest BIS global USD liabilities to UAE '
                    f"(${latest_row['value_usd_bn']:.1f}B)"
                ),
            })

    btar = phase1_outputs.get('uae_btar_scenarios')
    if btar is not None and len(btar) > 0:
        btar = btar.copy()
        btar['bucket_date'] = pd.to_datetime(btar['bucket_date'])
        btar['uae_btar'] = pd.to_numeric(btar['uae_btar'], errors='coerce')

        low = btar[
            (btar['scenario'] == 'low')
            & (btar['uae_btar'] > 1.0)
        ].copy()

        if len(low) > 0:
            row = low.sort_values('uae_btar', ascending=False).iloc[0]
            events.append({
                'date': pd.Timestamp(row['bucket_date']),
                'series': 'Phase1_BTAR',
                'type': 'phase1_absorption_event',
                'description': (
                    'Low-scenario UAE-BTAR exceeds 1 for '
                    f"{row['bucket']} ({row['uae_btar']:.2f})"
                ),
            })

    events = [e for e in events if e['date'] <= DATA_CUTOFF]
    return events

def create_phase1_threshold_breaks(phase1_outputs):
    """
    Create a data-driven threshold-break table from fixed Phase 1 outputs.

    These are accounting / liquidity threshold breaks, not model-fitted statistical breaks.
    They are the main Phase 2 break objects for the corrected Phase 1 framework.
    """
    rows = []

    def add_row(date, metric, threshold, value, event, interpretation, source_file):
        rows.append({
            'date': pd.Timestamp(date),
            'metric': metric,
            'threshold': threshold,
            'value': value,
            'event': event,
            'interpretation': interpretation,
            'source_file': source_file,
        })

    def first_hit(df, condition):
        if df is None or len(df) == 0:
            return None

        tmp = df.copy()

        if 'date' not in tmp.columns:
            return None

        tmp['date'] = pd.to_datetime(tmp['date'])
        tmp = tmp.dropna(subset=['date']).sort_values('date')

        hit = tmp[condition(tmp)].copy()

        if len(hit) == 0:
            return None

        return hit.iloc[0]

    cbuae = phase1_outputs.get('cbuae_reserve_composition')

    if cbuae is not None and len(cbuae) > 0:
        cbuae = cbuae.copy()
        cbuae['date'] = pd.to_datetime(cbuae['date'])

        for col in [
            'cash_deposits_share_of_gross_reserves',
            'foreign_investments_share_of_gross_reserves',
            'cash_deposits_abroad_bn',
            'foreign_investments_bn',
            'gross_reserves_bn',
        ]:
            if col in cbuae.columns:
                cbuae[col] = pd.to_numeric(cbuae[col], errors='coerce')

        row = first_hit(
            cbuae,
            lambda d: d['cash_deposits_share_of_gross_reserves'] < 0.50
        )
        if row is not None:
            add_row(
                row['date'],
                'cash_deposits_share_of_gross_reserves',
                '< 50%',
                float(row['cash_deposits_share_of_gross_reserves']),
                'CBUAE cash/deposits share falls below 50%',
                'Cash/deposit-like reserve layer loses majority status.',
                'cbuae_reserve_composition.csv'
            )

        row = first_hit(
            cbuae,
            lambda d: d['foreign_investments_bn'] > d['cash_deposits_abroad_bn']
        )
        if row is not None:
            add_row(
                row['date'],
                'foreign_investments_bn > cash_deposits_abroad_bn',
                'foreign investments > cash/deposits',
                (
                    f"foreign_investments=${float(row['foreign_investments_bn']):.1f}B; "
                    f"cash_deposits=${float(row['cash_deposits_abroad_bn']):.1f}B"
                ),
                'CBUAE foreign investments exceed cash/deposits',
                'Securities/foreign-investment reserve layer becomes larger than cash/deposit-like liquidity.',
                'cbuae_reserve_composition.csv'
            )

        row = first_hit(
            cbuae,
            lambda d: d['cash_deposits_share_of_gross_reserves'] < 0.35
        )
        if row is not None:
            add_row(
                row['date'],
                'cash_deposits_share_of_gross_reserves',
                '< 35%',
                float(row['cash_deposits_share_of_gross_reserves']),
                'CBUAE cash/deposits share falls below 35%',
                'Cash/deposit-like reserve layer becomes thin relative to gross reserves.',
                'cbuae_reserve_composition.csv'
            )

        row = first_hit(
            cbuae,
            lambda d: d['cash_deposits_share_of_gross_reserves'] < 0.25
        )
        if row is not None:
            add_row(
                row['date'],
                'cash_deposits_share_of_gross_reserves',
                '< 25%',
                float(row['cash_deposits_share_of_gross_reserves']),
                'CBUAE cash/deposits share falls below 25%',
                'Cash/deposit-like reserve layer approaches hard liquidity minimum.',
                'cbuae_reserve_composition.csv'
            )

    clc = phase1_outputs.get('uae_import_liquidity_clc')

    if clc is not None and len(clc) > 0:
        clc = clc.copy()
        clc['date'] = pd.to_datetime(clc['date'])
        clc = clc[clc['date'] >= pd.Timestamp('2024-03-31')].copy()

        for col in [
            'clc_real_3m',
            'clc_real_6m',
            'cash_deposits_abroad_bn',
            'import_need_3m_bn',
            'import_need_6m_bn',
            'implied_monthly_imports_bn',
        ]:
            if col in clc.columns:
                clc[col] = pd.to_numeric(clc[col], errors='coerce')

        row = first_hit(
            clc,
            lambda d: d['clc_real_3m'] < 1.0
        )
        if row is not None:
            add_row(
                row['date'],
                'clc_real_3m',
                '< 1',
                float(row['clc_real_3m']),
                '3-month import CLC crosses below 1',
                'Cash/deposit-like reserve layer no longer covers a 3-month implied import-liquidity floor.',
                'uae_import_liquidity_clc.csv'
            )

        row = first_hit(
            clc,
            lambda d: d['clc_real_6m'] < 1.0
        )
        if row is not None:
            add_row(
                row['date'],
                'clc_real_6m',
                '< 1',
                float(row['clc_real_6m']),
                '6-month import CLC below 1 in observed CBUAE window',
                'Cash/deposit-like reserve layer does not cover a 6-month implied import-liquidity floor in the observed CBUAE reserve-composition window.',
                'uae_import_liquidity_clc.csv'
            )

    bis_usd = phase1_outputs.get('bis_global_usd_liabilities')

    if bis_usd is not None and len(bis_usd) > 0:
        bis_usd = bis_usd.copy()
        bis_usd['date'] = pd.to_datetime(bis_usd['date'])
        bis_usd['value_usd_bn'] = pd.to_numeric(bis_usd['value_usd_bn'], errors='coerce')
        bis_usd = bis_usd.dropna(subset=['date', 'value_usd_bn']).sort_values('date')

        if len(bis_usd) > 0:
            max_row = bis_usd.loc[bis_usd['value_usd_bn'].idxmax()]
            add_row(
                max_row['date'],
                'bis_global_usd_liabilities_to_uae',
                'sample high',
                float(max_row['value_usd_bn']),
                'BIS global USD liabilities to UAE reach sample high',
                'Global banking dollar-liability layer to UAE reaches its highest observed value in the BIS sample.',
                'channel_Channel_2_BIS_global_usd_liabilities.csv'
            )

            latest_row = bis_usd.iloc[-1]
            add_row(
                latest_row['date'],
                'bis_global_usd_liabilities_to_uae',
                'latest observation',
                float(latest_row['value_usd_bn']),
                'Latest BIS global USD liabilities to UAE',
                'Latest observed global BIS USD-liability layer remains large relative to official CBUAE reserves.',
                'channel_Channel_2_BIS_global_usd_liabilities.csv'
            )

    btar = phase1_outputs.get('uae_btar_scenarios')

    if btar is not None and len(btar) > 0:
        btar = btar.copy()
        btar['bucket_date'] = pd.to_datetime(btar['bucket_date'])
        btar['uae_btar'] = pd.to_numeric(btar['uae_btar'], errors='coerce')

        low = btar[
            (btar['scenario'] == 'low')
            & (btar['uae_btar'] > 1.0)
        ].copy()

        if len(low) > 0:
            row = low.sort_values('uae_btar', ascending=False).iloc[0]
            add_row(
                row['bucket_date'],
                'uae_btar',
                'low scenario > 1',
                float(row['uae_btar']),
                f"Low-scenario UAE-BTAR exceeds 1 for {row['bucket']}",
                'Even the low encumbrance/leverage scenario is larger than observed Fed balance-sheet absorption for this bucket.',
                'uae_btar_scenarios.csv'
            )

    threshold_df = pd.DataFrame(rows)

    if len(threshold_df) == 0:
        threshold_df = pd.DataFrame(columns=[
            'date',
            'metric',
            'threshold',
            'value',
            'event',
            'interpretation',
            'source_file',
        ])
    else:
        threshold_df['date'] = pd.to_datetime(threshold_df['date'])
        threshold_df = threshold_df[threshold_df['date'] <= DATA_CUTOFF].copy()
        threshold_df = threshold_df.sort_values(['date', 'metric']).reset_index(drop=True)

    out = STATS_DIR / 'phase1_threshold_breaks.csv'
    threshold_df.to_csv(out, index=False)

    print(f"  Saved Phase 1 threshold breaks: {out}")
    print(threshold_df.to_string(index=False))

    return threshold_df


def get_series(master, series_name):
    s = master[master['series'] == series_name].copy().sort_values('date')
    return s[['date', 'value']].reset_index(drop=True)


def get_te_series(te_us, category):
    df = te_us[te_us['Category'] == category].copy().sort_values('DateTime')
    return df[['DateTime', 'Value']].rename(
        columns={'DateTime': 'date', 'Value': 'value'}).reset_index(drop=True)


# =============================================================================
# 1. STRUCTURAL BREAK TESTS
# =============================================================================

def detect_breaks(series, dates, series_label, method='pelt', max_breaks=4):
    """
    Detect structural breaks using ruptures (Pelt algorithm with L2 cost).
    Returns dict with break dates and segment statistics.
    """
    import ruptures as rpt

    y = np.asarray(series, dtype=float)
    mask = ~np.isnan(y)
    y_clean = y[mask]
    dates_clean = dates[mask].reset_index(drop=True)

    if len(y_clean) < 10:
        return {
            'series': series_label,
            'n_obs': len(y_clean),
            'error': 'insufficient data'
        }

    # Try multiple penalty values and report the most parsimonious result
    # with 1-max_breaks breaks
    sigma2 = np.var(y_clean)
    penalties = [
        np.log(len(y_clean)) * sigma2,     # BIC-like
        2 * np.log(len(y_clean)) * sigma2, # heavier
        0.5 * np.log(len(y_clean)) * sigma2, # lighter
        3 * sigma2,
        10 * sigma2,
    ]

    results_by_pen = {}
    algo = rpt.Pelt(model="l2").fit(y_clean)
    for pen in penalties:
        try:
            bkps = algo.predict(pen=pen)[:-1]
            results_by_pen[pen] = bkps
        except Exception:
            continue

    # Pick the result with 1 <= breaks <= max_breaks, preferring fewer
    chosen_bkps = None
    for pen in sorted(results_by_pen.keys(), reverse=True):  # highest pen first => fewest breaks
        bkps = results_by_pen[pen]
        if 1 <= len(bkps) <= max_breaks:
            chosen_bkps = bkps
            chosen_pen = pen
            break

    if chosen_bkps is None:
        # Accept whatever we got
        if results_by_pen:
            chosen_bkps = min(results_by_pen.values(), key=len)
            chosen_pen = None
        else:
            return {'series': series_label, 'n_obs': len(y_clean), 'error': 'no breaks detected'}

    # Map to dates
    break_dates = [dates_clean.iloc[i] for i in chosen_bkps if i < len(dates_clean)]

    # Segment statistics
    segments = []
    prev = 0
    for b in list(chosen_bkps) + [len(y_clean)]:
        seg = y_clean[prev:b]
        seg_dates = dates_clean.iloc[prev:b]
        if len(seg) > 0:
            segments.append({
                'start': seg_dates.iloc[0].strftime('%Y-%m'),
                'end': seg_dates.iloc[-1].strftime('%Y-%m'),
                'n': int(len(seg)),
                'mean': float(np.mean(seg)),
                'std': float(np.std(seg)),
            })
        prev = b

    # Confidence: compare segment means
    if len(segments) >= 2:
        pct_changes = []
        for i in range(len(segments) - 1):
            m1, m2 = segments[i]['mean'], segments[i+1]['mean']
            s1, s2 = segments[i]['std'], segments[i+1]['std']
            # Welch-style t-stat for magnitude
            if s1 > 0 or s2 > 0:
                pooled_se = np.sqrt((s1**2 / segments[i]['n']) + (s2**2 / segments[i+1]['n']))
                t_stat = (m2 - m1) / pooled_se if pooled_se > 0 else np.nan
            else:
                t_stat = np.nan
            pct_changes.append({
                'break_at': break_dates[i].strftime('%Y-%m'),
                'pre_mean': m1,
                'post_mean': m2,
                'pct_change': (m2 - m1) / m1 * 100 if m1 != 0 else np.nan,
                't_stat': float(t_stat) if not np.isnan(t_stat) else None,
            })
    else:
        pct_changes = []

    return {
        'series': series_label,
        'n_obs': int(len(y_clean)),
        'n_breaks': len(chosen_bkps),
        'break_dates': [d.strftime('%Y-%m-%d') for d in break_dates],
        'segments': segments,
        'segment_changes': pct_changes,
        'method': 'Pelt + L2 cost',
    }


def run_break_tests(master, te_us):
    print("\n  Structural break tests...")
    results = {}

    # UAE Portfolio Investment (annual, the flagship breakout)
    pi = get_series(master, 'portfolio_investment')
    if len(pi) > 5:
        results['uae_portfolio_investment'] = detect_breaks(
            pi['value'], pi['date'],
            'UAE Portfolio Investment (annual, USD mn)'
        )

    # UAE FX Reserves level (monthly 1973-2025)
    fx = get_series(master, 'forex_reserves_monthly')
    if len(fx) > 24:
        results['uae_fx_reserves_level'] = detect_breaks(
            fx['value'], fx['date'],
            'UAE FX Reserves level (monthly, USD mn)'
        )

    # UAE FX Reserves YoY growth
    fx_g = fx.copy()
    fx_g['yoy'] = fx_g['value'].pct_change(12) * 100
    fx_g = fx_g.dropna(subset=['yoy'])
    if len(fx_g) > 24:
        results['uae_fx_reserves_yoy'] = detect_breaks(
            fx_g['yoy'], fx_g['date'],
            'UAE FX Reserves YoY growth (monthly, %)'
        )

    # UAE M2 level
    m2 = get_series(master, 'M2')
    if len(m2) > 24:
        results['uae_m2_level'] = detect_breaks(
            m2['value'], m2['date'],
            'UAE M2 Money Supply (monthly, USD mn)'
        )

    # Foreign Treasury holdings — per custodial country MoM changes
    for country in ['Belgium', 'Canada', 'UK', 'Japan']:
        cat = f'Foreign Treasury Holdings {country}'
        df = get_te_series(te_us, cat)
        df['mom'] = df['value'].diff()
        df_clean = df.dropna(subset=['mom'])
        if len(df_clean) > 24:
            results[f'treasury_{country.lower()}_mom'] = detect_breaks(
                df_clean['mom'], df_clean['date'],
                f'{country} Treasury Holdings MoM change (USD bn)'
            )

    # SOFR-EFFR spread (resample to monthly mean)
    sofr = get_te_series(te_us, 'Secured Overnight Financing Rate')
    effr = get_te_series(te_us, 'Effective Federal Funds Rate')
    if len(sofr) > 50 and len(effr) > 50:
        spread = pd.merge_asof(
            sofr.sort_values('date'),
            effr.sort_values('date').rename(columns={'value': 'effr'}),
            on='date', direction='backward'
        )
        spread['spread_bp'] = (spread['value'] - spread['effr']) * 100
        # Monthly mean
        spread_m = spread.set_index('date')['spread_bp'].resample('M').mean().reset_index()
        spread_m = spread_m.dropna()
        if len(spread_m) > 24:
            results['sofr_effr_spread_monthly'] = detect_breaks(
                spread_m['spread_bp'], spread_m['date'],
                'SOFR minus EFFR spread (monthly mean, bp)'
            )

    # Fed balance sheet level
    fed = get_te_series(te_us, 'Central Bank Balance Sheet')
    if len(fed) > 50:
        fed_m = fed.set_index('date').resample('M').last().reset_index()
        results['fed_balance_sheet'] = detect_breaks(
            fed_m['value'], fed_m['date'],
            'Fed Balance Sheet (monthly end, USD mn)'
        )

    # Save results
    with open(STATS_DIR / 'structural_breaks.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"    Saved: {STATS_DIR / 'structural_breaks.json'}")

    # Print summary to console
    print("\n  === BREAK DATES SUMMARY ===")
    for name, r in results.items():
        if 'break_dates' in r:
            dates_str = ', '.join(r['break_dates']) if r['break_dates'] else '(none)'
            print(f"    {name}: {dates_str}  ({r.get('n_breaks', 0)} breaks, n={r.get('n_obs', 0)})")

    return results


# =============================================================================
# 2. ROLLING VOLATILITY / ANOMALY DETECTION
# =============================================================================

def rolling_anomaly_detection(te_us, countries, window=12, z_threshold=2.0):
    """
    Rolling MoM change with z-score flagging.
    Flags observations where |z| > threshold relative to trailing window.
    """
    print("\n  Rolling anomaly detection on foreign Treasury holdings...")
    all_results = {}
    all_anomalies = []

    for country in countries:
        cat = (f'Foreign Treasury Holdings {country}' if country != 'Aggregate'
               else 'Foreign Treasury Holdings')
        df = get_te_series(te_us, cat)
        if len(df) < window + 2:
            continue
        df['mom'] = df['value'].diff()
        df['rolling_mean'] = df['mom'].rolling(window, min_periods=6).mean()
        df['rolling_std'] = df['mom'].rolling(window, min_periods=6).std()
        df['z'] = (df['mom'] - df['rolling_mean']) / df['rolling_std']
        df['anomaly'] = df['z'].abs() > z_threshold
        df['country'] = country
        all_results[country] = df

        # Report anomalies
        anom = df[df['anomaly']].copy()
        for _, row in anom.iterrows():
            all_anomalies.append({
                'country': country,
                'date': row['date'].strftime('%Y-%m-%d'),
                'mom_change_bn': float(row['mom']),
                'z_score': float(row['z']),
            })

    # Rank all anomalies by absolute z
    anom_df = pd.DataFrame(all_anomalies).sort_values('z_score', key=abs, ascending=False)
    anom_df.to_csv(STATS_DIR / 'treasury_anomalies.csv', index=False)
    print(f"    Top anomalies (|z| > {z_threshold}):")
    print(anom_df.head(15).to_string(index=False))

    return all_results, anom_df


def plot_anomalies(anomaly_results, z_threshold=2.0):
    countries = list(anomaly_results.keys())
    n = len(countries)
    fig, axes = plt.subplots(n, 1, figsize=(11, 2.5 * n), sharex=True)
    if n == 1:
        axes = [axes]
    for ax, (country, df) in zip(axes, anomaly_results.items()):
        recent = df[df['date'] >= '2018-01-01']
        ax.plot(recent['date'], recent['mom'], color='#264653', linewidth=1)
        anom = recent[recent['anomaly']]
        if len(anom) > 0:
            ax.scatter(anom['date'], anom['mom'],
                       color='#E76F51', s=35, zorder=3,
                       label=f'|z|>{z_threshold}')
        ax.axhline(0, color='black', linewidth=0.4, alpha=0.3)
        ax.set_title(f'{country}: MoM change in Treasury holdings (USD bn)',
                     loc='left', fontsize=10)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        if len(anom) > 0:
            ax.legend(loc='upper left', frameon=False, fontsize=8)

    axes[-1].set_xlabel('')
    fig.suptitle('Rolling-window anomaly detection: foreign Treasury holdings by custodial country',
                 fontsize=12, y=1.00)
    plt.tight_layout()
    out = OUT_PLOTS / 'phase2_anomaly_detection.png'
    plt.savefig(out, bbox_inches='tight')
    plt.close()
    print(f"    Saved: {out}")


# =============================================================================
# 3. LEAD-LAG CROSS-CORRELATION
# =============================================================================

def lead_lag_analysis(master, te_us, max_lag_months=12):
    """
    Cross-correlation of UAE-side flows (monthly) against US custodial stocks.
    Identifies if UAE flows lead or lag observable US-side movements.
    """
    print("\n  Lead-lag cross-correlation analysis...")

    # UAE FX reserves MoM change (proxy for UAE-side dollar flow)
    fx = get_series(master, 'forex_reserves_monthly')
    fx_m = fx.sort_values('date').set_index('date')['value'].resample('M').last().diff()

    # UAE M2 MoM change
    m2 = get_series(master, 'M2')
    m2_m = m2.sort_values('date').set_index('date')['value'].resample('M').last().diff()

    results = []
    for uae_series_name, uae_series in [('uae_fx_mom', fx_m), ('uae_m2_mom', m2_m)]:
        for country in ['Belgium', 'Canada', 'UK', 'Japan', 'China']:
            cat = f'Foreign Treasury Holdings {country}'
            t = get_te_series(te_us, cat)
            t_m = t.sort_values('date').set_index('date')['value'].resample('M').last().diff()

            # Align on monthly index
            combined = pd.concat([uae_series, t_m], axis=1, join='inner').dropna()
            combined.columns = ['uae', 'us']
            if len(combined) < max_lag_months * 3:
                continue

            # Cross-correlation for lags -max_lag to +max_lag
            lag_corrs = []
            for lag in range(-max_lag_months, max_lag_months + 1):
                if lag < 0:
                    c = combined['uae'].shift(-lag).corr(combined['us'])
                else:
                    c = combined['uae'].corr(combined['us'].shift(lag))
                lag_corrs.append({'lag_months': lag, 'corr': c})
            corr_df = pd.DataFrame(lag_corrs)
            corr_df = corr_df.dropna(subset=['corr'])
            if len(corr_df) == 0:
                continue

            peak = corr_df.loc[corr_df['corr'].abs().idxmax()]
            results.append({
                'uae_series': uae_series_name,
                'us_country': country,
                'peak_corr': float(peak['corr']),
                'peak_lag_months': int(peak['lag_months']),
                'interpretation': (
                    f"UAE leads US by {abs(int(peak['lag_months']))} months"
                    if peak['lag_months'] < 0 else
                    f"UAE lags US by {int(peak['lag_months'])} months"
                    if peak['lag_months'] > 0 else
                    "contemporaneous"
                ),
                'n_obs': int(len(combined)),
            })

    if len(results) == 0:
        ll_df = pd.DataFrame(columns=[
            'uae_series',
            'us_country',
            'peak_corr',
            'peak_lag_months',
            'interpretation',
            'n_obs'
        ])
    else:
        ll_df = pd.DataFrame(results).sort_values(
            'peak_corr',
            key=lambda s: s.abs(),
            ascending=False
        )

    ll_df.to_csv(STATS_DIR / 'lead_lag_correlations.csv', index=False)
    print(f"    Top lead-lag relationships:")
    print(ll_df.head(10).to_string(index=False))
    return ll_df

# =============================================================================
# 4. UNIFIED TIMELINE CHART
# =============================================================================
def build_timeline_chart(break_results, anomaly_df, phase1_outputs=None, phase1_threshold_df=None):
    """
    Build a publication-quality pre-event threshold sequence figure.

    This replaces the prior diagnostic dot-cloud timeline. The article figure
    should show only the data-driven threshold sequence that matters:
      - reserve-composition deterioration
      - CLC breach
      - BIS banking-layer scale
      - BTAR crossing
      - Bessent policy signal

    Diagnostic structural-break and anomaly events are still saved to CSV,
    but they are not plotted in the article figure.
    """
    print("\n  Building publication threshold-sequence figure...")

    OUT_PLOTS.mkdir(parents=True, exist_ok=True)
    STATS_DIR.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # 1. Preserve full diagnostic event table for audit, but do not plot it.
    # -------------------------------------------------------------------------
    diagnostic_events = []

    for series_name, r in break_results.items():
        if 'break_dates' not in r:
            continue

        for bd in r['break_dates']:
            diagnostic_events.append({
                'date': pd.Timestamp(bd),
                'series': series_name,
                'type': 'structural_break',
                'description': r.get('series', series_name),
            })

    top_anom = anomaly_df.head(10)

    for _, row in top_anom.iterrows():
        diagnostic_events.append({
            'date': pd.Timestamp(row['date']),
            'series': f"treasury_{row['country']}",
            'type': 'anomaly',
            'description': (
                f"{row['country']} Treasury MoM z={row['z_score']:.1f}, "
                f"delta ${row['mom_change_bn']:.0f}B"
            ),
        })

    if phase1_outputs is not None:
        phase1_events = derive_phase1_timeline_events(phase1_outputs)
        diagnostic_events.extend(phase1_events)
        print(f"    Phase 1-derived diagnostic events available: {len(phase1_events)}")

    diagnostic_events.append({
        'date': FICC_SPONSORED_DARK,
        'series': 'FICC_structure',
        'type': 'architecture_event',
        'description': 'FICC Sponsored list moved behind MyDTCC',
    })

    diagnostic_events.append({
        'date': FED_PIVOT,
        'series': 'Fed_policy',
        'type': 'policy_event',
        'description': 'Fed balance-sheet stress-window expansion begins',
    })

    diagnostic_events.append({
        'date': SOFR_SPIKE,
        'series': 'Repo_market',
        'type': 'market_event',
        'description': 'SOFR stress marker',
    })

    diagnostic_events.append({
        'date': PART4_PUBLISHED,
        'series': 'Paper',
        'type': 'publication',
        'description': 'Part IV published',
    })

    diagnostic_df = pd.DataFrame(diagnostic_events)

    if len(diagnostic_df) == 0:
        diagnostic_df = pd.DataFrame(columns=['date', 'series', 'type', 'description'])
    else:
        diagnostic_df['date'] = pd.to_datetime(diagnostic_df['date'])
        diagnostic_df = diagnostic_df[diagnostic_df['date'] <= DATA_CUTOFF].copy()
        diagnostic_df = diagnostic_df.sort_values('date').reset_index(drop=True)

    diagnostic_out = STATS_DIR / 'timeline_events_diagnostics.csv'
    diagnostic_df.to_csv(diagnostic_out, index=False)
    print(f"    Saved diagnostic timeline table: {diagnostic_out}")

    # -------------------------------------------------------------------------
    # 2. Use threshold table for publication figure.
    # -------------------------------------------------------------------------
    if phase1_threshold_df is None:
        if phase1_outputs is None:
            raise RuntimeError(
                "build_timeline_chart requires phase1_threshold_df or phase1_outputs."
            )
        phase1_threshold_df = create_phase1_threshold_breaks(phase1_outputs)

    threshold_df = phase1_threshold_df.copy()

    if len(threshold_df) == 0:
        raise RuntimeError("Phase 1 threshold table is empty; cannot build figure.")

    threshold_df['date'] = pd.to_datetime(threshold_df['date'])
    threshold_df['event'] = threshold_df['event'].astype(str)
    threshold_df['metric'] = threshold_df['metric'].astype(str)
    threshold_df['threshold'] = threshold_df['threshold'].astype(str)
    threshold_df = threshold_df.sort_values('date').reset_index(drop=True)

    sequence_rows = []

    def add_sequence_event(match_text, lane, label, short_note=None):
        hit = threshold_df[
            threshold_df['event'].str.contains(match_text, case=False, regex=False)
        ].copy()

        if len(hit) == 0:
            print(f"    WARNING: threshold event not found: {match_text}")
            return

        row = hit.iloc[0]

        sequence_rows.append({
            'date': pd.Timestamp(row['date']),
            'lane': lane,
            'label': label,
            'short_note': short_note if short_note is not None else row['event'],
            'source_event': row['event'],
            'metric': row['metric'],
            'threshold': row['threshold'],
            'value': row['value'],
        })

    add_sequence_event(
        '6-month import CLC below 1',
        'Liquidity cover',
        '6m CLC < 1',
        '6-month import cover already below one'
    )

    add_sequence_event(
        'cash/deposits share falls below 50%',
        'Reserve composition',
        'Cash share < 50%',
        'cash/deposit reserve layer loses majority status'
    )

    add_sequence_event(
        'foreign investments exceed cash/deposits',
        'Reserve composition',
        'Foreign investments > cash',
        'investment layer exceeds cash/deposit layer'
    )

    add_sequence_event(
        '3-month import CLC crosses below 1',
        'Liquidity cover',
        '3m CLC < 1',
        'cash/deposit layer below 3-month import floor'
    )

    add_sequence_event(
        'BIS global USD liabilities to UAE reach sample high',
        'Banking layer',
        'BIS USD liabilities high',
        'banking-layer dollar exposure reaches sample high'
    )

    add_sequence_event(
        'cash/deposits share falls below 35%',
        'Reserve composition',
        'Cash share < 35%',
        'cash/deposit reserve layer becomes thin'
    )

    add_sequence_event(
        'Low-scenario UAE-BTAR exceeds 1',
        'Absorption risk',
        'Low BTAR > 1',
        'low scenario exceeds observed absorption denominator'
    )

    add_sequence_event(
        'cash/deposits share falls below 25%',
        'Reserve composition',
        'Cash share < 25%',
        'cash/deposit reserve layer approaches hard minimum'
    )

    sequence_rows.append({
        'date': BESSENT_DATE,
        'lane': 'Policy marker',
        'label': 'Bessent signal',
        'short_note': 'public policy signal',
        'source_event': 'Bessent UAE swap-line signal',
        'metric': 'policy_marker',
        'threshold': 'public signal',
        'value': '',
    })

    sequence_df = pd.DataFrame(sequence_rows)
    sequence_df['date'] = pd.to_datetime(sequence_df['date'])
    sequence_df = sequence_df.sort_values('date').reset_index(drop=True)

    sequence_out = STATS_DIR / 'pre_event_threshold_sequence.csv'
    sequence_df.to_csv(sequence_out, index=False)
    print(f"    Saved publication threshold sequence table: {sequence_out}")

    # -------------------------------------------------------------------------
    # 3. Plot publication-quality threshold sequence.
    # -------------------------------------------------------------------------
    lanes = [
        'Reserve composition',
        'Liquidity cover',
        'Banking layer',
        'Absorption risk',
        'Policy marker',
    ]

    y_map = {
        'Reserve composition': 5,
        'Liquidity cover': 4,
        'Banking layer': 3,
        'Absorption risk': 2,
        'Policy marker': 1,
    }

    lane_colors = {
        'Reserve composition': '#1f4e79',
        'Liquidity cover': '#8f1d14',
        'Banking layer': '#2f6f4e',
        'Absorption risk': '#6f4aa1',
        'Policy marker': '#b03a2e',
    }

    label_display = {
        '6m CLC < 1': '6m CLC\n< 1',
        'Cash share < 50%': 'Cash share\n< 50%',
        'Foreign investments > cash': 'Foreign investments\n> cash',
        '3m CLC < 1': '3m CLC\n< 1',
        'BIS USD liabilities high': 'BIS USD liabilities\nsample high',
        'Cash share < 35%': 'Cash share\n< 35%',
        'Low BTAR > 1': 'Low BTAR\n> 1',
        'Cash share < 25%': 'Cash share\n< 25%',
        'Bessent signal': 'Bessent\nsignal',
    }

    # Manual offsets are intentional. This is a publication figure, not a generic scatter.
    label_offsets = {
        '6m CLC < 1': (0, -34, 'center', 'top'),
        'Cash share < 50%': (-22, 34, 'center', 'bottom'),
        'Foreign investments > cash': (0, 42, 'center', 'bottom'),
        '3m CLC < 1': (0, -34, 'center', 'top'),
        'BIS USD liabilities high': (36, 42, 'left', 'bottom'),
        'Cash share < 35%': (22, 34, 'center', 'bottom'),
        'Low BTAR > 1': (0, -36, 'center', 'top'),
        'Cash share < 25%': (0, 34, 'center', 'bottom'),
        'Bessent signal': (-34, 34, 'right', 'bottom'),
    }

    fig, ax = plt.subplots(figsize=(14.5, 6.2))

    x_min = pd.Timestamp('2024-01-01')
    x_max = pd.Timestamp('2026-06-15')

    for lane in lanes:
        y = y_map[lane]
        ax.hlines(
            y,
            xmin=x_min,
            xmax=x_max,
            color='#d8d8d8',
            linewidth=1.1,
            zorder=1
        )


    for _, row in sequence_df.iterrows():
        x = pd.Timestamp(row['date'])
        lane = row['lane']
        y = y_map[lane]
        color = lane_colors.get(lane, '#555555')
        raw_label = str(row['label'])
        label = label_display.get(raw_label, raw_label)

        ax.scatter(
            x,
            y,
            s=155,
            color=color,
            edgecolor='white',
            linewidth=1.2,
            zorder=4
        )

        dx, dy, ha, va = label_offsets.get(raw_label, (0, 30, 'center', 'bottom'))

        ax.annotate(
            label,
            xy=(x, y),
            xytext=(dx, dy),
            textcoords='offset points',
            ha=ha,
            va=va,
            fontsize=9,
            color='#202020',
            linespacing=1.05,
            bbox={
                'boxstyle': 'round,pad=0.25',
                'facecolor': 'white',
                'edgecolor': '#d9d9d9',
                'linewidth': 0.6,
                'alpha': 0.96
            },
            arrowprops={
                'arrowstyle': '-',
                'color': '#9a9a9a',
                'linewidth': 0.7,
                'shrinkA': 2,
                'shrinkB': 5
            },
            zorder=5
        )

    ax.axvline(
        BESSENT_DATE,
        color='#b03a2e',
        linestyle='--',
        linewidth=1.2,
        alpha=0.85,
        zorder=2
    )

    ax.set_xlim(x_min, x_max)
    ax.set_ylim(0.45, 5.9)

    ax.set_yticks([y_map[lane] for lane in lanes])
    ax.set_yticklabels(lanes, fontsize=10.5)

    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

    ax.set_title(
        'Pre-event threshold sequence in the UAE dollar balance sheet',
        loc='left',
        fontsize=15,
        fontweight='bold',
        pad=16
    )

    ax.text(
        0.0,
        1.02,
        'Reserve mix shifts, liquidity cover weakens, the BIS dollar layer remains large, and BTAR crosses one before the public policy signal.',
        transform=ax.transAxes,
        fontsize=9.5,
        color='#4a4a4a',
        ha='left',
        va='bottom'
    )

    ax.set_xlabel('')
    ax.set_ylabel('')

    ax.text(
        0.0,
        -0.18,
        (
            'Source: author calculations from CBUAE, CEIC, BIS LBS, TIC, and BTAR scenario table. '
            'Thresholds are accounting and liquidity markers, not causal proof.'
        ),
        transform=ax.transAxes,
        fontsize=8,
        color='#555555',
        ha='left',
        va='top'
    )

    ax.grid(axis='x', alpha=0.18)
    ax.grid(axis='y', visible=False)

    for spine in ['top', 'right', 'left']:
        ax.spines[spine].set_visible(False)

    ax.spines['bottom'].set_color('#999999')
    ax.tick_params(axis='y', length=0)
    ax.tick_params(axis='x', labelsize=9)

    plt.tight_layout()

    out_png = OUT_PLOTS / 'fig05_pre_event_threshold_sequence.png'
    out_pdf = OUT_PLOTS / 'fig05_pre_event_threshold_sequence.pdf'
    legacy_out = OUT_PLOTS / 'phase2_pre_event_timeline.png'

    plt.savefig(out_png, bbox_inches='tight', dpi=300)
    plt.savefig(out_pdf, bbox_inches='tight')
    plt.savefig(legacy_out, bbox_inches='tight', dpi=300)
    plt.close()

    print(f"    Saved publication figure: {out_png}")
    print(f"    Saved publication figure: {out_pdf}")
    print(f"    Saved legacy-compatible timeline path: {legacy_out}")

    return sequence_df


# =============================================================================
# 5. SUMMARY REPORT
# =============================================================================
def write_phase2_report(break_results, anom_df, lead_lag_df, timeline_df, phase1_threshold_df=None):
    lines = [
        "# Phase 2 — Pre-Event Break Identification",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Data cutoff: {DATA_CUTOFF.strftime('%Y-%m-%d')} (pre-Bessent signal)",
        "",
        "## Research question",
        "What pre-existing balance-sheet and market conditions preceded the April 22, 2026 Bessent UAE swap line signal?",
        "",
        "## Methodological note",
        "",
        "Phase 2 is a timing and diagnostic layer. It is not a causal event study. The core evidence comes from Phase 1: CBUAE reserve composition, CLC, BIS dollar-routing, TIC visibility, BTAR, and OFR repo-channel context.",
        "",
        "The main Phase 2 object is the sequence of data-driven Phase 1 accounting and liquidity threshold breaks. Legacy structural-break, anomaly, and lead-lag diagnostics are retained as supporting public-market context.",
        "",
        "## 1. Phase 1 Threshold Breaks",
        "",
        "These are accounting and liquidity threshold breaks derived from fixed Phase 1 output CSVs. They are the primary Phase 2 timing evidence.",
        "",
    ]

    if phase1_threshold_df is not None and len(phase1_threshold_df) > 0:
        tmp_thresholds = phase1_threshold_df.copy()
        tmp_thresholds['date'] = pd.to_datetime(tmp_thresholds['date'])
        tmp_thresholds = tmp_thresholds.sort_values('date')

        lines += [
            "| Date | Event | Metric | Threshold | Value | Interpretation |",
            "|---|---|---|---|---:|---|",
        ]

        for _, row in tmp_thresholds.iterrows():
            value = row.get('value')
            if isinstance(value, float):
                if abs(value) < 10:
                    value_str = f"{value:,.3f}"
                else:
                    value_str = f"{value:,.1f}"
            else:
                value_str = str(value)

            lines.append(
                f"| {pd.to_datetime(row.get('date')).strftime('%Y-%m-%d')} | "
                f"{row.get('event')} | "
                f"{row.get('metric')} | "
                f"{row.get('threshold')} | "
                f"{value_str} | "
                f"{row.get('interpretation')} |"
            )
    else:
        lines.append("Phase 1 threshold-break table was not available.")

    lines += [
        "",
        "## 2. Legacy Structural Break Dates",
        "",
        "These model-fitted structural breaks are retained as public-data diagnostics. They do not replace the Phase 1 threshold-break sequence.",
        "",
        "Only break dates are shown here. Segment statistics and percentage changes are saved in `structural_breaks.json`; they are not shown in the main report because percentage changes can become unstable when segment means are near zero.",
        "",
        "| Series | # breaks | Break dates |",
        "|---|---:|---|",
    ]

    for name, r in break_results.items():
        if 'break_dates' not in r:
            continue

        breaks = ', '.join(r['break_dates']) if r['break_dates'] else 'none'

        lines.append(
            f"| {r['series']} | {r.get('n_breaks', 0)} | {breaks} |"
        )

    lines += [
        "",
        "## 3. Top Treasury Holdings Anomalies (|z| > 2)",
        "",
        "| Country | Date | Δ (USD bn) | z-score |",
        "|---|---|---|---|",
    ]
    for _, row in anom_df.head(15).iterrows():
        lines.append(f"| {row['country']} | {row['date']} | {row['mom_change_bn']:.0f} | {row['z_score']:.2f} |")

    lines += [
        "",
        "## 4. Lead-Lag Cross-Correlations (UAE flows vs US custodial flows)",
        "",
        "| UAE series | US country | peak corr | peak lag | interpretation |",
        "|---|---|---|---|---|",
    ]
    for _, row in lead_lag_df.head(15).iterrows():
        lines.append(f"| {row['uae_series']} | {row['us_country']} | "
                     f"{row['peak_corr']:.3f} | {row['peak_lag_months']} | "
                     f"{row['interpretation']} |")


    lines += [
        "",
        "## 5. Timeline Synthesis",
        "",
        "The unified timeline is the main Phase 2 object. It combines:",
        "",
        "- Phase 1 reserve-composition events.",
        "- Phase 1 CLC liquidity-cliff events.",
        "- Phase 1 BIS routing and BTAR events.",
        "- Public-market diagnostics from structural breaks, anomaly detection, and lead-lag checks.",
        "- Policy and market anchors such as the Fed pivot, SOFR stress marker, and Bessent signal.",
        "",
        "VAR and Granger tests are intentionally excluded. The fixed Phase 1 stress variables are short, mixed-frequency, and partly reconstructed. A VAR on old monthly UAE FX-reserve changes and public custody proxies is not a defensible test of the Phase 1 thesis.",
    ]

    lines += [
        "",
        "## 6. Interpretation Guide",
        "",
        "**How to read the results:**",
        "",
        "- Phase 2 is a timing and diagnostic layer. It is not the core proof of the UAE swap-line thesis.",
        "",
        "- The core evidence is Phase 1: CBUAE reserve composition, CLC, BIS dollar-routing, TIC visibility, BTAR, and OFR repo-channel context.",
        "",
        "- A structural break in UAE portfolio investment in 2023-2024 identifies when UAE-side external deployment behavior changed. It supports the portfolio-breakout claim, but it does not by itself locate the destination of the funds.",
        "",
        "- A later break in SOFR-EFFR spread or foreign Treasury MoM changes is timing-consistent with stress appearing in U.S.-side plumbing. Phase 2 alone cannot attribute that stress to UAE behavior.",
        "",
        "- Weak lead-lag results should not be read as falsifying the Phase 1 thesis. They mainly show that simple public UAE FX-reserve changes do not map cleanly into public TIC custody-country movements.",
        "",
        "- The timeline chart is now the main Phase 2 object. It orders Phase 1 balance-sheet events, CLC cliff events, BIS routing events, public-market diagnostics, and policy anchors to test whether the sequence is coherent.",
        "",
        "## 7. Output files",
        "",
        f"- Breaks: {STATS_DIR / 'structural_breaks.json'}",
        f"- Phase 1 threshold breaks: {STATS_DIR / 'phase1_threshold_breaks.csv'}",
        f"- Anomalies: {STATS_DIR / 'treasury_anomalies.csv'}",
        f"- Lead-lag: {STATS_DIR / 'lead_lag_correlations.csv'}",
        f"- Timeline: {STATS_DIR / 'timeline_events.csv'}",
        f"- Timeline plot: {OUT_PLOTS / 'phase2_pre_event_timeline.png'}",
        f"- Anomaly plot: {OUT_PLOTS / 'phase2_anomaly_detection.png'}",
    ]

    out = OUT_REPORTS / 'phase2_summary.md'
    out.write_text('\n'.join(lines))
    print(f"\n  Saved summary: {out}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 70)
    print("UAE Swap Line Analysis — Phase 2: Pre-Event Break Identification")
    print(f"Data cutoff: {DATA_CUTOFF.strftime('%Y-%m-%d')}")
    print("=" * 70)

    print("\n[1] Mount Drive and ensure packages...")
    mount_drive()
    ensure_packages()

    print("\n[2] Loading data...")
    master = load_master()
    te_us = load_te_us()
    phase1_outputs = load_phase1_outputs()
    print(f"  UAE master: {len(master)} rows ({master['series'].nunique()} series)")
    print(f"  TE US: {len(te_us)} rows")
    print(f"  Phase 1 outputs loaded: {sum(v is not None for v in phase1_outputs.values())} / {len(phase1_outputs)}")

    print("\n[3] Creating Phase 1 threshold breaks...")
    phase1_threshold_df = create_phase1_threshold_breaks(phase1_outputs)

    print("\n[4] Running structural break tests...")
    break_results = run_break_tests(master, te_us)

    print("\n[5] Rolling anomaly detection...")
    countries = ['UK', 'Belgium', 'Canada', 'Japan', 'China', 'Aggregate']
    anomaly_results, anom_df = rolling_anomaly_detection(te_us, countries)
    plot_anomalies(anomaly_results)

    print("\n[6] Lead-lag cross-correlation...")
    lead_lag_df = lead_lag_analysis(master, te_us)

    print("\n[7] Publication threshold sequence figure...")
    timeline_df = build_timeline_chart(
        break_results,
        anom_df,
        phase1_outputs,
        phase1_threshold_df
    )

    print("\n[8] Writing summary report...")
    write_phase2_report(break_results, anom_df, lead_lag_df, timeline_df, phase1_threshold_df)

    print("\n" + "=" * 70)
    print("PHASE 2 COMPLETE")
    print(f"All outputs in: {OUT_DIR}")
    print("=" * 70)


if __name__ == '__main__':
    main()

# =============================================================================
# UAE Swap Line Analysis — Phase 2.5: SWF Context & Governance Module
# =============================================================================
#
# Augments Phase 2 outputs with:
#   1. Structured SWF fact table (AUM, governance, key relationships)
#   2. Governance network mapping (common control nodes)
#   3. Updated pre-event timeline with SWF events
#   4. Integrated exposure section in summary report
#
# Non-destructive: reads Phase 2 outputs, writes additional files.
# Run as Cell 3 of Colab notebook, after Phase 2.
# =============================================================================

import json
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches

BASE = Path('/content/drive/MyDrive/StockElephant/uae_swap_line_analysis')
OUT_DIR = BASE / 'outputs'
OUT_CSV = OUT_DIR / 'csv'
OUT_PLOTS = OUT_DIR / 'plots'
OUT_REPORTS = OUT_DIR / 'reports'
STATS_DIR = OUT_DIR / 'stats'

DATA_CUTOFF = pd.Timestamp('2026-04-20')
BESSENT_DATE = pd.Timestamp('2026-04-22')

plt.style.use('seaborn-v0_8-whitegrid')
plt.rcParams['figure.dpi'] = 110
plt.rcParams['savefig.dpi'] = 150


# =============================================================================
# 1. SWF FACT TABLE
# =============================================================================

def build_swf_facts():
    """
    Structured table of UAE sovereign investment entities with AUM,
    governance, and key external relationships as of April 2026.

    Important:
      - ADQ pre-merger is retained for historical context.
      - ADQ pre-merger is excluded from current headline AUM because it is
        already represented inside L'IMAD after absorption.
    """
    facts = [
        {
            'entity': 'ADIA',
            'full_name': 'Abu Dhabi Investment Authority',
            'aum_usd_bn': 1100,
            'include_current_total': True,
            'type': 'sovereign_wealth_fund',
            'founded': 1976,
            'chairman': 'Sheikh Tahnoon bin Zayed Al Nahyan',
            'ceo': 'Hamed bin Zayed Al Nahyan',
            'primary_mandate': 'Global diversified asset management',
            'alternatives_share_pct': 32,
            'estimated_usd_denominated_share': 0.65,
            'key_external_relationships': 'Numerous global external managers; deep Western exposure',
            'notes': 'Largest UAE sovereign pool. Current headline AUM included.',
        },
        {
            'entity': 'Mubadala',
            'full_name': 'Mubadala Investment Company',
            'aum_usd_bn': 327,
            'include_current_total': True,
            'type': 'sovereign_wealth_fund',
            'founded': 2002,
            'chairman': 'Sheikh Mohammed bin Zayed Al Nahyan',
            'ceo': 'Khaldoon Al Mubarak',
            'primary_mandate': 'Strategic investment, direct and co-investment',
            'alternatives_share_pct': 60,
            'estimated_usd_denominated_share': 0.70,
            'key_external_relationships': 'Active direct and co-investment platform; AI, technology, and advanced manufacturing focus',
            'notes': 'Current headline AUM included. Includes ADIC subsidiary.',
        },
        {
            'entity': "L'IMAD",
            'full_name': "L'imad Holding Company",
            'aum_usd_bn': 300,
            'include_current_total': True,
            'type': 'sovereign_wealth_fund',
            'founded': 2025,
            'chairman': 'Sheikh Khaled bin Mohamed bin Zayed Al Nahyan',
            'ceo': 'Jassem Al-Zaabi',
            'primary_mandate': 'Sovereign investment holding and strategic development platform',
            'alternatives_share_pct': None,
            'estimated_usd_denominated_share': 0.55,
            'key_external_relationships': 'ADQ assets plus new strategic investment direction',
            'notes': "Current headline AUM included. ADQ pre-merger assets are treated as represented here after absorption.",
        },
        {
            'entity': 'ADQ (pre-merger)',
            'full_name': 'Abu Dhabi Developmental Holding Company',
            'aum_usd_bn': 263,
            'include_current_total': False,
            'type': 'historical_context',
            'founded': 2018,
            'chairman': 'Sheikh Tahnoon bin Zayed Al Nahyan until Jan 30, 2026',
            'ceo': 'Mohamed Hassan Alsuwaidi until Jan 29, 2026',
            'primary_mandate': 'National strategic development before absorption into L\'IMAD',
            'alternatives_share_pct': None,
            'estimated_usd_denominated_share': 0.45,
            'key_external_relationships': 'Egypt, Turkey, Vietnam partnerships; Etihad; Emirates Nuclear Energy',
            'notes': "Historical context only. Excluded from current headline AUM to avoid double-counting with L'IMAD.",
        },
        {
            'entity': 'Lunate',
            'full_name': 'Lunate',
            'aum_usd_bn': 115,
            'include_current_total': True,
            'type': 'alternative_asset_manager',
            'founded': 2023,
            'chairman': 'Mohamed Hassan Alsuwaidi',
            'ceo': 'Various',
            'primary_mandate': 'Alternative asset management and private markets',
            'alternatives_share_pct': 100,
            'estimated_usd_denominated_share': 0.80,
            'key_external_relationships': 'Minority stake in Brevan Howard; partnerships with global private-market managers',
            'notes': 'Current headline AUM included. Lunate-Brevan is a relationship channel, not quantified basis-trade attribution.',
        },
        {
            'entity': 'Chimera',
            'full_name': 'Chimera Investment LLC',
            'aum_usd_bn': None,
            'include_current_total': False,
            'type': 'holding_company',
            'founded': 2010,
            'chairman': 'Sheikh Tahnoon bin Zayed Al Nahyan',
            'ceo': 'Syed Basar Shueb',
            'primary_mandate': 'Strategic holdings and investments',
            'alternatives_share_pct': None,
            'estimated_usd_denominated_share': None,
            'key_external_relationships': 'Majority owner of Lunate; linked to IHC ecosystem',
            'notes': 'Governance/context vehicle. AUM not included because disclosed AUM is not available here.',
        },
        {
            'entity': 'MGX',
            'full_name': 'MGX Fund Management',
            'aum_usd_bn': 100,
            'include_current_total': True,
            'type': 'tech_investment_vehicle',
            'founded': 2024,
            'chairman': 'Sheikh Tahnoon bin Zayed Al Nahyan',
            'ceo': 'Ahmed Yahia Al Idrissi',
            'primary_mandate': 'AI and advanced technology investments',
            'alternatives_share_pct': 100,
            'estimated_usd_denominated_share': 0.90,
            'key_external_relationships': 'AI and advanced-compute investment ecosystem',
            'notes': 'Current headline AUM included.',
        },
        {
            'entity': 'IHC',
            'full_name': 'International Holding Company',
            'aum_usd_bn': None,
            'include_current_total': False,
            'type': 'listed_conglomerate',
            'founded': 1998,
            'chairman': 'Sheikh Tahnoon bin Zayed Al Nahyan',
            'ceo': 'Syed Basar Shueb',
            'primary_mandate': 'Diversified listed conglomerate',
            'alternatives_share_pct': None,
            'estimated_usd_denominated_share': None,
            'key_external_relationships': 'Large listed Abu Dhabi conglomerate',
            'notes': 'Governance/context vehicle. Market cap is not treated as SWF AUM.',
        },
    ]

    df = pd.DataFrame(facts)

    df['estimated_usd_exposure_bn'] = (
        df['aum_usd_bn'].fillna(0)
        * df['estimated_usd_denominated_share'].fillna(0)
    )

    out = STATS_DIR / 'swf_facts.csv'
    df.to_csv(out, index=False)

    current_total = df[df['include_current_total'] == True]['aum_usd_bn'].fillna(0).sum()

    print(f"  Saved SWF facts: {out}")
    print(f"  Current headline AUM excluding ADQ pre-merger double count: ${current_total:,.0f}B")

    return df

# =============================================================================
# 2. GOVERNANCE NETWORK MAPPING
# =============================================================================

def build_governance_edges():
    """
    Directed edges: control/chairmanship relationships across UAE sovereign network.
    Each edge: (controller, entity, relationship_type, since_date).
    """
    edges = [
        # Sheikh Tahnoon network (dominant)
        ('Sheikh Tahnoon bin Zayed', 'ADIA', 'chairman', '2023-03-01'),
        ('Sheikh Tahnoon bin Zayed', 'Chimera', 'chairman', None),
        ('Sheikh Tahnoon bin Zayed', 'IHC', 'chairman', None),
        ('Sheikh Tahnoon bin Zayed', 'MGX', 'chairman', '2024-01-01'),
        ('Sheikh Tahnoon bin Zayed', 'G42', 'chairman', None),
        ('Chimera', 'Lunate', 'majority_owner', '2023-01-01'),

        # Sheikh Khaled network (rising)
        ('Sheikh Khaled bin Mohamed', 'L\'IMAD', 'chairman', '2026-01-01'),

        # Sheikh Mohammed bin Zayed (President)
        ('Sheikh Mohammed bin Zayed', 'Mubadala', 'chairman', None),

        # SCFEA oversight
        ('SCFEA', 'ADIA', 'oversight', None),
        ('SCFEA', 'Mubadala', 'oversight', None),
        ('SCFEA', 'L\'IMAD', 'oversight', None),
        ('SCFEA', 'ADNOC', 'oversight', None),

        # Lunate external relationships (investment exposures)
        ('Lunate', 'Brevan Howard', 'minority_stake', '2024-01-01'),
        ('Lunate', 'Brookfield_platform', 'partnership', '2023-06-01'),
        ('Lunate', 'BlueOwl_platform', 'partnership', '2023-06-01'),
        ('Lunate', 'OpenAI', 'equity_stake', '2024-01-01'),
        ('Lunate', 'CoreWeave', 'equity_stake', '2024-06-01'),

        # L'IMAD ecosystem
        ('L\'IMAD', 'ADQ_assets', 'absorbed', '2026-01-30'),
        ('L\'IMAD', 'Paramount_Skydance', 'participant', '2026-01-01'),

        # Key individual appointments
        ('Mohamed Alsuwaidi', 'Lunate', 'executive_chairman', '2026-01-29'),
        ('Mohamed Alsuwaidi', 'ADQ_CEO', 'ceo_until', '2026-01-29'),
        ('Jassem Al-Zaabi', 'L\'IMAD', 'ceo', '2026-01-30'),
        ('Jassem Al-Zaabi', 'UAE Central Bank', 'vice_chairman', None),
    ]
    df = pd.DataFrame(edges, columns=['from', 'to', 'relationship', 'since'])
    df.to_csv(STATS_DIR / 'swf_governance_edges.csv', index=False)
    print(f"  Saved governance edges: {STATS_DIR / 'swf_governance_edges.csv'}")
    return df


# =============================================================================
# 3. SWF EVENTS TO ADD TO TIMELINE
# =============================================================================

def swf_events():
    """SWF-related dated events to overlay on pre-event timeline."""
    events = [
        {
            'date': pd.Timestamp('2023-01-01'),
            'series': 'SWF_structure',
            'type': 'swf_formation',
            'description': 'Lunate founded ($115B alternative asset manager, Chimera majority)',
        },
        {
            'date': pd.Timestamp('2024-01-01'),
            'series': 'SWF_exposure',
            'type': 'swf_exposure',
            'description': 'Lunate takes minority stake in Brevan Howard',
        },
        {
            'date': pd.Timestamp('2024-01-01'),
            'series': 'SWF_exposure',
            'type': 'swf_exposure',
            'description': 'Lunate invests in OpenAI',
        },
        {
            'date': pd.Timestamp('2024-01-01'),
            'series': 'SWF_structure',
            'type': 'swf_formation',
            'description': 'MGX established under Sheikh Tahnoon',
        },
        {
            'date': pd.Timestamp('2025-06-01'),
            'series': 'SWF_structure',
            'type': 'swf_formation',
            'description': 'L\'IMAD launched (initial real estate and strategic assets)',
        },
        {
            'date': pd.Timestamp('2026-01-29'),
            'series': 'SWF_governance',
            'type': 'governance_change',
            'description': 'Alsuwaidi moves from ADQ CEO to Lunate executive chairman',
        },
        {
            'date': pd.Timestamp('2026-01-30'),
            'series': 'SWF_governance',
            'type': 'governance_change',
            'description': 'L\'IMAD absorbs $263B ADQ; Crown Prince Sheikh Khaled direct chair',
        },
    ]
    df = pd.DataFrame(events)
    df = df[df['date'] <= DATA_CUTOFF]
    return df


# =============================================================================
# 4. UPDATED TIMELINE CHART WITH SWF OVERLAY
# =============================================================================
def build_augmented_timeline():
    """
    Read Phase 2 timeline CSV, augment with SWF events, and re-plot.

    This chart is contextual. SWF governance events are not treated as causal
    proof of market stress. They are overlaid as institutional context.
    """
    print("\n  Building augmented pre-event timeline with SWF overlay...")

    phase2_timeline_file = STATS_DIR / 'timeline_events.csv'

    if not phase2_timeline_file.exists():
        print(f"  WARNING: Phase 2 timeline not found at {phase2_timeline_file}")
        print("  Using SWF events only.")
        phase2_events = pd.DataFrame(columns=['date', 'series', 'type', 'description'])
    else:
        phase2_events = pd.read_csv(phase2_timeline_file, parse_dates=['date'])

    swf_df = swf_events()

    combined = pd.concat([phase2_events, swf_df], ignore_index=True)
    combined['date'] = pd.to_datetime(combined['date'])
    combined = combined[combined['date'] <= DATA_CUTOFF].copy()
    combined = combined.sort_values('date').reset_index(drop=True)

    combined.to_csv(STATS_DIR / 'timeline_events_augmented.csv', index=False)

    fig, ax = plt.subplots(figsize=(15, 10))

    if len(combined) == 0:
        ax.text(
            0.5,
            0.5,
            'No timeline events available',
            transform=ax.transAxes,
            ha='center',
            va='center'
        )
        out = OUT_PLOTS / 'phase25_augmented_timeline.png'
        plt.tight_layout()
        plt.savefig(out, bbox_inches='tight')
        plt.close()
        print(f"    Saved: {out}")
        return combined

    series_list = sorted(combined['series'].dropna().unique())
    y_map = {s: i for i, s in enumerate(series_list)}

    type_styling = {
        'structural_break': ('#E76F51', 'o', 100),
        'anomaly': ('#F4A261', 's', 90),
        'architecture_event': ('#264653', 'D', 110),
        'policy_event': ('#2A9D8F', 'P', 120),
        'market_event': ('#E9C46A', '^', 100),
        'publication': ('#9B5DE5', '*', 180),
        'phase1_balance_sheet_event': ('#006D77', 'X', 120),
        'phase1_liquidity_cliff_event': ('#D62828', 'v', 120),
        'phase1_routing_event': ('#3A86FF', 'h', 120),
        'phase1_absorption_event': ('#8338EC', '8', 120),
        'swf_formation': ('#F72585', 'h', 140),
        'swf_exposure': ('#7209B7', 'X', 120),
        'governance_change': ('#B5179E', 'v', 140),
    }

    for event_type in combined['type'].dropna().unique():
        sub = combined[combined['type'] == event_type]
        color, marker, size = type_styling.get(event_type, ('gray', 'o', 80))

        ax.scatter(
            sub['date'],
            [y_map[s] for s in sub['series']],
            c=color,
            marker=marker,
            s=size,
            label=event_type.replace('_', ' '),
            edgecolors='black',
            linewidth=0.5,
            zorder=3,
            alpha=0.85,
        )

    ax.axvline(BESSENT_DATE, color='red', linestyle='--', linewidth=1.5, alpha=0.7)

    ax.text(
        BESSENT_DATE,
        len(y_map) - 0.5,
        f'  Bessent signal\n  {BESSENT_DATE.strftime("%Y-%m-%d")}',
        color='red',
        fontsize=10,
        fontweight='bold',
        va='top',
    )

    governance_window_start = pd.Timestamp('2026-01-29')
    governance_window_end = pd.Timestamp('2026-01-30')

    ax.axvspan(
        governance_window_start,
        governance_window_end,
        alpha=0.12,
        color='purple'
    )

    ax.text(
        pd.Timestamp('2026-01-29 12:00'),
        -0.5,
        'UAE SWF governance\nwindow',
        fontsize=8,
        color='#6A0572',
        ha='center',
        fontweight='bold'
    )

    ax.set_yticks(range(len(series_list)))
    ax.set_yticklabels(series_list, fontsize=9)
    ax.set_xlabel('Date')

    ax.set_title(
        'Pre-event timeline with SWF governance overlay\n'
        'Phase 1 stress events, public diagnostics, policy anchors, and SWF context',
        fontsize=12,
        loc='left',
        pad=12,
    )

    ax.legend(loc='upper left', frameon=False, fontsize=8, ncol=2)
    ax.grid(True, alpha=0.3)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    plt.figtext(
        0.01,
        0.01,
        f'Data cutoff: {DATA_CUTOFF.strftime("%Y-%m-%d")} | '
        'SWF events are contextual governance markers, not attribution proof.',
        fontsize=8,
        color='gray',
    )

    plt.tight_layout()

    out = OUT_PLOTS / 'phase25_augmented_timeline.png'
    plt.savefig(out, bbox_inches='tight')
    plt.close()

    print(f"    Saved: {out}")
    return combined

# =============================================================================
# 5. INTEGRATED EXPOSURE REPORT
# =============================================================================
def write_swf_report(facts_df, governance_df, augmented_timeline):
    print("\n  Writing integrated exposure report...")

    facts = facts_df.copy()

    if 'include_current_total' not in facts.columns:
        facts['include_current_total'] = facts['entity'].ne('ADQ (pre-merger)')

    current_facts = facts[facts['include_current_total'] == True].copy()

    total_aum = current_facts[
        current_facts['type'].isin([
            'sovereign_wealth_fund',
            'alternative_asset_manager',
            'tech_investment_vehicle',
        ])
    ]['aum_usd_bn'].fillna(0).sum()

    total_usd_exposure = current_facts['estimated_usd_exposure_bn'].fillna(0).sum()

    cbuae_gross_reserves_bn = np.nan
    cbuae_cash_bn = np.nan
    cbuae_foreign_inv_bn = np.nan

    cbuae_path = OUT_CSV / 'cbuae_reserve_composition.csv'
    if cbuae_path.exists():
        cbuae = pd.read_csv(cbuae_path)
        cbuae['date'] = pd.to_datetime(cbuae['date'])
        cbuae = cbuae.sort_values('date')
        if len(cbuae) > 0:
            latest_cb = cbuae.iloc[-1]
            cbuae_gross_reserves_bn = float(latest_cb.get('gross_reserves_bn', np.nan))
            cbuae_cash_bn = float(latest_cb.get('cash_deposits_abroad_bn', np.nan))
            cbuae_foreign_inv_bn = float(latest_cb.get('foreign_investments_bn', np.nan))

    reserve_denominator = cbuae_gross_reserves_bn if pd.notna(cbuae_gross_reserves_bn) else 244.0
    reserve_ratio = total_aum / reserve_denominator if reserve_denominator else np.nan

    def fmt_bn(x):
        if pd.isna(x):
            return 'n/a'
        return f'${x:,.0f}B'

    def fmt_ratio(x):
        if pd.isna(x):
            return 'n/a'
        return f'{x:,.1f}x'

    lines = [
        '# Phase 2.5 - UAE Sovereign Investment Network and Exposure Context',
        f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}',
        '',
        '## Scope and caveat',
        '',
        'Phase 2.5 is a context module. It maps UAE sovereign investment entities, governance links, and plausible exposure channels. It does not prove basis-trade exposure, forced selling, legal cross-guarantees, or balance-sheet transmission between entities.',
        '',
        'The purpose is to show why the UAE dollar ecosystem is larger than CBUAE reserves alone and why external-manager, hedge-fund, and sovereign investment channels remain relevant to the swap-line question.',
        '',
        '## Headline numbers',
        '',
        f'- **Current UAE sovereign / quasi-sovereign AUM included in this module:** ~{fmt_bn(total_aum)}',
        f'- **Estimated USD-denominated exposure across included current entities:** ~{fmt_bn(total_usd_exposure)}',
        f'- **CBUAE gross reserves:** ~{fmt_bn(cbuae_gross_reserves_bn)}',
        f'- **CBUAE cash/deposits abroad:** ~{fmt_bn(cbuae_cash_bn)}',
        f'- **CBUAE foreign investments:** ~{fmt_bn(cbuae_foreign_inv_bn)}',
        f'- **Current included AUM / CBUAE gross reserves:** ~{fmt_ratio(reserve_ratio)}',
        '',
        'ADQ pre-merger is retained in the entity table for historical context but excluded from current headline AUM because those assets are treated as represented inside L\'IMAD after absorption. This avoids double-counting.',
        '',
        '## Entity table',
        '',
        '| Entity | Current headline AUM included? | Type | AUM | Chairman | Est. USD share | Est. USD exposure | Notes |',
        '|---|---:|---|---:|---|---:|---:|---|',
    ]

    for _, r in facts.iterrows():
        included = 'yes' if bool(r.get('include_current_total')) else 'no'
        aum = fmt_bn(r['aum_usd_bn']) if pd.notna(r['aum_usd_bn']) else '-'
        share = f"{r['estimated_usd_denominated_share']:.0%}" if pd.notna(r['estimated_usd_denominated_share']) else '-'
        expo = fmt_bn(r['estimated_usd_exposure_bn']) if pd.notna(r['estimated_usd_exposure_bn']) else '-'

        lines.append(
            f"| {r['entity']} | {included} | {r['type']} | {aum} | "
            f"{r['chairman']} | {share} | {expo} | {r['notes']} |"
        )

    tahnoon_direct = facts[
        (facts['include_current_total'] == True)
        & facts['chairman'].astype(str).str.contains('Tahnoon', na=False)
    ].copy()

    lunate = facts[facts['entity'] == 'Lunate'].copy()

    tahnoon_context_aum = tahnoon_direct['aum_usd_bn'].fillna(0).sum()
    if len(lunate) > 0:
        tahnoon_context_aum += lunate['aum_usd_bn'].fillna(0).sum()

    lines += [
        '',
        '## Governance network interpretation',
        '',
        f'**Sheikh Tahnoon bin Zayed** appears as a common governance node across ADIA, Chimera, IHC, MGX, G42, and indirectly Lunate through Chimera.',
        '',
        f'**AUM-reporting entities in the Tahnoon governance context:** ~{fmt_bn(tahnoon_context_aum)}',
        '',
        'This should be interpreted as governance and coordination context, not legal balance-sheet consolidation. Common governance may imply shared risk awareness, faster coordination, and correlated liquidity-management decisions. It does not prove that stress in one entity legally transmits to another entity.',
        '',
        '## Lunate-Brevan channel',
        '',
        'Lunate has a publicly identified relationship channel to Brevan Howard through a minority stake. This matters because Brevan Howard is a major macro hedge-fund platform and hedge-fund channels can be connected to Treasury/repo strategies.',
        '',
        'The disciplined interpretation is:',
        '',
        '1. The Lunate-Brevan relationship makes hedge-fund exposure a concrete relationship channel rather than a purely hypothetical channel.',
        '2. The public data do not quantify Lunate capital calls, Brevan basis-trade exposure attributable to Lunate, or losses from any specific trade.',
        '3. Therefore, the relationship supports channel plausibility, not exposure attribution.',
        '',
        '## January 2026 governance timing',
        '',
        'The relevant dates are:',
        '',
        '- **Jan 21, 2026:** Fed balance-sheet stress-window expansion begins in the Phase 1 BTAR denominator.',
        '- **Jan 29, 2026:** Mohamed Alsuwaidi moves from ADQ leadership context to Lunate executive-chairman role in this module.',
        '- **Jan 30, 2026:** ADQ assets are absorbed into L\'IMAD under Crown Prince Sheikh Khaled in this module.',
        '- **Apr 22, 2026:** Bessent swap-line signal.',
        '',
        'Jan 30 is nine days after Jan 21, not before it. The governance event should therefore be read as part of the broader pre-signal window, not as a dated precursor to the Fed pivot.',
        '',
        'Two conservative interpretations are possible:',
        '',
        '- **Governance-context interpretation:** Abu Dhabi was consolidating and reorganizing major sovereign investment functions during the same period that the public data show worsening CBUAE reserve composition and import-liquidity CLC.',
        '- **Common-environment interpretation:** UAE governance changes, Fed balance-sheet expansion, repo stress markers, and the later Bessent signal may all reflect the same broader dollar-liquidity environment without requiring direct causation between any pair of events.',
        '',
        'This module does not claim that the governance shift caused the Fed pivot, the SOFR marker, or the Bessent signal.',
        '',
        '## Updated channel framework',
        '',
        'Channel 7, externally managed sovereign accounts, should be disaggregated in later work:',
        '',
        '- **Channel 7a: ADIA external allocations.** Large global public and private-market external-manager footprint.',
        '- **Channel 7b: Mubadala direct and co-investments.** Strategic and private-market dollar exposure.',
        '- **Channel 7c: L\'IMAD / ADQ international exposure.** Post-consolidation sovereign development and international investment channel.',
        '- **Channel 7d: Lunate.** Alternative-asset manager with a concrete hedge-fund relationship channel.',
        '',
        'Channel 5, hedge-fund LP and ownership channels, is no longer purely hypothetical as a relationship category because the Lunate-Brevan relationship exists in the module. The size, instrument exposure, leverage, margin sensitivity, and stress transmission remain unobserved.',
        '',
        '## Why the U.S. should care',
        '',
        'The U.S. policy relevance does not require proving that UAE entities directly ran a basis trade. The relevant question is whether a large sovereign-linked dollar ecosystem could become a source of forced dollar-asset liquidation or repo/collateral stress during a liquidity event.',
        '',
        'Phase 1 already shows the core mechanism:',
        '',
        '- CBUAE cash/deposits became thin relative to gross reserves and import-liquidity needs.',
        '- CBUAE foreign investments became the dominant reserve component.',
        '- BIS global USD liabilities to UAE were large.',
        '- Low-scenario BTAR exceeded one for the BIS dollar-liability bucket.',
        '',
        'Phase 2.5 adds context: UAE sovereign investment entities and external-manager relationships are large enough that even small encumbered or liquidity-sensitive shares can matter in a stressed Treasury/repo environment.',
        '',
        '## Output files',
        '',
        f'- SWF facts: {STATS_DIR / "swf_facts.csv"}',
        f'- Governance edges: {STATS_DIR / "swf_governance_edges.csv"}',
        f'- Augmented timeline: {STATS_DIR / "timeline_events_augmented.csv"}',
        f'- Augmented timeline plot: {OUT_PLOTS / "phase25_augmented_timeline.png"}',
    ]

    out = OUT_REPORTS / 'phase25_swf_report.md'
    out.write_text('\n'.join(lines))

    print(f"    Saved: {out}")

# =============================================================================
# MAIN
# =============================================================================
def main():
    print("=" * 70)
    print("Phase 2.5 - SWF Context and Governance Module")
    print("=" * 70)

    try:
        from google.colab import drive
        drive.mount('/content/drive')
    except ImportError:
        pass

    print("\n[1] Building SWF facts table...")
    facts_df = build_swf_facts()
    print(f"    {len(facts_df)} entities")

    current_aum = facts_df[
        facts_df.get('include_current_total', False) == True
    ]['aum_usd_bn'].fillna(0).sum()

    print(f"    Current headline AUM excluding ADQ pre-merger double count: ${current_aum:,.0f}B")

    print("\n[2] Building governance edges...")
    gov_df = build_governance_edges()
    print(f"    {len(gov_df)} edges")

    print("\n[3] Building augmented timeline...")
    timeline_df = build_augmented_timeline()
    print(f"    {len(timeline_df)} total events")

    print("\n[4] Writing integrated exposure report...")
    write_swf_report(facts_df, gov_df, timeline_df)

    print("\n" + "=" * 70)
    print("PHASE 2.5 COMPLETE")
    print(f"Outputs in: {OUT_DIR}")
    print("=" * 70)


if __name__ == '__main__':
    main()
# === Publishable UAE import-liquidity CLC plot ===

from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# ------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------
BASE = Path('/content/drive/MyDrive/StockElephant/uae_swap_line_analysis/outputs')
IN_CSV = BASE / 'csv' / 'uae_import_liquidity_clc.csv'
OUT_PNG = BASE / 'plots' / 'uae_import_liquidity_clc.png'

if not IN_CSV.exists():
    raise FileNotFoundError(f"Missing input CSV: {IN_CSV}")

df = pd.read_csv(IN_CSV)

# ------------------------------------------------------------------
# Basic cleaning
# ------------------------------------------------------------------
if 'date' not in df.columns:
    raise RuntimeError(f"'date' column not found. Columns are: {list(df.columns)}")

df['date'] = pd.to_datetime(df['date'], errors='coerce')
df = df.dropna(subset=['date']).sort_values('date').copy()

# ------------------------------------------------------------------
# Robust column detection
# ------------------------------------------------------------------
def find_col(candidates, contains_all=None):
    lower_map = {c.lower(): c for c in df.columns}

    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]

    if contains_all is not None:
        for c in df.columns:
            cl = c.lower()
            if all(token in cl for token in contains_all):
                return c

    return None

clc_3m_col = find_col(
    candidates=[
        'clc_3m',
        'clc_3_month',
        'clc_3m_imports',
        'import_clc_3m',
        'liquidity_cliff_3m',
        'clc_three_month'
    ],
    contains_all=['clc', '3']
)

clc_6m_col = find_col(
    candidates=[
        'clc_6m',
        'clc_6_month',
        'clc_6m_imports',
        'import_clc_6m',
        'liquidity_cliff_6m',
        'clc_six_month'
    ],
    contains_all=['clc', '6']
)

if clc_3m_col is None and clc_6m_col is None:
    raise RuntimeError(
        "Could not identify 3-month or 6-month CLC columns. "
        f"Available columns: {list(df.columns)}"
    )

for col in [clc_3m_col, clc_6m_col]:
    if col is not None:
        df[col] = pd.to_numeric(df[col], errors='coerce')

plot_cols = [c for c in [clc_3m_col, clc_6m_col] if c is not None]
plot_df = df[['date'] + plot_cols].dropna(how='all', subset=plot_cols).copy()

if plot_df.empty:
    raise RuntimeError("CLC series are empty after cleaning.")

# ------------------------------------------------------------------
# Helper: first threshold-crossing below 1
# ------------------------------------------------------------------
def first_cross_below_one(series_df, value_col):
    s = series_df[['date', value_col]].dropna().copy()
    if s.empty or len(s) < 2:
        return None
    s['prev'] = s[value_col].shift(1)
    hit = s[(s['prev'] >= 1.0) & (s[value_col] < 1.0)]
    if hit.empty:
        return None
    row = hit.iloc[0]
    return row['date'], float(row[value_col])

# ------------------------------------------------------------------
# Figure
# ------------------------------------------------------------------
plt.close('all')
fig, ax = plt.subplots(figsize=(11.5, 6.5), dpi=220)

# y-range
y_vals = pd.concat([plot_df[c] for c in plot_cols], axis=0).dropna()
y_min = min(0.0, y_vals.min() - 0.10)
y_max = max(1.15, y_vals.max() + 0.12)

# danger zone below 1
ax.axhspan(y_min, 1.0, alpha=0.10, zorder=0)
ax.axhline(1.0, linestyle='--', linewidth=1.4, zorder=1, label='Threshold = 1.0')

# plot series
label_map = {}
if clc_3m_col is not None:
    label_map[clc_3m_col] = '3-month import liquidity cliff'
if clc_6m_col is not None:
    label_map[clc_6m_col] = '6-month import liquidity cliff'

style_map = {
    clc_3m_col: dict(linewidth=2.3, marker='o', markersize=5),
    clc_6m_col: dict(linewidth=2.3, marker='s', markersize=5),
}

for col in plot_cols:
    ax.plot(
        plot_df['date'],
        plot_df[col],
        label=label_map[col],
        **style_map[col]
    )

# ------------------------------------------------------------------
# Annotate first crossings
# ------------------------------------------------------------------
for col in plot_cols:
    cross = first_cross_below_one(plot_df, col)
    if cross is not None:
        x, y = cross
        ax.scatter([x], [y], s=55, zorder=5)
        ax.annotate(
            f"First < 1.0\n{pd.Timestamp(x).strftime('%Y-%m')} ({y:.2f})",
            xy=(x, y),
            xytext=(10, -28 if col == clc_3m_col else 18),
            textcoords='offset points',
            fontsize=9,
            bbox=dict(boxstyle='round,pad=0.25', fc='white', ec='0.5', alpha=0.95),
            arrowprops=dict(arrowstyle='-', lw=1.0)
        )

# ------------------------------------------------------------------
# Annotate latest values
# ------------------------------------------------------------------
for col in plot_cols:
    s = plot_df[['date', col]].dropna()
    if s.empty:
        continue
    x_last = s['date'].iloc[-1]
    y_last = float(s[col].iloc[-1])
    ax.scatter([x_last], [y_last], s=45, zorder=5)
    ax.annotate(
        f"{label_map[col]}: {y_last:.2f}",
        xy=(x_last, y_last),
        xytext=(8, 8 if col == clc_3m_col else -16),
        textcoords='offset points',
        fontsize=9,
        bbox=dict(boxstyle='round,pad=0.20', fc='white', ec='0.6', alpha=0.95)
    )

# ------------------------------------------------------------------
# Titles and formatting
# ------------------------------------------------------------------
ax.set_title(
    'UAE Central Bank Import Liquidity Cliff',
    fontsize=15,
    pad=14
)
ax.text(
    0.0, 1.01,
    'Cash and deposits abroad relative to estimated 3-month and 6-month import needs',
    transform=ax.transAxes,
    ha='left',
    va='bottom',
    fontsize=10
)

ax.set_ylabel('Coverage ratio')
ax.set_xlabel('Date')
ax.set_ylim(y_min, y_max)

# x-axis formatting
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
plt.setp(ax.get_xticklabels(), rotation=45, ha='right')

# grid
ax.grid(axis='y', alpha=0.25)
ax.grid(axis='x', alpha=0.10)

# legend placed cleanly above plot
ax.legend(
    loc='upper center',
    bbox_to_anchor=(0.5, -0.18),
    ncol=3,
    frameon=False,
    fontsize=10
)

# footnote
fig.text(
    0.01, 0.01,
    'Source: CBUAE reserve composition series and UAE macro series. '
    'Liquidity cliff is defined as liquid foreign cash/deposits divided by estimated import needs.',
    ha='left',
    va='bottom',
    fontsize=8
)

fig.tight_layout(rect=[0, 0.05, 1, 0.96])

OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT_PNG, dpi=300, bbox_inches='tight')
plt.show()

print(f"Saved: {OUT_PNG}")
print("\nColumns used:")
print(f"  3-month CLC: {clc_3m_col}")
print(f"  6-month CLC: {clc_6m_col}")
print("\nLatest data:")
display(plot_df.tail(10))

# === Publishable UAE import-liquidity CLC plot ===

from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# ------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------
BASE = Path('/content/drive/MyDrive/StockElephant/uae_swap_line_analysis/outputs')
IN_CSV = BASE / 'csv' / 'uae_import_liquidity_clc.csv'
OUT_PNG = BASE / 'plots' / 'uae_import_liquidity_clc.png'

if not IN_CSV.exists():
    raise FileNotFoundError(f"Missing input CSV: {IN_CSV}")

df = pd.read_csv(IN_CSV)

# ------------------------------------------------------------------
# Basic cleaning
# ------------------------------------------------------------------
if 'date' not in df.columns:
    raise RuntimeError(f"'date' column not found. Columns are: {list(df.columns)}")

df['date'] = pd.to_datetime(df['date'], errors='coerce')
df = df.dropna(subset=['date']).sort_values('date').copy()

# ------------------------------------------------------------------
# Robust column detection
# ------------------------------------------------------------------
def find_col(candidates, contains_all=None):
    lower_map = {c.lower(): c for c in df.columns}

    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]

    if contains_all is not None:
        for c in df.columns:
            cl = c.lower()
            if all(token in cl for token in contains_all):
                return c

    return None

clc_3m_col = find_col(
    candidates=[
        'clc_3m',
        'clc_3_month',
        'clc_3m_imports',
        'import_clc_3m',
        'liquidity_cliff_3m',
        'clc_three_month'
    ],
    contains_all=['clc', '3']
)

clc_6m_col = find_col(
    candidates=[
        'clc_6m',
        'clc_6_month',
        'clc_6m_imports',
        'import_clc_6m',
        'liquidity_cliff_6m',
        'clc_six_month'
    ],
    contains_all=['clc', '6']
)

if clc_3m_col is None and clc_6m_col is None:
    raise RuntimeError(
        "Could not identify 3-month or 6-month CLC columns. "
        f"Available columns: {list(df.columns)}"
    )

for col in [clc_3m_col, clc_6m_col]:
    if col is not None:
        df[col] = pd.to_numeric(df[col], errors='coerce')

plot_cols = [c for c in [clc_3m_col, clc_6m_col] if c is not None]
plot_df = df[['date'] + plot_cols].dropna(how='all', subset=plot_cols).copy()

if plot_df.empty:
    raise RuntimeError("CLC series are empty after cleaning.")

# ------------------------------------------------------------------
# Helper: first threshold-crossing below 1
# ------------------------------------------------------------------
def first_cross_below_one(series_df, value_col):
    s = series_df[['date', value_col]].dropna().copy()
    if s.empty or len(s) < 2:
        return None
    s['prev'] = s[value_col].shift(1)
    hit = s[(s['prev'] >= 1.0) & (s[value_col] < 1.0)]
    if hit.empty:
        return None
    row = hit.iloc[0]
    return row['date'], float(row[value_col])

# ------------------------------------------------------------------
# Figure
# ------------------------------------------------------------------
plt.close('all')
fig, ax = plt.subplots(figsize=(11.5, 6.5), dpi=220)

# y-range
y_vals = pd.concat([plot_df[c] for c in plot_cols], axis=0).dropna()
y_min = min(0.0, y_vals.min() - 0.10)
y_max = max(1.15, y_vals.max() + 0.12)

# danger zone below 1
ax.axhspan(y_min, 1.0, alpha=0.10, zorder=0)
ax.axhline(1.0, linestyle='--', linewidth=1.4, zorder=1, label='Threshold = 1.0')

# plot series
label_map = {}
if clc_3m_col is not None:
    label_map[clc_3m_col] = '3-month import liquidity cliff'
if clc_6m_col is not None:
    label_map[clc_6m_col] = '6-month import liquidity cliff'

style_map = {
    clc_3m_col: dict(linewidth=2.3, marker='o', markersize=5),
    clc_6m_col: dict(linewidth=2.3, marker='s', markersize=5),
}

for col in plot_cols:
    ax.plot(
        plot_df['date'],
        plot_df[col],
        label=label_map[col],
        **style_map[col]
    )

# ------------------------------------------------------------------
# Annotate first crossings
# ------------------------------------------------------------------
for col in plot_cols:
    cross = first_cross_below_one(plot_df, col)
    if cross is not None:
        x, y = cross
        ax.scatter([x], [y], s=55, zorder=5)
        ax.annotate(
            f"First < 1.0\n{pd.Timestamp(x).strftime('%Y-%m')} ({y:.2f})",
            xy=(x, y),
            xytext=(10, -28 if col == clc_3m_col else 18),
            textcoords='offset points',
            fontsize=9,
            bbox=dict(boxstyle='round,pad=0.25', fc='white', ec='0.5', alpha=0.95),
            arrowprops=dict(arrowstyle='-', lw=1.0)
        )

# ------------------------------------------------------------------
# Annotate latest values
# ------------------------------------------------------------------
for col in plot_cols:
    s = plot_df[['date', col]].dropna()
    if s.empty:
        continue
    x_last = s['date'].iloc[-1]
    y_last = float(s[col].iloc[-1])
    ax.scatter([x_last], [y_last], s=45, zorder=5)
    ax.annotate(
        f"{label_map[col]}: {y_last:.2f}",
        xy=(x_last, y_last),
        xytext=(8, 8 if col == clc_3m_col else -16),
        textcoords='offset points',
        fontsize=9,
        bbox=dict(boxstyle='round,pad=0.20', fc='white', ec='0.6', alpha=0.95)
    )

# ------------------------------------------------------------------
# Titles and formatting
# ------------------------------------------------------------------
ax.set_title(
    'UAE Central Bank Import Liquidity Cliff',
    fontsize=15,
    pad=14
)
ax.text(
    0.0, 1.01,
    'Cash and deposits abroad relative to estimated 3-month and 6-month import needs',
    transform=ax.transAxes,
    ha='left',
    va='bottom',
    fontsize=10
)

ax.set_ylabel('Coverage ratio')
ax.set_xlabel('Date')
ax.set_ylim(y_min, y_max)

# x-axis formatting
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
plt.setp(ax.get_xticklabels(), rotation=45, ha='right')

# grid
ax.grid(axis='y', alpha=0.25)
ax.grid(axis='x', alpha=0.10)

# legend placed cleanly above plot
ax.legend(
    loc='upper center',
    bbox_to_anchor=(0.5, -0.18),
    ncol=3,
    frameon=False,
    fontsize=10
)

# footnote
fig.text(
    0.01, 0.01,
    'Source: CBUAE reserve composition series and UAE macro series. '
    'Liquidity cliff is defined as liquid foreign cash/deposits divided by estimated import needs.',
    ha='left',
    va='bottom',
    fontsize=8
)

fig.tight_layout(rect=[0, 0.05, 1, 0.96])

OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT_PNG, dpi=300, bbox_inches='tight')
plt.show()

print(f"Saved: {OUT_PNG}")
print("\nColumns used:")
print(f"  3-month CLC: {clc_3m_col}")
print(f"  6-month CLC: {clc_6m_col}")
print("\nLatest data:")
display(plot_df.tail(10))

# ============================================================
# Figure 5 — UAE BTAR Scenarios (publication-quality)
# Standalone cell
# ============================================================

from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import textwrap

# ------------------------------------------------------------
# Paths
# ------------------------------------------------------------
BASE = Path("/content/drive/MyDrive/StockElephant/uae_swap_line_analysis")
OUT_CSV = BASE / "outputs" / "csv"
OUT_PLOTS = BASE / "outputs" / "plots"
OUT_PLOTS.mkdir(parents=True, exist_ok=True)

csv_path = OUT_CSV / "uae_btar_scenarios.csv"
if not csv_path.exists():
    raise FileNotFoundError(f"BTAR scenarios file not found: {csv_path}")

df = pd.read_csv(csv_path)
print("Loaded:", csv_path)
print("Shape:", df.shape)
print("Columns:", list(df.columns))

# ------------------------------------------------------------
# Helper: find likely columns robustly
# ------------------------------------------------------------
def find_col(columns, candidates):
    lower_map = {c.lower(): c for c in columns}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    for c in columns:
        cl = c.lower()
        for cand in candidates:
            if cand.lower() in cl:
                return c
    return None

layer_col = find_col(df.columns, [
    "layer", "source_layer", "exposure_layer", "bucket", "category", "name", "label", "series"
])

scenario_col = find_col(df.columns, [
    "scenario", "case", "stress_case"
])

btar_col = find_col(df.columns, [
    "btar", "btar_value", "ratio", "value"
])

exposure_col = find_col(df.columns, [
    "exposure_usd_bn", "exposure_bn", "exposure", "usd_exposure_bn", "layer_exposure_bn"
])

denom_col = find_col(df.columns, [
    "fed_absorption_bn", "denominator_bn", "absorption_bn", "fed_impulse_bn"
])

if layer_col is None or scenario_col is None or btar_col is None:
    raise RuntimeError(
        "Could not identify required BTAR columns.\n"
        f"Detected layer_col={layer_col}, scenario_col={scenario_col}, btar_col={btar_col}\n"
        f"Columns present: {list(df.columns)}"
    )

# ------------------------------------------------------------
# Clean / normalize
# ------------------------------------------------------------
plot_df = df.copy()

plot_df[scenario_col] = (
    plot_df[scenario_col]
    .astype(str)
    .str.strip()
    .str.lower()
    .replace({
        "low scenario": "low",
        "mid scenario": "mid",
        "middle": "mid",
        "medium": "mid",
        "high scenario": "high"
    })
)

plot_df[btar_col] = pd.to_numeric(plot_df[btar_col], errors="coerce")
plot_df = plot_df.dropna(subset=[layer_col, scenario_col, btar_col]).copy()

# Keep canonical scenario order if present
scenario_order = [s for s in ["low", "mid", "high"] if s in plot_df[scenario_col].unique().tolist()]
if not scenario_order:
    scenario_order = sorted(plot_df[scenario_col].unique().tolist())

# ------------------------------------------------------------
# Optional article filter
# These are the two layers you said matter most in the article.
# Set FILTER_TO_ARTICLE_LAYERS = False if you want all layers shown.
# ------------------------------------------------------------
FILTER_TO_ARTICLE_LAYERS = True

if FILTER_TO_ARTICLE_LAYERS:
    layer_text = plot_df[layer_col].astype(str).str.lower()
    mask = (
        layer_text.str.contains("foreign investments", na=False) |
        layer_text.str.contains("bis", na=False) |
        layer_text.str.contains("global usd liabilities", na=False)
    )
    filtered = plot_df.loc[mask].copy()
    if not filtered.empty:
        plot_df = filtered

# ------------------------------------------------------------
# Make pretty labels
# ------------------------------------------------------------
def clean_label(x):
    s = str(x)
    s = s.replace("CBUAE", "CBUAE ")
    s = s.replace("BIS", "BIS ")
    s = " ".join(s.split())
    return s.strip()

plot_df["_layer_clean"] = plot_df[layer_col].map(clean_label)

# Pivot for grouped bars
piv = plot_df.pivot_table(
    index="_layer_clean",
    columns=scenario_col,
    values=btar_col,
    aggfunc="first"
)

# Keep scenario order
existing_scenarios = [s for s in scenario_order if s in piv.columns]
piv = piv[existing_scenarios]

# Sort by high, then mid, then low if available
sort_key = None
for s in ["high", "mid", "low"]:
    if s in piv.columns:
        sort_key = s
        break
if sort_key is not None:
    piv = piv.sort_values(sort_key, ascending=False)

if piv.empty:
    raise RuntimeError("No BTAR rows available to plot after filtering.")

# Wrap long labels
wrapped_index = []
for idx in piv.index:
    wrapped_index.append("\n".join(textwrap.wrap(str(idx), width=26)))
piv.index = wrapped_index

# ------------------------------------------------------------
# Pull denominator for subtitle/note if available
# ------------------------------------------------------------
denom_text = None
if denom_col is not None:
    denom_vals = pd.to_numeric(df[denom_col], errors="coerce").dropna().unique()
    if len(denom_vals) > 0:
        denom_text = f"BTAR denominator = observed Fed balance-sheet absorption impulse (~${denom_vals[0]:.1f}B)"

# ------------------------------------------------------------
# Plot
# ------------------------------------------------------------
n_layers = len(piv.index)
n_scen = len(piv.columns)

fig_width = max(10.5, 2.2 * n_layers + 2.5)
fig_height = 7.2

fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=180)

x = np.arange(n_layers)
total_width = 0.78
bar_width = total_width / max(n_scen, 1)

# default matplotlib colors are fine
for i, scen in enumerate(piv.columns):
    offsets = x - total_width/2 + bar_width/2 + i * bar_width
    vals = piv[scen].values
    bars = ax.bar(offsets, vals, width=bar_width, label=scen.capitalize())

    # annotate bars
    for rect, v in zip(bars, vals):
        if pd.notna(v):
            ax.text(
                rect.get_x() + rect.get_width()/2,
                rect.get_height() + max(0.03, 0.015 * piv.max().max()),
                f"{v:.2f}",
                ha="center",
                va="bottom",
                fontsize=10
            )

# Threshold line at 1
ax.axhline(1.0, linewidth=1.8, linestyle="--")
ax.text(
    len(x) - 0.02,
    1.0 + max(0.03, 0.01 * piv.max().max()),
    "BTAR = 1 threshold",
    ha="right",
    va="bottom",
    fontsize=10
)

# Axes / labels
ax.set_xticks(x)
ax.set_xticklabels(piv.index, fontsize=11)
ax.set_ylabel("Basis Trade Absorption Ratio (BTAR)", fontsize=12)

title = "UAE BTAR Scenarios"
subtitle = "Scale test applied to observable UAE-linked dollar layers"
if denom_text is not None:
    subtitle = subtitle + f"\n{denom_text}"

ax.set_title(title, fontsize=15, pad=16)
fig.text(0.5, 0.93, subtitle, ha="center", va="center", fontsize=10)

# Grid and limits
ax.yaxis.grid(True, linestyle=":", alpha=0.5)
ax.set_axisbelow(True)

ymax = float(np.nanmax(piv.values))
ax.set_ylim(0, max(1.35, ymax * 1.22))

# Legend
ax.legend(
    title="Scenario",
    frameon=False,
    loc="upper left",
    bbox_to_anchor=(1.01, 1.0),
    borderaxespad=0.0
)

# Footnote
foot = (
    "BTAR > 1 indicates that the modeled exposure exceeds the comparison absorption impulse. "
    "This is a scale comparison, not direct attribution of UAE assets to basis-trade positions."
)
fig.text(0.01, 0.02, foot, ha="left", va="bottom", fontsize=9)

plt.tight_layout(rect=[0.03, 0.06, 0.86, 0.90])

out_path = OUT_PLOTS / "uae_btar_scenarios.png"
plt.savefig(out_path, dpi=300, bbox_inches="tight")
plt.show()

print(f"Saved: {out_path}")

if __name__ == '__main__':
    resume_phase1()
