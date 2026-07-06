import pandas as pd

import matplotlib

import matplotlib.pyplot as plt

import matplotlib.dates as mdates

from matplotlib.ticker import FuncFormatter, StrMethodFormatter

import os

from . import utils as mbs_utils

import warnings

import re

import numpy as np



warnings.simplefilter(action='ignore')

matplotlib.use('Agg')

try: plt.style.use('seaborn-v0_8-whitegrid')

except: pass

plt.rcParams.update({'font.size': 10, 'figure.dpi': 150})



# --- ENHANCED PARSER (Supports 3-digit ticks like 1-097) ---

def parse_mbs_price_extended(val):

    if isinstance(val, (int, float)): return float(val)

    s = str(val).strip().replace(',', '')

    if not s or s.lower() == 'nan': return float('nan')

    

    # Format: 100-16+ or 100-16

    if '-' in s and len(s.split('-')[1]) <= 3:

        try:

            base_str, tick_str = s.split('-')

            base = float(base_str)

            

            # 1-097 logic: 09 is ticks (9/32), 7 is 1/8 of a tick (7/256)

            if len(tick_str) == 3 and tick_str.isdigit():

                ticks = float(tick_str[:2])

                eighths = float(tick_str[2])

                return base + (ticks / 32.0) + (eighths / 256.0)

                

            # Standard logic

            ticks = 0.0

            if tick_str.endswith('+'):

                ticks = float(tick_str[:-1]) + 0.5

            elif tick_str.endswith('2') and len(tick_str)>2: # rare Bloomberg format

                 ticks = float(tick_str[:-1]) + 0.25

            elif tick_str.endswith('6') and len(tick_str)>2: # rare Bloomberg format

                 ticks = float(tick_str[:-1]) + 0.75

            else:

                ticks = float(tick_str)

            return base + (ticks / 32.0)

        except: pass

        

    try: return float(s)

    except: return float('nan')



def robust_date_parser(val):

    try:

        num = float(val)

        if 35000 < num < 60000:

            return pd.to_datetime(num, unit='D', origin='1899-12-30')

    except: pass

    try:

        dt = pd.to_datetime(val, errors='coerce')

        if pd.notna(dt) and dt.year > 2000: return dt

    except: pass

    return pd.NaT



def filter_by_period(df, period, date_col=None):

    if not period or period == "All History": return df

    if date_col: last_date = df[date_col].max()

    else: last_date = df.index.max()

    if pd.isna(last_date): return df

    

    cutoff = None

    if period == "1 Month": cutoff = last_date - pd.DateOffset(months=1)

    elif period == "3 Months": cutoff = last_date - pd.DateOffset(months=3)

    elif period == "6 Months": cutoff = last_date - pd.DateOffset(months=6)

    elif period == "1 Year": cutoff = last_date - pd.DateOffset(years=1)

    elif period == "YTD": cutoff = pd.Timestamp(year=last_date.year, month=1, day=1)

    

    if cutoff:

        if date_col: return df[df[date_col] >= cutoff]

        else: return df[df.index >= cutoff]

    return df



def setup_date_axis(ax):

    formatter = mdates.DateFormatter('%m/%d/%y')

    locator = mdates.AutoDateLocator()

    ax.xaxis.set_major_locator(locator)

    ax.xaxis.set_major_formatter(formatter)

    plt.gcf().autofmt_xdate()



# === UNIVERSAL LOADER ===

def load_timeseries_data(filepath, status_cb, is_price_mode=True):

    status_cb("Scanning file structure...")

    if filepath.endswith('.csv'): df_raw = pd.read_csv(filepath, header=None)

    else: df_raw = pd.read_excel(filepath, header=None)

    

    header_idx = -1; max_valid = 0

    for i in range(min(50, len(df_raw))):

        row = df_raw.iloc[i]

        valid = 0

        for val in row:

            if pd.notna(robust_date_parser(val)): valid += 1

        if valid > max_valid: max_valid = valid; header_idx = i

            

    if max_valid < 2: raise ValueError("CRITICAL: No valid dates found.")



    if filepath.endswith('.csv'): df = pd.read_csv(filepath, header=header_idx)

    else: df = pd.read_excel(filepath, header=header_idx)



    date_cols = []

    for c in df.columns:

        if pd.notna(robust_date_parser(c)): date_cols.append(c)

            

    possible = [c for c in df.columns if c not in date_cols]

    bond_col = None; max_score = 0

    for c in possible:

        s = df[c].astype(str)

        letters = s.str.contains('[a-zA-Z]').sum()

        unique = s[s != 'nan'].nunique()

        score = letters + (unique * 2)

        if score > max_score: max_score = score; bond_col = c



    if not bond_col: raise ValueError("Bond column not found.")



    df = df.dropna(subset=[bond_col])

    df = df.drop_duplicates(subset=[bond_col], keep='first')

    df_clean = df.set_index(bond_col)[date_cols].T

    new_idx = [robust_date_parser(x) for x in df_clean.index]

    df_clean.index = pd.to_datetime(new_idx)

    df_clean = df_clean[df_clean.index.notna()].sort_index()

    

    if is_price_mode:

        status_cb("Parsing Prices (Extended 32nds)...")

        try: df_num = df_clean.map(parse_mbs_price_extended)

        except: df_num = df_clean.applymap(parse_mbs_price_extended)

    else:

        status_cb("Loading Raw Values (Decimal)...")

        df_num = df_clean.apply(pd.to_numeric, errors='coerce')



    df_num.dropna(how='all', axis=1, inplace=True)

    return df_num



def load_residuals_data(filepath, status_cb):

    status_cb("Indexing Residuals...")

    if filepath.endswith('.csv'): df = pd.read_csv(filepath)

    else: df = pd.read_excel(filepath)

    res_col = None

    candidates = [c for c in df.columns if "residual" in str(c).lower()]

    for c in candidates:

        if "tick" in str(c).lower(): res_col = c; break

    if not res_col and candidates: res_col = candidates[0]

    if not res_col and 'Residual_Ticks' in df.columns: res_col = 'Residual_Ticks'

    if not res_col: raise ValueError("Could not find a 'Residuals' column.")

    df['Date'] = pd.to_datetime(df['Date'])

    df['Res_Pts'] = df[res_col] / 32.0

    return df



# === CHART GENERATOR ===

def generate_charts(df, filepath, normalize, filter_txt, period, is_price_mode, stop_event, status_cb):

    df = filter_by_period(df, period)

    if is_price_mode: folder_name = "MBS_PRICES_OUTPUT"

    else: folder_name = "MBS_GENERAL_OUTPUT"

    base_dir = os.path.join(os.path.dirname(filepath), folder_name)

    indiv_dir = os.path.join(base_dir, "Individual_Charts")

    groups_dir = os.path.join(base_dir, "Group_Comparisons")

    os.makedirs(indiv_dir, exist_ok=True)

    

    if filter_txt:

        filtered_bonds = [b for b in df.columns if filter_txt.lower() in str(b).lower()]

        if len(filtered_bonds) > 1:

            os.makedirs(groups_dir, exist_ok=True)

            status_cb(f"Creating Comparison for '{filter_txt}'...")

            plt.figure(figsize=(12, 7))

            for b in filtered_bonds:

                y = df[b].dropna()

                if normalize: y = y - y.iloc[0]

                plt.plot(y.index, y.values, label=b, alpha=0.8)

            plt.title(f"Comparison: {filter_txt} ({period})")

            if is_price_mode: plt.gca().yaxis.set_major_formatter(FuncFormatter(mbs_utils.format_32nds))

            else: plt.gca().yaxis.set_major_formatter(StrMethodFormatter('{x:,.2f}'))

            setup_date_axis(plt.gca())

            plt.legend(); plt.tight_layout()

            safe_name = "".join([c if c.isalnum() else "_" for c in filter_txt])

            plt.savefig(os.path.join(groups_dir, f"Comparison_Filter_{safe_name}.png")); plt.close()



    elif not filter_txt:

        os.makedirs(groups_dir, exist_ok=True)

        status_cb("Grouping Families...")

        groups = {}

        for c in df.columns: groups.setdefault(str(c).split()[0], []).append(c)

        for prefix, bonds in groups.items():

            if stop_event.is_set(): return

            if len(bonds) < 2: continue

            plt.figure(figsize=(12, 7))

            count = 0

            for b in bonds:

                y = df[b].dropna()

                if len(y) > 1:

                    if normalize: y = y - y.iloc[0]

                    plt.plot(y.index, y.values, label=b, alpha=0.8)

                    count += 1

                if count > 10: break

            plt.title(f"{prefix} Comparison ({period})")

            if is_price_mode: plt.gca().yaxis.set_major_formatter(FuncFormatter(mbs_utils.format_32nds))

            else: plt.gca().yaxis.set_major_formatter(StrMethodFormatter('{x:,.2f}'))

            setup_date_axis(plt.gca())

            plt.legend(); plt.tight_layout()

            plt.savefig(os.path.join(groups_dir, f"Comparison_{prefix}.png")); plt.close()



    total = len(df.columns)

    for i, bond in enumerate(df.columns):

        if stop_event.is_set(): return

        if filter_txt and (filter_txt.lower() not in str(bond).lower()): continue

        status_cb(f"Charting {i+1}/{total}: {bond}")

        s = df[bond].dropna()

        if len(s) < 2: continue

        if normalize: s = s - s.iloc[0]

        plt.figure(figsize=(10, 6))

        plt.plot(s.index, s.values, marker='o', markersize=4)

        plt.title(f"{bond} ({period})")

        if is_price_mode: plt.gca().yaxis.set_major_formatter(FuncFormatter(mbs_utils.format_32nds))

        else: plt.gca().yaxis.set_major_formatter(StrMethodFormatter('{x:,.2f}'))

        setup_date_axis(plt.gca())

        plt.grid(True, alpha=0.5); plt.tight_layout()

        safe = "".join([c if c.isalnum() else "_" for c in str(bond)])

        plt.savefig(os.path.join(indiv_dir, f"{safe}.png")); plt.close()



    return base_dir



def generate_spread_chart(df, bond_a, bond_b, filepath, period, is_price_mode=True):

    df = filter_by_period(df, period)

    series_a = df[bond_a].dropna(); series_b = df[bond_b].dropna()

    common_idx = series_a.index.intersection(series_b.index)

    if len(common_idx) < 2: raise ValueError(f"Not enough data for {period}.")

    spread = series_a.loc[common_idx] - series_b.loc[common_idx]

    

    plt.figure(figsize=(10, 6))

    plt.plot(spread.index, spread.values, label=f"{bond_a} - {bond_b}", color='purple')

    plt.axhline(0, color='black', linewidth=1)

    plt.title(f"Spread: {bond_a} minus {bond_b} ({period})")

    if is_price_mode: plt.gca().yaxis.set_major_formatter(FuncFormatter(mbs_utils.format_32nds))

    else: plt.gca().yaxis.set_major_formatter(StrMethodFormatter('{x:,.2f}'))

    setup_date_axis(plt.gca())

    plt.grid(True, linestyle='--', alpha=0.5); plt.legend(); plt.tight_layout()

    out_dir = os.path.join(os.path.dirname(filepath), "MBS_SPREADS")

    os.makedirs(out_dir, exist_ok=True)

    safe_name = f"{bond_a}_vs_{bond_b}".replace(" ", "_").replace("/", "-")

    path = os.path.join(out_dir, f"{safe_name}.png")

    plt.savefig(path); plt.close()

    return path



def generate_residual_line_chart(df, bond_name, filepath, period):

    sub = df[df['Bond'] == bond_name].copy()

    sub = filter_by_period(sub, period, date_col='Date')

    sub = sub.sort_values('Date')

    if sub.empty: raise ValueError(f"No data for {bond_name} in {period}")

    plt.figure(figsize=(10, 6))

    plt.plot(sub['Date'], sub['Res_Pts'], marker='o', markersize=4, label=bond_name, linewidth=2, color='#1f77b4')

    plt.axhline(0, color='black', linewidth=1.5, linestyle='-')

    plt.title(f"Residuals History: {bond_name} ({period})")

    plt.gca().yaxis.set_major_formatter(FuncFormatter(mbs_utils.format_32nds))

    setup_date_axis(plt.gca())

    plt.grid(True, linestyle='--', alpha=0.5); plt.legend(); plt.tight_layout()

    out_dir = os.path.join(os.path.dirname(filepath), "MBS_RESIDUALS_OUTPUT")

    os.makedirs(out_dir, exist_ok=True)

    safe = "".join([c if c.isalnum() else "_" for c in str(bond_name)])

    path = os.path.join(out_dir, f"ResChart_{safe}.png")

    plt.savefig(path); plt.close()

    return path



def process_residuals_scatter(df, filepath, period, stop_event, status_cb):

    df = filter_by_period(df, period, date_col='Date')

    out_dir = os.path.join(os.path.dirname(filepath), "MBS_RESIDUALS_OUTPUT")

    os.makedirs(out_dir, exist_ok=True)

    try:

        latest_date = df['Date'].max()

        latest_df = df[df['Date'] == latest_date].sort_values('Res_Pts', ascending=False)

        top_rich = latest_df.head(10)[['Bond', 'Res_Pts']]

        top_cheap = latest_df.tail(10)[['Bond', 'Res_Pts']]

        with pd.ExcelWriter(os.path.join(out_dir, "REPORT_RICH_CHEAP.xlsx")) as w:

            top_rich['Res_32s'] = top_rich['Res_Pts'].apply(mbs_utils.format_32nds)

            top_cheap['Res_32s'] = top_cheap['Res_Pts'].apply(mbs_utils.format_32nds)

            top_rich.to_excel(w, sheet_name='Top 10 Rich', index=False)

            top_cheap.to_excel(w, sheet_name='Top 10 Cheap', index=False)

    except: pass

    bonds = df['Bond'].unique()

    status_cb(f"Plotting {len(bonds)} residual points...")

    plt.figure(figsize=(14, 9))

    for b in bonds:

        if stop_event.is_set(): return

        sub = df[df['Bond'] == b].sort_values('Date')

        if sub.empty: continue

        style = 'o' if len(sub)==1 else '-o'

        plt.plot(sub['Date'], sub['Res_Pts'], style, alpha=0.5, label=b if len(bonds)<15 else "")

    plt.axhline(0, color='black', linewidth=1.5)

    plt.title(f"Residuals Market Overview ({period})")

    plt.gca().yaxis.set_major_formatter(FuncFormatter(mbs_utils.format_32nds))

    setup_date_axis(plt.gca())

    plt.tight_layout()

    plt.savefig(os.path.join(out_dir, "Residuals_Scatter.png")); plt.close()

    return out_dir



# === NEW: CURVE ANALYSIS LOGIC (UPDATED: FULL LABELS ON X-AXIS) ===

def generate_curve_analysis(df, filepath, filter_txt, mode, period):

    # 1. FIND BONDS

    matched_bonds = [c for c in df.columns if filter_txt.lower() in str(c).lower()]

    if not matched_bonds: raise ValueError(f"No bonds found matching '{filter_txt}'")

    

    # 2. EXTRACT COUPONS

    data = []

    for bond in matched_bonds:

        # Regex looks for number, possibly decimal, surrounded by spaces

        # e.g. "FNCL 3.5 2022" -> 3.5

        match = re.search(r' (\d+\.?\d*) ', str(bond))

        if match:

            coupon = float(match.group(1))

            if 0 < coupon < 15:

                data.append({'Bond': bond, 'Coupon': coupon})

    

    if not data: raise ValueError("Found matching bonds but couldn't parse Coupons (e.g. '3.5').")

    

    meta = pd.DataFrame(data).sort_values('Coupon')

    

    # 3. PLOT

    out_dir = os.path.join(os.path.dirname(filepath), "MBS_CURVES")

    os.makedirs(out_dir, exist_ok=True)

    

    if mode == "Time Series":

        # Plot history lines

        df_sub = df[meta['Bond']]

        df_sub = filter_by_period(df_sub, period)

        

        plt.figure(figsize=(12, 7))

        for _, row in meta.iterrows():

            bond = row['Bond']

            y = df_sub[bond].dropna()

            if not y.empty:

                plt.plot(y.index, y.values, label=f"Cpn {row['Coupon']} ({bond})")

        

        plt.title(f"Pay-up History: {filter_txt} ({period})")

        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')

        plt.gca().yaxis.set_major_formatter(FuncFormatter(mbs_utils.format_32nds))

        setup_date_axis(plt.gca())

        plt.tight_layout()

        fname = f"History_{filter_txt}.png"

        

    else: # Curve Mode (Snapshot)

        # Get latest valid prices

        latest_prices = []

        df_sub = df[meta['Bond']]

        last_date = df_sub.dropna(how='all').index[-1]

        

        for _, row in meta.iterrows():

            bond = row['Bond']

            try:

                val = df_sub.loc[last_date, bond]

                if pd.notna(val):

                    latest_prices.append({'Coupon': row['Coupon'], 'Price': val, 'Bond': bond})

            except: pass

            

        if not latest_prices: raise ValueError("No valid price data for latest date.")

        

        curve_df = pd.DataFrame(latest_prices).sort_values('Coupon')

        

        plt.figure(figsize=(12, 7)) # Slightly wider for labels

        

        # Use simple numeric index for X, but label with Full Names

        x_pos = range(len(curve_df))

        plt.plot(x_pos, curve_df['Price'], marker='o', markersize=8, linestyle='-', linewidth=2)

        

        # Set X-Ticks to be the Bond Names (Rotated)

        plt.xticks(x_pos, curve_df['Bond'], rotation=45, ha='right')

        

        for i, row in enumerate(curve_df.itertuples()):

            lbl = mbs_utils.format_32nds(row.Price)

            plt.annotate(lbl, (i, row.Price), textcoords="offset points", xytext=(0,10), ha='center')

            

        plt.title(f"Pay-up Curve: {filter_txt} (as of {last_date.strftime('%Y-%m-%d')})")

        plt.ylabel("Price (32nds)")

        plt.gca().yaxis.set_major_formatter(FuncFormatter(mbs_utils.format_32nds))

        plt.grid(True, linestyle='--')

        plt.tight_layout()

        fname = f"Curve_Snapshot_{filter_txt}.png"



    stem, ext = os.path.splitext(fname)
    safe_stem = "".join([c if c.isalnum() else "_" for c in stem]).strip("_")
    safe = f"{safe_stem}{ext}"

    final_path = os.path.join(out_dir, safe)

    plt.savefig(final_path)

    plt.close()

    

    return final_path