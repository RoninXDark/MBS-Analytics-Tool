import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter, StrMethodFormatter
import os
import mbs_utils
import warnings

warnings.simplefilter(action='ignore')
matplotlib.use('Agg')
try:
    plt.style.use('seaborn-v0_8-whitegrid')
except:
    pass
plt.rcParams.update({'font.size': 10, 'figure.dpi': 150})


def robust_date_parser(val):
    try:
        num = float(val)
        if 35000 < num < 60000:
            return pd.to_datetime(num, unit='D', origin='1899-12-30')
    except:
        pass
    try:
        dt = pd.to_datetime(val, errors='coerce')
        if pd.notna(dt) and dt.year > 2000: return dt
    except:
        pass
    return pd.NaT


def filter_by_period(df, period, date_col=None):
    if not period or period == "All History": return df
    if date_col:
        last_date = df[date_col].max()
    else:
        last_date = df.index.max()
    if pd.isna(last_date): return df

    cutoff = None
    if period == "1 Month":
        cutoff = last_date - pd.DateOffset(months=1)
    elif period == "3 Months":
        cutoff = last_date - pd.DateOffset(months=3)
    elif period == "6 Months":
        cutoff = last_date - pd.DateOffset(months=6)
    elif period == "1 Year":
        cutoff = last_date - pd.DateOffset(years=1)
    elif period == "YTD":
        cutoff = pd.Timestamp(year=last_date.year, month=1, day=1)

    if cutoff:
        if date_col:
            return df[df[date_col] >= cutoff]
        else:
            return df[df.index >= cutoff]
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
    if filepath.endswith('.csv'):
        df_raw = pd.read_csv(filepath, header=None)
    else:
        df_raw = pd.read_excel(filepath, header=None)

    header_idx = -1;
    max_valid = 0
    for i in range(min(50, len(df_raw))):
        row = df_raw.iloc[i]
        valid = 0
        for val in row:
            if pd.notna(robust_date_parser(val)): valid += 1
        if valid > max_valid: max_valid = valid; header_idx = i

    if max_valid < 2: raise ValueError("CRITICAL: No valid dates found in first 50 rows.")

    if filepath.endswith('.csv'):
        df = pd.read_csv(filepath, header=header_idx)
    else:
        df = pd.read_excel(filepath, header=header_idx)

    date_cols = []
    for c in df.columns:
        if pd.notna(robust_date_parser(c)): date_cols.append(c)

    possible = [c for c in df.columns if c not in date_cols]
    bond_col = None;
    max_score = 0
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
        status_cb("Parsing Prices (32nds)...")
        try:
            df_num = df_clean.map(mbs_utils.parse_mbs_price)
        except:
            df_num = df_clean.applymap(mbs_utils.parse_mbs_price)
    else:
        status_cb("Loading Raw Values (Decimal)...")
        df_num = df_clean.apply(pd.to_numeric, errors='coerce')

    df_num.dropna(how='all', axis=1, inplace=True)
    return df_num


def load_residuals_data(filepath, status_cb):
    status_cb("Indexing Residuals...")
    if filepath.endswith('.csv'):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)

    res_col = None
    candidates = [c for c in df.columns if "residual" in str(c).lower()]
    for c in candidates:
        if "tick" in str(c).lower(): res_col = c; break
    if not res_col and candidates: res_col = candidates[0]
    if not res_col and 'Residual_Ticks' in df.columns: res_col = 'Residual_Ticks'
    if not res_col: raise ValueError("Could not find a 'Residuals' column in the file.")

    df['Date'] = pd.to_datetime(df['Date'])
    df['Res_Pts'] = df[res_col] / 32.0
    return df


# === UNIVERSAL CHART GENERATOR ===
def generate_charts(df, filepath, normalize, filter_txt, period, is_price_mode, stop_event, status_cb):
    df = filter_by_period(df, period)

    if is_price_mode:
        folder_name = "MBS_PRICES_OUTPUT"
    else:
        folder_name = "MBS_GENERAL_OUTPUT"

    base_dir = os.path.join(os.path.dirname(filepath), folder_name)
    indiv_dir = os.path.join(base_dir, "Individual_Charts")
    groups_dir = os.path.join(base_dir, "Group_Comparisons")
    os.makedirs(indiv_dir, exist_ok=True)

    if not filter_txt:
        os.makedirs(groups_dir, exist_ok=True)
        if is_price_mode and len(df) > 1:
            try:
                last = df.index[-1];
                week_idx = -min(5, len(df) - 1)
                d_diff = df.iloc[-1] - df.iloc[-2]
                w_diff = df.iloc[-1] - df.iloc[week_idx]

                def save_sheet(writer, name, diffs):
                    top = diffs.abs().sort_values(ascending=False).head(50)
                    vals = diffs.loc[top.index]
                    pd.DataFrame({
                        'Bond': top.index, 'Change_Dec': vals.values,
                        'Change_32nds': [mbs_utils.format_32nds(x) for x in vals.values]
                    }).to_excel(writer, sheet_name=name, index=False)

                with pd.ExcelWriter(os.path.join(base_dir, "REPORT_TOP_MOVERS.xlsx")) as w:
                    save_sheet(w, 'Daily Top 50', d_diff);
                    save_sheet(w, 'Weekly Top 50', w_diff)
            except:
                pass

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

            if is_price_mode:
                plt.gca().yaxis.set_major_formatter(FuncFormatter(mbs_utils.format_32nds))
            else:
                plt.gca().yaxis.set_major_formatter(StrMethodFormatter('{x:,.2f}'))

            setup_date_axis(plt.gca())
            plt.legend();
            plt.tight_layout()
            plt.savefig(os.path.join(groups_dir, f"Comparison_{prefix}.png"));
            plt.close()

    total = len(df.columns)
    for i, bond in enumerate(df.columns):
        if stop_event.is_set(): return

        if filter_txt and (filter_txt.lower() not in str(bond).lower()):
            continue

        status_cb(f"Charting {i + 1}/{total}: {bond}")
        s = df[bond].dropna()
        if len(s) < 2: continue
        if normalize: s = s - s.iloc[0]
        plt.figure(figsize=(10, 6))
        plt.plot(s.index, s.values, marker='o', markersize=4)
        plt.title(f"{bond} ({period})")

        if is_price_mode:
            plt.gca().yaxis.set_major_formatter(FuncFormatter(mbs_utils.format_32nds))
        else:
            plt.gca().yaxis.set_major_formatter(StrMethodFormatter('{x:,.2f}'))

        setup_date_axis(plt.gca())
        plt.grid(True, alpha=0.5);
        plt.tight_layout()
        safe = "".join([c if c.isalnum() else "_" for c in str(bond)])
        plt.savefig(os.path.join(indiv_dir, f"{safe}.png"));
        plt.close()

    return base_dir


# === UPDATED: NOW ACCEPTS is_price_mode argument ===
def generate_spread_chart(df, bond_a, bond_b, filepath, period, is_price_mode=True):
    df = filter_by_period(df, period)
    series_a = df[bond_a].dropna();
    series_b = df[bond_b].dropna()
    common_idx = series_a.index.intersection(series_b.index)
    if len(common_idx) < 2: raise ValueError(f"Not enough data for {period}.")
    spread = series_a.loc[common_idx] - series_b.loc[common_idx]

    plt.figure(figsize=(10, 6))
    plt.plot(spread.index, spread.values, label=f"{bond_a} - {bond_b}", color='purple')
    plt.axhline(0, color='black', linewidth=1)
    plt.title(f"Spread: {bond_a} minus {bond_b} ({period})")

    # === SWITCH AXIS FORMAT ===
    if is_price_mode:
        plt.gca().yaxis.set_major_formatter(FuncFormatter(mbs_utils.format_32nds))
    else:
        plt.gca().yaxis.set_major_formatter(StrMethodFormatter('{x:,.2f}'))
    # ==========================

    setup_date_axis(plt.gca())
    plt.grid(True, linestyle='--', alpha=0.5);
    plt.legend();
    plt.tight_layout()

    out_dir = os.path.join(os.path.dirname(filepath), "MBS_SPREADS")
    os.makedirs(out_dir, exist_ok=True)
    safe_name = f"{bond_a}_vs_{bond_b}".replace(" ", "_").replace("/", "-")
    path = os.path.join(out_dir, f"{safe_name}.png")
    plt.savefig(path);
    plt.close()
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
    plt.grid(True, linestyle='--', alpha=0.5);
    plt.legend();
    plt.tight_layout()

    out_dir = os.path.join(os.path.dirname(filepath), "MBS_RESIDUALS_OUTPUT")
    os.makedirs(out_dir, exist_ok=True)
    safe = "".join([c if c.isalnum() else "_" for c in str(bond_name)])
    path = os.path.join(out_dir, f"ResChart_{safe}.png")
    plt.savefig(path);
    plt.close()
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
    except:
        pass

    bonds = df['Bond'].unique()
    status_cb(f"Plotting {len(bonds)} residual points...")
    plt.figure(figsize=(14, 9))

    for b in bonds:
        if stop_event.is_set(): return
        sub = df[df['Bond'] == b].sort_values('Date')
        if sub.empty: continue
        style = 'o' if len(sub) == 1 else '-o'
        plt.plot(sub['Date'], sub['Res_Pts'], style, alpha=0.5, label=b if len(bonds) < 15 else "")

    plt.axhline(0, color='black', linewidth=1.5)
    plt.title(f"Residuals Market Overview ({period})")
    plt.gca().yaxis.set_major_formatter(FuncFormatter(mbs_utils.format_32nds))
    setup_date_axis(plt.gca())
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "Residuals_Scatter.png"));
    plt.close()
    return out_dir