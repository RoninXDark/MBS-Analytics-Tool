import tkinter as tk

from tkinter import filedialog, messagebox, simpledialog, ttk

try:
    import ttkbootstrap as ttkbootstrap

    HAS_TTKBOOTSTRAP = True
except Exception:
    ttkbootstrap = None

    HAS_TTKBOOTSTRAP = False

import threading

import os
import json
import logging
import copy
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import backend as mbs_backend
from ..automation import (
    DEFAULT_MIN_OBSERVATIONS,
    IdeaScanRunDefinition,
    resolve_latest_input_file,
    resolve_saved_workflow,
    run_idea_scan_definition,
    run_saved_batch,
)
from ..data import load_and_normalize_dataset
from ..logging_setup import configure_logging
from ..runtime_paths import resolve_default_config_store_path, resolve_default_overnight_output_dir



def _calculate_start_geometry(screen_width: int, screen_height: int) -> tuple[int, int, int, int, int, int]:
    """Return a large, centered startup geometry without forcing full-screen."""

    default_width = min(max(1600, int(screen_width * 0.92)), max(screen_width - 80, 1180))
    default_height = min(max(950, int(screen_height * 0.88)), max(screen_height - 120, 760))
    min_width = min(1280, default_width)
    min_height = min(820, default_height)
    x_offset = max((screen_width - default_width) // 2, 0)
    y_offset = max((screen_height - default_height) // 3, 0)
    return default_width, default_height, min_width, min_height, x_offset, y_offset


class MBSApp:

    def __init__(self, root):

        self.root = root

        self.root.title("MBS Analytics Tool (Client Edition v3.0)")

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        default_width, default_height, min_width, min_height, x_offset, y_offset = _calculate_start_geometry(
            screen_width,
            screen_height,
        )
        self.root.geometry(f"{default_width}x{default_height}+{x_offset}+{y_offset}")
        self.root.minsize(min_width, min_height)

        

        self.stop_event = threading.Event()

        # Data containers

        self.df_prices = None

        self.df_generic = None

        self.df_residuals = None

        

        # Paths

        self.path_prices = ""

        self.path_generic = ""

        self.path_residuals = ""

        self.config_store_path = resolve_default_config_store_path()
        self.saved_configs = {}
        self.last_automation_output_path = None
        self.last_automation_metadata_path = None
        self.current_automation_metadata_file_path = None
        self.pending_saved_config_run_name = None
        self.auto_filter_widgets = {}
        self.auto_filter_values = {}
        self.log_path = configure_logging()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Desktop GUI initialized")

        

        self._busy = False
        self._resize_last_size = None
        self._default_status_text = "Ready."

        style = ttk.Style()
        if HAS_TTKBOOTSTRAP:
            theme_name = os.getenv("MBS_THEME", "superhero")
            try:
                style.theme_use(theme_name)
            except Exception:
                try:
                    style.theme_use("cosmo")
                except Exception:
                    style.theme_use("clam")
        else:
            style.theme_use("clam")
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), padding=(14, 8))

        

        # UI Tabs
        self.nb = ttk.Notebook(root)
        self.nb.pack(expand=True, fill='both', padx=10, pady=10)

        self.analysis_tab = ttk.Frame(self.nb)
        self.t6 = ttk.Frame(self.nb)
        self.nb.add(self.analysis_tab, text="Analysis")
        self.nb.add(self.t6, text="Automation")

        self.analysis_nb = ttk.Notebook(self.analysis_tab)
        self.analysis_nb.pack(expand=True, fill='both', padx=8, pady=8)

        self.t1 = ttk.Frame(self.analysis_nb)
        self.t5 = ttk.Frame(self.analysis_nb)
        self.t3 = ttk.Frame(self.analysis_nb)
        self.t4 = ttk.Frame(self.analysis_nb)
        self.t2 = ttk.Frame(self.analysis_nb)

        self.analysis_nb.add(self.t1, text="Price History")
        self.analysis_nb.add(self.t5, text="Pay-up Curves")
        self.analysis_nb.add(self.t3, text="Spread")
        self.analysis_nb.add(self.t4, text="General/OAS")
        self.analysis_nb.add(self.t2, text="Residuals")
        self.analysis_nb.bind("<<NotebookTabChanged>>", self._on_analysis_mode_changed)

        self.setup_t1()       # Prices
        self.setup_t5()       # Curves
        self.setup_t3()       # Spreads
        self.setup_t4()       # Generic/OAS
        self.setup_t2()       # Residuals
        self.setup_t6()       # Automation

        

        # Status Bar

        self.status = tk.StringVar(value=self._default_status_text)

        bar = ttk.Frame(root, relief=tk.RAISED)

        bar.pack(side=tk.BOTTOM, fill=tk.X)

        ttk.Label(bar, textvariable=self.status).pack(side=tk.LEFT, padx=10)

        right_bar = ttk.Frame(bar)
        right_bar.pack(side=tk.RIGHT, padx=6, pady=4)

        self.progress_text = tk.StringVar(value="0%")
        ttk.Label(right_bar, textvariable=self.progress_text, width=10, anchor=tk.E).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Label(right_bar, text="Progress:").pack(side=tk.RIGHT, padx=(0, 6))

        self.progress = ttk.Progressbar(right_bar, mode="determinate", length=280, maximum=100)
        self.progress.pack(side=tk.RIGHT)

        self.btn_stop = ttk.Button(bar, text="STOP", command=self.stop, state='disabled')

        self.btn_stop.pack(side=tk.RIGHT, padx=(0, 8))

        self.root.bind("<Configure>", self._on_root_configure)



    # --- TAB 1: PRICES ---

    def setup_t1(self):

        f = ttk.Labelframe(self.t1, text="Bond Price Data Input", padding=15)

        f.pack(fill='x', padx=10, pady=10)

        

        self.p1 = tk.StringVar()

        ttk.Entry(f, textvariable=self.p1).pack(side=tk.LEFT, fill='x', expand=True)

        ttk.Button(f, text="Browse", command=lambda: self.browse(self.p1)).pack(side=tk.RIGHT)

        

        f2 = ttk.Frame(self.t1); f2.pack(fill='x', padx=10)

        ttk.Label(f2, text="Time Period:").pack(side=tk.LEFT, pady=10)

        self.period_p = tk.StringVar(value="All History")

        times = ["All History", "YTD", "1 Year", "6 Months", "3 Months", "1 Month"]

        ttk.Combobox(f2, textvariable=self.period_p, values=times, state="readonly", width=15).pack(side=tk.LEFT, padx=5, pady=10)

        

        self.norm_p = tk.BooleanVar()

        ttk.Checkbutton(f2, text="Normalize (Start at 0)", variable=self.norm_p).pack(side=tk.RIGHT, pady=10, padx=5)

        

        f3 = ttk.Labelframe(self.t1, text="Smart Filter & Grouping", padding=10)

        f3.pack(fill='x', padx=10)

        ttk.Label(f3, text="Enter text (e.g. '2022 FL') to generate individual charts AND a comparison overlay:").pack(anchor=tk.W)

        self.filt_p = tk.StringVar()

        self.cb_price_filter = ttk.Combobox(f3, textvariable=self.filt_p, values=[], state="normal")
        self.cb_price_filter.pack(fill='x', pady=5)

        

        ttk.Button(self.t1, text="LOAD PRICE DATA", command=self.load_prices).pack(pady=5)

        ttk.Button(self.t1, text="GENERATE PRICE CHARTS", command=self.run_prices).pack(pady=5)



    # --- TAB 5: CURVES (NEW) ---

    def setup_t5(self):

        f = ttk.Labelframe(self.t5, text="Curve Analysis Control", padding=15)

        f.pack(fill='both', expand=True, padx=10, pady=10)

        

        ttk.Label(f, text="1. Load a Price History dataset in the Price History sub-tab.").pack(anchor=tk.W, pady=5)

        

        ttk.Label(f, text="2. Smart Search (e.g. '2022 FL' or 'NY'):").pack(anchor=tk.W, pady=(15, 5))

        self.curve_filter = tk.StringVar()

        self.cb_curve_filter = ttk.Combobox(f, textvariable=self.curve_filter, values=[], state="normal")
        self.cb_curve_filter.pack(fill='x', pady=5)

        

        ttk.Label(f, text="3. Select Chart Type:").pack(anchor=tk.W, pady=(15, 5))

        self.curve_mode = tk.StringVar(value="Time Series")

        

        # Radio buttons for modes

        rb1 = ttk.Radiobutton(f, text="Time Series (History of all coupons)", variable=self.curve_mode, value="Time Series")

        rb1.pack(anchor=tk.W, padx=10)

        

        rb2 = ttk.Radiobutton(f, text="Pay-up Curve (Scatter: Coupon vs Price - Latest Date)", variable=self.curve_mode, value="Curve")

        rb2.pack(anchor=tk.W, padx=10)

        

        ttk.Label(f, text="Time Period (for Time Series only):").pack(anchor=tk.W, pady=(15, 5))

        self.period_c = tk.StringVar(value="3 Months")

        times = ["All History", "YTD", "1 Year", "6 Months", "3 Months", "1 Month"]

        ttk.Combobox(f, textvariable=self.period_c, values=times, state="readonly").pack(fill='x', padx=5)



        ttk.Button(f, text="GENERATE CURVE ANALYSIS", command=self.run_curve).pack(pady=25, ipadx=10, ipady=5)



    # --- TAB 4: GENERIC/OAS ---

    def setup_t4(self):

        f = ttk.Labelframe(self.t4, text="General Data Input (OAS, Yields, etc.)", padding=15)

        f.pack(fill='x', padx=10, pady=10)

        

        self.p4 = tk.StringVar()

        ttk.Entry(f, textvariable=self.p4).pack(side=tk.LEFT, fill='x', expand=True)

        ttk.Button(f, text="Browse", command=lambda: self.browse(self.p4)).pack(side=tk.RIGHT)

        

        f2 = ttk.Frame(self.t4); f2.pack(fill='x', padx=10)

        ttk.Label(f2, text="Time Period:").pack(side=tk.LEFT, pady=10)

        self.period_g = tk.StringVar(value="All History")

        times = ["All History", "YTD", "1 Year", "6 Months", "3 Months", "1 Month"]

        ttk.Combobox(f2, textvariable=self.period_g, values=times, state="readonly", width=15).pack(side=tk.LEFT, padx=5, pady=10)

        

        self.norm_g = tk.BooleanVar()

        ttk.Checkbutton(f2, text="Normalize", variable=self.norm_g).pack(side=tk.RIGHT, pady=10, padx=5)



        f3 = ttk.Labelframe(self.t4, text="Filter & Group", padding=10)

        f3.pack(fill='x', padx=10)

        self.filt_g = tk.StringVar()

        self.cb_generic_filter = ttk.Combobox(f3, textvariable=self.filt_g, values=[], state="normal")
        self.cb_generic_filter.pack(fill='x')

        

        ttk.Button(self.t4, text="LOAD GENERAL DATA", command=self.load_generic).pack(pady=5)

        ttk.Button(self.t4, text="GENERATE CHARTS", command=self.run_generic).pack(pady=5)



    # --- TAB 3: SPREADS ---

    def setup_t3(self):

        f_src = ttk.Labelframe(self.t3, text="Select Data Source for Spread", padding=10)

        f_src.pack(fill='x', padx=10, pady=5)

        

        self.spread_source = tk.StringVar(value="Price")

        rb1 = ttk.Radiobutton(f_src, text="Price History data", variable=self.spread_source, value="Price", command=self.refresh_spread_combos)

        rb1.pack(side=tk.LEFT, padx=20)

        rb2 = ttk.Radiobutton(f_src, text="General/OAS data", variable=self.spread_source, value="OAS", command=self.refresh_spread_combos)

        rb2.pack(side=tk.LEFT, padx=20)



        f = ttk.Labelframe(self.t3, text="Interactive Spread Calculator", padding=15)

        f.pack(fill='both', expand=True, padx=10, pady=10)

        

        # SMART SEARCH FOR SPREADS

        ttk.Label(f, text="Search/Filter Bond List:").pack(anchor=tk.W)

        self.search_spread = tk.StringVar()

        self.search_spread.trace("w", self.filter_spread_combos)

        ttk.Entry(f, textvariable=self.search_spread).pack(fill='x', pady=5)



        ttk.Label(f, text="Bond A (Long):").pack(anchor=tk.W)

        self.cb_a = ttk.Combobox(f); self.cb_a.pack(fill='x', pady=5)

        

        ttk.Label(f, text="Bond B (Short):").pack(anchor=tk.W)

        self.cb_b = ttk.Combobox(f); self.cb_b.pack(fill='x', pady=5)

        

        ttk.Button(f, text="PLOT SPREAD", command=self.run_spread).pack(pady=20, ipadx=10)



    # --- TAB 2: RESIDUALS ---

    def setup_t2(self):

        f = ttk.Labelframe(self.t2, text="Residuals Input", padding=15)

        f.pack(fill='x', padx=10, pady=10)

        self.p2 = tk.StringVar()

        ttk.Entry(f, textvariable=self.p2).pack(side=tk.LEFT, fill='x', expand=True)

        ttk.Button(f, text="Browse", command=lambda: self.browse(self.p2)).pack(side=tk.RIGHT)

        

        ttk.Button(self.t2, text="LOAD RESIDUALS FILE", command=self.load_residuals).pack(pady=5)

        

        f_sel = ttk.Labelframe(self.t2, text="Chart Specific Bond", padding=15)

        f_sel.pack(fill='both', expand=True, padx=10, pady=10)

        

        # SMART SEARCH FOR RESIDUALS

        ttk.Label(f_sel, text="Search/Filter Bond List:").pack(anchor=tk.W)

        self.search_res = tk.StringVar()

        self.search_res.trace("w", self.filter_res_combo)

        ttk.Entry(f_sel, textvariable=self.search_res).pack(fill='x', pady=5)



        ttk.Label(f_sel, text="Select Bond:").pack(anchor=tk.W)

        self.cb_res_bond = ttk.Combobox(f_sel)

        self.cb_res_bond.pack(fill='x', pady=5)

        

        ttk.Label(f_sel, text="Timeline:").pack(anchor=tk.W, pady=(10,0))

        self.period_res = tk.StringVar(value="All History")

        times = ["All History", "YTD", "1 Year", "6 Months", "3 Months", "1 Month"]

        ttk.Combobox(f_sel, textvariable=self.period_res, values=times, state="readonly").pack(fill='x', pady=5)

        

        ttk.Button(f_sel, text="CHART RESIDUAL (LINE)", command=self.run_res_chart).pack(pady=10)

        ttk.Button(self.t2, text="GENERATE MARKET OVERVIEW (Scatter)", command=self.run_res_scatter).pack(pady=5)


    # --- TAB 6: AUTOMATION ---
    def setup_t6(self):
        self.t6.columnconfigure(0, weight=1)
        self.t6.rowconfigure(0, weight=1)

        self.auto_nb = ttk.Notebook(self.t6)
        self.auto_nb.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        tab_ideas = ttk.Frame(self.auto_nb)
        tab_canned = ttk.Frame(self.auto_nb)
        tab_overnight = ttk.Frame(self.auto_nb)
        tab_ideas.columnconfigure(0, weight=1)
        tab_ideas.rowconfigure(1, weight=1)
        tab_canned.columnconfigure(0, weight=1)
        tab_canned.rowconfigure(0, weight=1)
        tab_overnight.columnconfigure(0, weight=1)
        tab_overnight.rowconfigure(0, weight=1)

        self.auto_nb.add(tab_ideas, text="Ideas Workspace")
        self.auto_nb.add(tab_canned, text="Canned Reports")
        self.auto_nb.add(tab_overnight, text="BUY/SELL Runs / Saved Configs")

        intro = ttk.Labelframe(tab_ideas, text="Summary Tables / Dataset", padding=14)
        intro.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 10))
        intro.columnconfigure(0, weight=1)

        self.auto_config_name = tk.StringVar()
        self.auto_input_mode = tk.StringVar(value="fixed_file")
        self.auto_input = tk.StringVar()
        self.auto_input_folder = tk.StringVar()
        self.auto_input_pattern = tk.StringVar(value="*.xlsx")
        self.auto_output = tk.StringVar(value=str(resolve_default_overnight_output_dir()))
        self.auto_generate_summary_tables = tk.BooleanVar(value=True)
        self.auto_filters_visible = tk.BooleanVar(value=False)
        self.auto_fixed_source_widgets = []
        self.auto_latest_source_widgets = []

        self._add_automation_source_controls(intro, include_load_button=True)

        output_row = ttk.Frame(intro)
        output_row.pack(fill='x', pady=4)
        ttk.Label(output_row, text="Output root folder:", width=26).pack(side=tk.LEFT)
        ttk.Entry(output_row, textvariable=self.auto_output).pack(side=tk.LEFT, fill='x', expand=True, padx=5)
        ttk.Button(output_row, text="Browse", command=self.browse_output_dir).pack(side=tk.LEFT)
        ttk.Checkbutton(
            intro,
            text="Write client report, BUY/SELL charts, and diagnostics metadata",
            variable=self.auto_generate_summary_tables,
            state="disabled",
        ).pack(anchor=tk.W, pady=(6, 0))
        ttk.Label(
            intro,
            text="This workflow writes the client Excel report, BUY/SELL charts, diagnostics metadata, and run metadata.",
            wraplength=940,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, fill='x', pady=(8, 2))

        idea_actions = ttk.Frame(intro)
        idea_actions.pack(fill='x', pady=(10, 0))
        ttk.Button(
            idea_actions,
            text="RUN BUY/SELL SCAN",
            command=self.run_idea_scan_from_workspace,
            style="Primary.TButton",
            width=22,
        ).pack(side=tk.LEFT)
        ttk.Button(
            idea_actions,
            text="SAVE CONFIG",
            command=self.save_automation_config,
            width=14,
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(
            idea_actions,
            text="OPEN OUTPUT FOLDER",
            command=self.open_automation_output,
            width=20,
        ).pack(side=tk.LEFT, padx=(8, 0))
        self.btn_auto_filters = ttk.Button(
            idea_actions,
            text="SHOW OPTIONAL FILTERS",
            command=self.toggle_auto_filters,
            width=22,
        )
        self.btn_auto_filters.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(
            idea_actions,
            text="Run directly from this screen, or save the setup for nightly automation.",
        ).pack(side=tk.LEFT, padx=(12, 0))

        ideas_grid = ttk.Frame(tab_ideas)
        self.ideas_grid = ideas_grid
        ideas_grid.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 14))
        ideas_grid.columnconfigure(0, weight=5, minsize=500)
        ideas_grid.columnconfigure(1, weight=4, minsize=430)
        ideas_grid.rowconfigure(0, weight=1)

        left_ideas = ttk.Frame(ideas_grid)
        left_ideas.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left_ideas.columnconfigure(0, weight=1)
        right_ideas = ttk.Frame(ideas_grid)
        self.auto_filters_panel = right_ideas
        right_ideas.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        right_ideas.columnconfigure(0, weight=1)

        ranking = ttk.Labelframe(left_ideas, text="BUY / SELL Ranking", padding=16)
        ranking.pack(fill='x', expand=False, pady=(0, 10))

        self.auto_rank_by = tk.StringVar(value="Z-Score")
        self.auto_top_n = tk.StringVar(value="10")
        self.auto_min_observations = tk.StringVar(value=str(DEFAULT_MIN_OBSERVATIONS))
        self.auto_use_default_focus = tk.BooleanVar(value=True)
        self.auto_include_full_chart_history = tk.BooleanVar(value=True)
        self.auto_include_parse_failures = tk.BooleanVar(value=True)
        self.auto_run_profile = tk.StringVar(value="Standard (Recommended)")

        rank_row = ttk.Frame(ranking)
        rank_row.pack(fill='x', pady=(2, 6))
        rank_row.columnconfigure(1, weight=1)
        rank_row.columnconfigure(2, weight=0)
        rank_row.columnconfigure(3, weight=1)
        ttk.Label(rank_row, text="Rank by:", width=16).grid(row=0, column=0, sticky="w", padx=(0, 6), pady=3)
        ttk.Combobox(
            rank_row,
            textvariable=self.auto_rank_by,
            values=["Z-Score", "Raw Value", "Pay-up"],
            state="readonly",
            width=16,
        ).grid(row=0, column=1, sticky="ew", padx=(0, 14), pady=3)
        ttk.Label(rank_row, text="Top N BUY/SELL:", width=16).grid(row=0, column=2, sticky="w", padx=(0, 6), pady=3)
        ttk.Entry(rank_row, textvariable=self.auto_top_n, width=8).grid(row=0, column=3, sticky="w", pady=3)
        ttk.Label(rank_row, text="Min observations:", width=16).grid(row=1, column=0, sticky="w", padx=(0, 6), pady=(6, 3))
        ttk.Entry(rank_row, textvariable=self.auto_min_observations, width=8).grid(row=1, column=1, sticky="w", pady=(6, 3))
        ttk.Label(rank_row, text="Run profile:", width=16).grid(row=1, column=2, sticky="w", padx=(0, 6), pady=(6, 3))
        ttk.Combobox(
            rank_row,
            textvariable=self.auto_run_profile,
            values=[
                "Standard (Recommended)",
                "Full History",
                "Fast Active Charts",
                "Strict Parsed Only",
            ],
            state="readonly",
            width=24,
        ).grid(row=1, column=3, sticky="ew", pady=(6, 3))
        ttk.Label(
            rank_row,
            text=(
                f"Default {DEFAULT_MIN_OBSERVATIONS} observations. Standard scans 2019+ vintages, "
                "keeps full chart history, and includes partially parsed stories."
            ),
            wraplength=620,
            justify=tk.LEFT,
        ).grid(row=2, column=0, columnspan=4, sticky="ew", padx=(0, 0), pady=(4, 3))

        seasoning = ttk.Labelframe(left_ideas, text="Seasoning by Year", padding=16)
        seasoning.pack(fill='x', pady=(0, 10))
        self.auto_years = tk.StringVar()
        self.auto_year_min = tk.StringVar()
        self.auto_year_max = tk.StringVar()
        self._add_labeled_combo(
            seasoning,
            "Origination years (e.g. 2023,2024)",
            self.auto_years,
            "origination_years",
        )
        year_range = ttk.Frame(seasoning)
        year_range.pack(fill='x', pady=3)
        ttk.Label(year_range, text="Year range:", width=26).pack(side=tk.LEFT)
        ttk.Entry(year_range, textvariable=self.auto_year_min, width=10).pack(side=tk.LEFT, padx=5)
        ttk.Label(year_range, text="to").pack(side=tk.LEFT)
        ttk.Entry(year_range, textvariable=self.auto_year_max, width=10).pack(side=tk.LEFT, padx=5)
        ttk.Label(
            seasoning,
            text="Leave blank to use all parsed vintages. Active-universe focus is controlled in the ranking tab.",
            wraplength=420,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, fill='x', pady=(8, 0))

        coupon = ttk.Labelframe(left_ideas, text="Coupon Comparison", padding=16)
        coupon.pack(fill='x', pady=(8, 0))
        self.auto_coupons = tk.StringVar()
        self._add_labeled_combo(coupon, "Coupons (e.g. 4.5,5.0)", self.auto_coupons, "coupons")
        ttk.Label(
            coupon,
            text="Use comma-separated coupons to focus ranking and chart packages on specific coupon stories.",
            wraplength=420,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, fill='x', pady=(8, 0))

        comparisons = ttk.Labelframe(right_ideas, text="Story / Attribute Filters", padding=16)
        comparisons.pack(fill='both', expand=True)
        comparisons.columnconfigure(0, weight=1)
        self.auto_programs = tk.StringVar()
        self.auto_geos = tk.StringVar()
        self.auto_loan_balances = tk.StringVar()
        self.auto_story_families = tk.StringVar()
        self.auto_story_tags = tk.StringVar()
        self.auto_raw_stories = tk.StringVar()

        ttk.Label(
            comparisons,
            text="Optional: leave blank to scan everything, or narrow the run by story attributes detected from the dataset.",
            wraplength=390,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, fill='x', pady=(0, 12))

        filter_grid = ttk.Frame(comparisons)
        filter_grid.pack(fill='x', expand=False, pady=(0, 10))
        filter_grid.columnconfigure(0, weight=1)

        left_filters = ttk.Labelframe(filter_grid, text="Core Dimensions", padding=12)
        left_filters.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        left_filters.columnconfigure(0, weight=1)
        right_filters = ttk.Labelframe(filter_grid, text="Story Filters", padding=12)
        right_filters.grid(row=1, column=0, sticky="ew")
        right_filters.columnconfigure(0, weight=1)
        self._add_labeled_combo(left_filters, "Programs", self.auto_programs, "programs", label_width=18)
        self._add_labeled_combo(left_filters, "Geographies", self.auto_geos, "geographies", label_width=18)
        self._add_labeled_combo(left_filters, "Loan balances", self.auto_loan_balances, "loan_balance_buckets", label_width=18)
        self._add_labeled_combo(right_filters, "Story families", self.auto_story_families, "story_families", label_width=18)
        self._add_labeled_combo(right_filters, "Story tags", self.auto_story_tags, "story_tags", label_width=18)
        self._add_labeled_combo(right_filters, "Raw story names", self.auto_raw_stories, "raw_story_names", label_width=18)
        self._set_auto_filters_visible(False)

        overnight = ttk.Labelframe(tab_overnight, text="BUY/SELL Saved Configurations and Launcher", padding=14)
        overnight.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        overnight.columnconfigure(0, weight=1)
        self.auto_package_name = tk.StringVar()

        source_frame = ttk.Labelframe(overnight, text="Nightly Input Source", padding=10)
        source_frame.pack(fill='x', pady=(0, 8))
        self._add_automation_source_controls(source_frame, include_load_button=False)
        ttk.Label(
            source_frame,
            text=(
                "This tab only runs BUY/SELL idea-scan configs. "
                "Canned payup reports are managed in the Canned Reports tab. "
                "Latest-file mode is recommended for Task Scheduler."
            ),
            wraplength=900,
        ).pack(anchor=tk.W, pady=(6, 0))

        config_row = ttk.Frame(overnight)
        config_row.pack(fill='x', pady=4)
        ttk.Label(config_row, text="BUY/SELL config:", width=14).pack(side=tk.LEFT)
        self.cb_auto_configs = ttk.Combobox(
            config_row,
            textvariable=self.auto_config_name,
            state="readonly",
            values=[],
        )
        self.cb_auto_configs.pack(side=tk.LEFT, fill='x', expand=True, padx=(0, 8))
        self.cb_auto_configs.bind("<<ComboboxSelected>>", self.on_saved_config_selected)
        ttk.Button(config_row, text="Save Config", command=self.save_automation_config).pack(side=tk.LEFT, padx=4)
        ttk.Button(config_row, text="Load Config", command=self.load_selected_automation_config).pack(side=tk.LEFT, padx=4)

        package_row = ttk.Frame(overnight)
        package_row.pack(fill='x', pady=4)
        ttk.Label(package_row, text="Package name:", width=14).pack(side=tk.LEFT)
        ttk.Entry(package_row, textvariable=self.auto_package_name).pack(side=tk.LEFT, fill='x', expand=True, padx=5)
        ttk.Label(package_row, text="Blank = timestamped folder").pack(side=tk.LEFT, padx=(8, 0))

        actions = ttk.Frame(overnight)
        actions.pack(fill='x', pady=8)
        run_button_kwargs = {"width": 22, "style": "Primary.TButton"}
        self.btn_run_automation = ttk.Button(
            actions,
            text="RUN BUY/SELL SCAN",
            command=self.run_automation,
            **run_button_kwargs,
        )
        self.btn_run_automation.pack(side=tk.LEFT, ipady=2)
        ttk.Button(actions, text="OPEN OUTPUT FOLDER", command=self.open_automation_output).pack(side=tk.LEFT, padx=8)
        ttk.Label(actions, text=f"Configs: {self.config_store_path.parent}").pack(side=tk.LEFT, padx=(10, 0))

        meta_frame = ttk.Labelframe(overnight, text="Run Metadata", padding=10)
        meta_frame.pack(fill='both', expand=True, pady=(0, 2))

        meta_actions = ttk.Frame(meta_frame)
        meta_actions.pack(fill='x', pady=(0, 8))
        self.btn_copy_metadata = ttk.Button(
            meta_actions,
            text="Copy Metadata",
            command=self.copy_automation_metadata,
        )
        self.btn_copy_metadata.pack(side=tk.LEFT)
        self.btn_open_metadata_file = ttk.Button(
            meta_actions,
            text="Open Metadata File",
            command=self.open_automation_metadata_file,
            state="disabled",
        )
        self.btn_open_metadata_file.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(
            meta_actions,
            text="Tip: text is selectable; use Ctrl+C for selected snippets or the button for the full JSON.",
        ).pack(side=tk.LEFT, padx=(12, 0))

        meta_body = ttk.Frame(meta_frame)
        meta_body.pack(fill='both', expand=True)
        meta_scroll = ttk.Scrollbar(meta_body, orient="vertical")
        meta_scroll.pack(side=tk.RIGHT, fill='y')
        meta_xscroll = ttk.Scrollbar(meta_body, orient="horizontal")
        meta_xscroll.pack(side=tk.BOTTOM, fill='x')
        self.auto_metadata_text = tk.Text(meta_body, height=12, wrap='none')
        self.auto_metadata_text.pack(side=tk.LEFT, fill='both', expand=True)
        self.auto_metadata_text.configure(
            yscrollcommand=meta_scroll.set,
            xscrollcommand=meta_xscroll.set,
            cursor="xterm",
            exportselection=True,
        )
        meta_scroll.configure(command=self.auto_metadata_text.yview)
        meta_xscroll.configure(command=self.auto_metadata_text.xview)
        self._style_metadata_text()
        self._bind_mousewheel(self.auto_metadata_text)
        self._bind_horizontal_mousewheel(self.auto_metadata_text)
        self._make_metadata_text_readonly()
        self.auto_metadata_text.insert("1.0", "No runs yet.")

        self.setup_canned_reports_tab(tab_canned)
        self._sync_automation_source_controls()
        self.refresh_saved_configs()
        self.refresh_canned_reports()
        self._refresh_automation_run_label()

    def setup_canned_reports_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=0, minsize=300)
        parent.rowconfigure(1, weight=1)
        parent.rowconfigure(2, weight=0, minsize=135)

        self.canned_chart_requests = []
        self.canned_request_edit_index = None
        self.canned_filter_widgets = {}
        self.canned_filter_values = {}
        self.last_canned_output_path = None
        self.last_canned_metadata_path = None
        self.current_canned_metadata_file_path = None
        self.pending_canned_config_run_name = None
        self.canned_filter_values_source = None

        self.canned_config_name = tk.StringVar()
        self.canned_report_name = tk.StringVar(value="Nightly Payup Curves")
        self.canned_input_mode = tk.StringVar(value="fixed_file")
        self.canned_input = tk.StringVar()
        self.canned_input_folder = tk.StringVar()
        self.canned_input_pattern = tk.StringVar(value="*.xlsx")
        self.canned_output = tk.StringVar(value=str(resolve_default_overnight_output_dir().parent / "canned_reports"))
        self.canned_max_charts_per_request = tk.StringVar(value="50")
        self.canned_max_total_charts = tk.StringVar(value="250")
        self.canned_max_series_per_chart = tk.StringVar(value="50")
        self.canned_req_name = tk.StringVar()
        self.canned_req_chart_type = tk.StringVar(value="time_series")
        self.canned_req_programs = tk.StringVar()
        self.canned_req_coupons = tk.StringVar()
        self.canned_req_coupon_min = tk.StringVar()
        self.canned_req_coupon_max = tk.StringVar()
        self.canned_req_years = tk.StringVar()
        self.canned_req_year_min = tk.StringVar()
        self.canned_req_year_max = tk.StringVar()
        self.canned_req_geos = tk.StringVar()
        self.canned_req_loan_balances = tk.StringVar()
        self.canned_req_story_families = tk.StringVar()
        self.canned_req_story_tags = tk.StringVar()
        self.canned_req_raw_stories = tk.StringVar()
        self.canned_request_advanced_filters_visible = tk.BooleanVar(value=False)
        self.canned_setup_visible = tk.BooleanVar(value=False)

        top = ttk.Frame(parent)
        self.canned_top_grid = top
        top.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 8))
        top.columnconfigure(0, weight=3, minsize=520)
        top.columnconfigure(1, weight=4, minsize=620)
        top.rowconfigure(0, weight=1)

        list_frame = ttk.Labelframe(top, text="Saved Canned Reports", padding=10)
        list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        columns = ("workflow", "requests", "input_mode", "output")
        self.canned_reports_tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="tree headings",
            height=7,
            selectmode="browse",
        )
        self.canned_reports_tree.heading("#0", text="Report name")
        self.canned_reports_tree.heading("workflow", text="Workflow")
        self.canned_reports_tree.heading("requests", text="Reqs")
        self.canned_reports_tree.heading("input_mode", text="Input")
        self.canned_reports_tree.heading("output", text="Output folder")
        self.canned_reports_tree.column("#0", width=190, minwidth=150, stretch=True)
        self.canned_reports_tree.column("workflow", width=155, minwidth=130, stretch=False)
        self.canned_reports_tree.column("requests", width=55, minwidth=50, stretch=False, anchor=tk.CENTER)
        self.canned_reports_tree.column("input_mode", width=100, minwidth=90, stretch=False)
        self.canned_reports_tree.column("output", width=220, minwidth=160, stretch=True)
        self.canned_reports_tree.grid(row=0, column=0, sticky="nsew")
        canned_tree_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.canned_reports_tree.yview)
        canned_tree_scroll.grid(row=0, column=1, sticky="ns")
        self.canned_reports_tree.configure(yscrollcommand=canned_tree_scroll.set)
        self.canned_reports_tree.bind("<<TreeviewSelect>>", self.on_canned_report_selected)

        report_actions = ttk.Frame(list_frame)
        report_actions.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        for idx in range(6):
            report_actions.columnconfigure(idx, weight=1)
        ttk.Button(report_actions, text="New Canned Report", command=self.new_canned_report).grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=2)
        ttk.Button(report_actions, text="Edit Selected", command=self.edit_selected_canned_report).grid(row=0, column=1, sticky="ew", padx=4, pady=2)
        ttk.Button(report_actions, text="Duplicate Selected", command=self.duplicate_selected_canned_report).grid(row=0, column=2, sticky="ew", padx=4, pady=2)
        ttk.Button(report_actions, text="Delete Selected", command=self.delete_selected_canned_report).grid(row=0, column=3, sticky="ew", padx=4, pady=2)
        ttk.Button(report_actions, text="Load Example", command=self.load_example_canned_report).grid(row=0, column=4, sticky="ew", padx=4, pady=2)
        self.btn_canned_setup = ttk.Button(
            report_actions,
            text="Show Report Setup",
            command=self.toggle_canned_setup,
        )
        self.btn_canned_setup.grid(row=0, column=5, sticky="ew", padx=(4, 0), pady=2)

        setup = ttk.Labelframe(top, text="Report Setup", padding=8)
        self.canned_setup_frame = setup
        setup.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        setup.columnconfigure(1, weight=1)

        self._add_canned_labeled_entry(setup, "Config name:", self.canned_config_name, row=0)
        self._add_canned_labeled_entry(setup, "Report name:", self.canned_report_name, row=1)
        self._add_canned_source_controls(setup, start_row=2)
        self._add_canned_labeled_entry(setup, "Output folder:", self.canned_output, row=6, browse_command=self.browse_canned_output_dir)

        self.canned_safety_frame = ttk.Frame(setup)
        self.canned_safety_frame.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self.canned_safety_frame.columnconfigure(1, weight=1)
        self.canned_safety_frame.columnconfigure(3, weight=1)
        self.canned_safety_frame.columnconfigure(5, weight=1)
        ttk.Label(self.canned_safety_frame, text="Max/request:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(self.canned_safety_frame, textvariable=self.canned_max_charts_per_request, width=8).grid(row=0, column=1, sticky="w")
        ttk.Label(self.canned_safety_frame, text="Max total:").grid(row=0, column=2, sticky="w", padx=(14, 6))
        ttk.Entry(self.canned_safety_frame, textvariable=self.canned_max_total_charts, width=8).grid(row=0, column=3, sticky="w")
        ttk.Label(self.canned_safety_frame, text="Max series/chart:").grid(row=0, column=4, sticky="w", padx=(14, 6))
        ttk.Entry(self.canned_safety_frame, textvariable=self.canned_max_series_per_chart, width=8).grid(row=0, column=5, sticky="w")

        setup_actions = ttk.Frame(setup)
        setup_actions.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        ttk.Button(setup_actions, text="Load Values", command=self.load_canned_filter_values).pack(side=tk.LEFT)
        ttk.Button(setup_actions, text="Save Config", command=self.save_canned_report_config).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(setup_actions, text="Run Selected Now", command=self.run_selected_canned_report, style="Primary.TButton").pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(setup_actions, text="Open Output Folder", command=self.open_canned_output).pack(side=tk.LEFT, padx=(8, 0))
        self._set_canned_setup_visible(False)

        body = ttk.Frame(parent)
        self.canned_body_grid = body
        body.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        body.columnconfigure(0, weight=3, minsize=500)
        body.columnconfigure(1, weight=4, minsize=620)
        body.rowconfigure(0, weight=1)

        requests = ttk.Labelframe(body, text="Chart Requests", padding=10)
        requests.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        requests.columnconfigure(0, weight=1)
        requests.rowconfigure(0, weight=1)

        req_columns = ("type", "filters")
        self.canned_requests_tree = ttk.Treeview(
            requests,
            columns=req_columns,
            show="tree headings",
            height=10,
            selectmode="browse",
        )
        self.canned_requests_tree.heading("#0", text="Request name")
        self.canned_requests_tree.heading("type", text="Chart type")
        self.canned_requests_tree.heading("filters", text="Explicit filters")
        self.canned_requests_tree.column("#0", width=190, minwidth=150, stretch=True)
        self.canned_requests_tree.column("type", width=130, minwidth=110, stretch=False)
        self.canned_requests_tree.column("filters", width=300, minwidth=220, stretch=True)
        self.canned_requests_tree.grid(row=0, column=0, sticky="nsew")
        req_scroll = ttk.Scrollbar(requests, orient="vertical", command=self.canned_requests_tree.yview)
        req_scroll.grid(row=0, column=1, sticky="ns")
        self.canned_requests_tree.configure(yscrollcommand=req_scroll.set)
        self.canned_requests_tree.bind("<<TreeviewSelect>>", self.on_canned_request_selected)

        req_actions = ttk.Frame(requests)
        req_actions.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        for idx in range(4):
            req_actions.columnconfigure(idx, weight=1)
        ttk.Button(req_actions, text="New / Add Request", command=self.new_canned_chart_request).grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=2)
        ttk.Button(req_actions, text="Edit / Save Selected", command=self.edit_selected_canned_chart_request).grid(row=0, column=1, sticky="ew", padx=4, pady=2)
        ttk.Button(req_actions, text="Duplicate Chart Request", command=self.duplicate_selected_canned_chart_request).grid(row=0, column=2, sticky="ew", padx=4, pady=2)
        ttk.Button(req_actions, text="Delete Chart Request", command=self.delete_selected_canned_chart_request).grid(row=0, column=3, sticky="ew", padx=(4, 0), pady=2)

        editor = ttk.Labelframe(body, text="Chart Request Editor", padding=10)
        self.canned_request_editor_frame = editor
        editor.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        editor.columnconfigure(1, weight=1)
        editor.rowconfigure(10, weight=1)

        self._add_canned_labeled_entry(editor, "Name:", self.canned_req_name, row=0)
        ttk.Label(editor, text="Chart type:", width=22).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Combobox(
            editor,
            textvariable=self.canned_req_chart_type,
            values=["time_series", "latest_snapshot_curve"],
            state="readonly",
        ).grid(row=1, column=1, columnspan=2, sticky="ew", pady=3)

        self._add_canned_labeled_combo(editor, "Coupons:", self.canned_req_coupons, "coupons", row=2)

        coupon_range = ttk.Frame(editor)
        coupon_range.grid(row=3, column=1, columnspan=2, sticky="ew", pady=3)
        ttk.Label(editor, text="Coupon range:", width=22).grid(row=3, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(coupon_range, textvariable=self.canned_req_coupon_min, width=10).pack(side=tk.LEFT)
        ttk.Label(coupon_range, text="to").pack(side=tk.LEFT, padx=6)
        ttk.Entry(coupon_range, textvariable=self.canned_req_coupon_max, width=10).pack(side=tk.LEFT)

        self._add_canned_labeled_combo(editor, "Origination years:", self.canned_req_years, "origination_years", row=4)
        year_range = ttk.Frame(editor)
        year_range.grid(row=5, column=1, columnspan=2, sticky="ew", pady=3)
        ttk.Label(editor, text="Year range:", width=22).grid(row=5, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(year_range, textvariable=self.canned_req_year_min, width=10).pack(side=tk.LEFT)
        ttk.Label(year_range, text="to").pack(side=tk.LEFT, padx=6)
        ttk.Entry(year_range, textvariable=self.canned_req_year_max, width=10).pack(side=tk.LEFT)

        self._add_canned_labeled_combo(editor, "Geographies:", self.canned_req_geos, "geographies", row=6)
        self._add_canned_labeled_combo(editor, "Loan balances:", self.canned_req_loan_balances, "loan_balance_buckets", row=7)
        self._add_canned_labeled_combo(editor, "Story tags:", self.canned_req_story_tags, "story_tags", row=8)

        self.btn_canned_advanced_filters = ttk.Button(
            editor,
            text="Show Advanced Filters",
            command=self.toggle_canned_request_advanced_filters,
        )
        self.btn_canned_advanced_filters.grid(row=9, column=0, columnspan=3, sticky="w", pady=(8, 2))

        self.canned_request_advanced_frame = ttk.Frame(editor)
        self.canned_request_advanced_frame.grid(row=10, column=0, columnspan=3, sticky="ew", pady=(2, 0))
        self.canned_request_advanced_frame.columnconfigure(1, weight=1)
        self._add_canned_labeled_combo(self.canned_request_advanced_frame, "Programs:", self.canned_req_programs, "programs", row=0)
        self._add_canned_labeled_combo(self.canned_request_advanced_frame, "Story families:", self.canned_req_story_families, "story_families", row=1)
        self._add_canned_labeled_combo(self.canned_request_advanced_frame, "Raw story names:", self.canned_req_raw_stories, "raw_story_names", row=2)
        self.canned_request_advanced_frame.grid_remove()

        help_text = ttk.Label(
            editor,
            text="At least one explicit filter is required. Do not rely on the request name.",
            wraplength=620,
            justify=tk.LEFT,
        )
        help_text.grid(row=11, column=0, columnspan=3, sticky="ew", pady=(8, 3))

        editor_actions = ttk.Frame(editor)
        editor_actions.grid(row=12, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        self.btn_save_canned_chart_request = ttk.Button(
            editor_actions,
            text="Add Request to List",
            command=self.save_canned_chart_request,
        )
        self.btn_save_canned_chart_request.pack(side=tk.LEFT)
        ttk.Button(editor_actions, text="Clear Editor", command=self.clear_canned_chart_request_editor).pack(side=tk.LEFT, padx=(8, 0))
        self._set_canned_request_editor_visible(False)

        metadata = ttk.Labelframe(parent, text="Canned Report Metadata", padding=10)
        metadata.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))
        metadata.columnconfigure(0, weight=1)
        metadata.rowconfigure(1, weight=1)

        meta_actions = ttk.Frame(metadata)
        meta_actions.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(meta_actions, text="Copy Metadata", command=self.copy_canned_metadata).pack(side=tk.LEFT)
        self.btn_open_canned_metadata_file = ttk.Button(
            meta_actions,
            text="Open Metadata File",
            command=self.open_canned_metadata_file,
            state="disabled",
        )
        self.btn_open_canned_metadata_file.pack(side=tk.LEFT, padx=(8, 0))

        meta_body = ttk.Frame(metadata)
        meta_body.grid(row=1, column=0, sticky="nsew")
        meta_body.columnconfigure(0, weight=1)
        meta_body.rowconfigure(0, weight=1)
        meta_scroll = ttk.Scrollbar(meta_body, orient="vertical")
        meta_scroll.grid(row=0, column=1, sticky="ns")
        self.canned_metadata_text = tk.Text(meta_body, height=4, wrap="none")
        self.canned_metadata_text.grid(row=0, column=0, sticky="nsew")
        self.canned_metadata_text.configure(yscrollcommand=meta_scroll.set, cursor="xterm", exportselection=True)
        meta_scroll.configure(command=self.canned_metadata_text.yview)
        self._style_canned_metadata_text()
        self._bind_mousewheel(self.canned_metadata_text)
        self.canned_metadata_text.insert("1.0", "No canned report run yet.")

    def _apply_idea_run_profile_flags(self):
        profile = str(self.auto_run_profile.get() or "Standard (Recommended)").strip()
        flags = {
            "Standard (Recommended)": (True, True, True),
            "Full History": (False, True, True),
            "Fast Active Charts": (True, False, True),
            "Strict Parsed Only": (True, True, False),
        }.get(profile, (True, True, True))
        self.auto_use_default_focus.set(flags[0])
        self.auto_include_full_chart_history.set(flags[1])
        self.auto_include_parse_failures.set(flags[2])

    @staticmethod
    def _idea_run_profile_from_flags(use_default_focus, include_full_chart_history, include_parse_failures):
        if not include_parse_failures:
            return "Strict Parsed Only"
        if not use_default_focus:
            return "Full History"
        if not include_full_chart_history:
            return "Fast Active Charts"
        return "Standard (Recommended)"

    def toggle_auto_filters(self):
        self._set_auto_filters_visible(not self.auto_filters_visible.get())

    def _set_auto_filters_visible(self, visible):
        visible = bool(visible)
        if visible:
            self.ideas_grid.columnconfigure(1, weight=4, minsize=430)
            self.auto_filters_panel.grid()
            self.auto_filters_visible.set(True)
            self.btn_auto_filters.configure(text="HIDE OPTIONAL FILTERS")
        else:
            self.auto_filters_panel.grid_remove()
            self.ideas_grid.columnconfigure(1, weight=0, minsize=0)
            self.auto_filters_visible.set(False)
            self.btn_auto_filters.configure(text="SHOW OPTIONAL FILTERS")

    def _automation_filter_values_present(self):
        return any(
            str(var.get() or "").strip()
            for var in (
                self.auto_programs,
                self.auto_geos,
                self.auto_loan_balances,
                self.auto_story_families,
                self.auto_story_tags,
                self.auto_raw_stories,
            )
        )

    def toggle_canned_setup(self):
        self._set_canned_setup_visible(not self.canned_setup_visible.get())

    def _set_canned_setup_visible(self, visible):
        visible = bool(visible)
        if visible:
            self.canned_top_grid.columnconfigure(1, weight=4, minsize=620)
            self.canned_setup_frame.grid()
            self.canned_setup_visible.set(True)
            self.btn_canned_setup.configure(text="Hide Report Setup")
        else:
            self.canned_setup_frame.grid_remove()
            self.canned_top_grid.columnconfigure(1, weight=0, minsize=0)
            self.canned_setup_visible.set(False)
            self.btn_canned_setup.configure(text="Show Report Setup")

    def toggle_canned_request_advanced_filters(self):
        if self.canned_request_advanced_filters_visible.get():
            self.canned_request_advanced_frame.grid_remove()
            self.canned_request_advanced_filters_visible.set(False)
            self.btn_canned_advanced_filters.configure(text="Show Advanced Filters")
        else:
            self.canned_request_advanced_frame.grid()
            self.canned_request_advanced_filters_visible.set(True)
            self.btn_canned_advanced_filters.configure(text="Hide Advanced Filters")

    def _set_canned_request_advanced_filters_visible(self, visible):
        currently_visible = bool(self.canned_request_advanced_filters_visible.get())
        if bool(visible) != currently_visible:
            self.toggle_canned_request_advanced_filters()

    def _set_canned_request_editor_visible(self, visible):
        visible = bool(visible)
        if visible:
            self.canned_body_grid.columnconfigure(1, weight=4, minsize=620)
            self.canned_request_editor_frame.grid()
        else:
            self.canned_request_editor_frame.grid_remove()
            self.canned_body_grid.columnconfigure(1, weight=0, minsize=0)

    def _add_automation_source_controls(self, parent, include_load_button=False):
        mode_row = ttk.Frame(parent)
        mode_row.pack(fill='x', pady=(0, 6))
        ttk.Label(mode_row, text="Input mode:", width=26).pack(side=tk.LEFT)
        ttk.Radiobutton(
            mode_row,
            text="Fixed file path",
            value="fixed_file",
            variable=self.auto_input_mode,
            command=self._sync_automation_source_controls,
        ).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Radiobutton(
            mode_row,
            text="Latest file from folder",
            value="latest_file",
            variable=self.auto_input_mode,
            command=self._sync_automation_source_controls,
        ).pack(side=tk.LEFT)
        if include_load_button:
            self.btn_load_filter_values = ttk.Button(
                mode_row,
                text="Load Values",
                command=self.load_automation_filter_values,
            )
            self.btn_load_filter_values.pack(side=tk.LEFT, padx=(16, 0))

        fixed_row = ttk.Frame(parent)
        fixed_row.pack(fill='x', pady=3)
        ttk.Label(fixed_row, text="Fixed dataset file:", width=26).pack(side=tk.LEFT)
        fixed_entry = ttk.Entry(fixed_row, textvariable=self.auto_input)
        fixed_entry.pack(side=tk.LEFT, fill='x', expand=True, padx=5)
        fixed_browse = ttk.Button(fixed_row, text="Browse File", command=self.browse_automation_input)
        fixed_browse.pack(side=tk.LEFT)
        self.auto_fixed_source_widgets.extend([fixed_entry, fixed_browse])

        latest_row = ttk.Frame(parent)
        latest_row.pack(fill='x', pady=3)
        ttk.Label(latest_row, text="Latest input folder:", width=26).pack(side=tk.LEFT)
        folder_entry = ttk.Entry(latest_row, textvariable=self.auto_input_folder)
        folder_entry.pack(side=tk.LEFT, fill='x', expand=True, padx=5)
        folder_browse = ttk.Button(latest_row, text="Browse Folder", command=self.browse_automation_input_folder)
        folder_browse.pack(side=tk.LEFT)
        self.auto_latest_source_widgets.extend([folder_entry, folder_browse])

        pattern_row = ttk.Frame(parent)
        pattern_row.pack(fill='x', pady=3)
        ttk.Label(pattern_row, text="File pattern:", width=26).pack(side=tk.LEFT)
        pattern_entry = ttk.Entry(pattern_row, textvariable=self.auto_input_pattern, width=20)
        pattern_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(pattern_row, text="Example: *.xlsx or BBG PUs*.xlsx").pack(side=tk.LEFT, padx=(8, 0))
        self.auto_latest_source_widgets.append(pattern_entry)

    def _add_labeled_entry(self, parent, label, var):
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=3)
        ttk.Label(row, text=label, width=32).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=var).pack(side=tk.LEFT, fill='x', expand=True, padx=5)

    def _add_labeled_combo(self, parent, label, var, key, label_width=32):
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=4)
        row.columnconfigure(1, weight=1)
        ttk.Label(row, text=label, width=label_width).grid(row=0, column=0, sticky="w", padx=(0, 8))
        combo = ttk.Combobox(row, textvariable=var, values=[], state="normal")
        combo.grid(row=0, column=1, sticky="ew")
        self.auto_filter_widgets[key] = combo
        return combo

    def _add_canned_labeled_entry(self, parent, label, var, row, browse_command=None):
        ttk.Label(parent, text=label, width=22).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", pady=2)
        if browse_command:
            ttk.Button(parent, text="Browse", command=browse_command).grid(row=row, column=2, sticky="e", padx=(8, 0), pady=2)
        else:
            ttk.Label(parent, text="").grid(row=row, column=2, sticky="e", padx=(8, 0), pady=2)

    def _add_canned_labeled_combo(self, parent, label, var, key, row):
        ttk.Label(parent, text=label, width=22).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
        combo = ttk.Combobox(parent, textvariable=var, values=[], state="normal")
        combo.grid(row=row, column=1, columnspan=2, sticky="ew", pady=2)
        self.canned_filter_widgets[key] = combo
        return combo

    def _add_canned_source_controls(self, parent, start_row):
        ttk.Label(parent, text="Input mode:", width=22).grid(row=start_row, column=0, sticky="w", padx=(0, 8), pady=2)
        mode_frame = ttk.Frame(parent)
        mode_frame.grid(row=start_row, column=1, columnspan=2, sticky="ew", pady=2)
        ttk.Radiobutton(
            mode_frame,
            text="Fixed file path",
            value="fixed_file",
            variable=self.canned_input_mode,
            command=self._sync_canned_source_controls,
        ).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Radiobutton(
            mode_frame,
            text="Latest file from folder",
            value="latest_file",
            variable=self.canned_input_mode,
            command=self._sync_canned_source_controls,
        ).pack(side=tk.LEFT)

        self.canned_fixed_source_widgets = []
        self.canned_latest_source_widgets = []
        fixed_label = ttk.Label(parent, text="Fixed input file:", width=22)
        fixed_label.grid(row=start_row + 1, column=0, sticky="w", padx=(0, 8), pady=2)
        fixed_entry = ttk.Entry(parent, textvariable=self.canned_input)
        fixed_entry.grid(row=start_row + 1, column=1, sticky="ew", pady=2)
        fixed_button = ttk.Button(parent, text="Browse File", command=self.browse_canned_input)
        fixed_button.grid(row=start_row + 1, column=2, sticky="e", padx=(8, 0), pady=2)
        self.canned_fixed_source_widgets.extend([fixed_label, fixed_entry, fixed_button])

        folder_label = ttk.Label(parent, text="Latest input folder:", width=22)
        folder_label.grid(row=start_row + 2, column=0, sticky="w", padx=(0, 8), pady=2)
        folder_entry = ttk.Entry(parent, textvariable=self.canned_input_folder)
        folder_entry.grid(row=start_row + 2, column=1, sticky="ew", pady=2)
        folder_button = ttk.Button(parent, text="Browse Folder", command=self.browse_canned_input_folder)
        folder_button.grid(row=start_row + 2, column=2, sticky="e", padx=(8, 0), pady=2)
        self.canned_latest_source_widgets.extend([folder_label, folder_entry, folder_button])

        pattern_label = ttk.Label(parent, text="File pattern:", width=22)
        pattern_label.grid(row=start_row + 3, column=0, sticky="w", padx=(0, 8), pady=2)
        pattern_entry = ttk.Entry(parent, textvariable=self.canned_input_pattern)
        pattern_entry.grid(row=start_row + 3, column=1, sticky="ew", pady=2)
        pattern_hint = ttk.Label(parent, text="Example: *.xlsx")
        pattern_hint.grid(row=start_row + 3, column=2, sticky="w", padx=(8, 0), pady=2)
        self.canned_latest_source_widgets.extend([pattern_label, pattern_entry, pattern_hint])
        self._sync_canned_source_controls()

    def _style_canned_metadata_text(self):
        style = ttk.Style()
        background = style.lookup("TFrame", "background") or "#233646"
        foreground = style.lookup("TLabel", "foreground") or "#f2f6fa"
        self.canned_metadata_text.configure(
            background=background,
            foreground=foreground,
            insertbackground=foreground,
            selectbackground="#4f8fd8",
            selectforeground="#ffffff",
            relief="flat",
            borderwidth=0,
            padx=8,
            pady=8,
        )

    def _bind_mousewheel(self, widget):
        widget.bind("<MouseWheel>", lambda event: self._on_mousewheel_scroll(event, widget), add="+")
        widget.bind("<Button-4>", lambda event: self._on_mousewheel_scroll(event, widget), add="+")
        widget.bind("<Button-5>", lambda event: self._on_mousewheel_scroll(event, widget), add="+")

    def _bind_horizontal_mousewheel(self, widget):
        widget.bind("<Shift-MouseWheel>", lambda event: self._on_horizontal_mousewheel_scroll(event, widget), add="+")

    @staticmethod
    def _on_mousewheel_scroll(event, widget):
        if getattr(event, "num", None) == 4:
            units = -3
        elif getattr(event, "num", None) == 5:
            units = 3
        else:
            wheel_steps = event.delta / 120 if event.delta else 0
            if abs(wheel_steps) < 1 and wheel_steps:
                units = -1 if wheel_steps > 0 else 1
            else:
                units = -1 * int(wheel_steps) if wheel_steps else 0
        if units:
            widget.yview_scroll(units, "units")
        return "break"

    @staticmethod
    def _on_horizontal_mousewheel_scroll(event, widget):
        wheel_steps = event.delta / 120 if event.delta else 0
        if abs(wheel_steps) < 1 and wheel_steps:
            units = -1 if wheel_steps > 0 else 1
        else:
            units = -1 * int(wheel_steps) if wheel_steps else 0
        if units:
            widget.xview_scroll(units, "units")
        return "break"

    def _style_metadata_text(self):
        style = ttk.Style()
        background = style.lookup("TFrame", "background") or "#233646"
        foreground = style.lookup("TLabel", "foreground") or "#f2f6fa"
        self.auto_metadata_text.configure(
            background=background,
            foreground=foreground,
            insertbackground=foreground,
            selectbackground="#4f8fd8",
            selectforeground="#ffffff",
            relief="flat",
            borderwidth=0,
            padx=8,
            pady=8,
        )

    def _make_metadata_text_readonly(self):
        self.auto_metadata_text.bind("<Control-a>", self._select_all_metadata_text, add="+")
        self.auto_metadata_text.bind("<Control-A>", self._select_all_metadata_text, add="+")
        self.auto_metadata_text.bind("<<Paste>>", self._block_text_edit, add="+")
        self.auto_metadata_text.bind("<<Cut>>", self._block_text_edit, add="+")
        self.auto_metadata_text.bind("<BackSpace>", self._block_text_edit, add="+")
        self.auto_metadata_text.bind("<Delete>", self._block_text_edit, add="+")
        self.auto_metadata_text.bind("<KeyPress>", self._block_metadata_typing, add="+")

    @staticmethod
    def _block_text_edit(_event=None):
        return "break"

    def _select_all_metadata_text(self, _event=None):
        self.auto_metadata_text.tag_add(tk.SEL, "1.0", tk.END)
        self.auto_metadata_text.mark_set(tk.INSERT, "1.0")
        self.auto_metadata_text.see(tk.INSERT)
        return "break"

    def _block_metadata_typing(self, event):
        ctrl_pressed = bool(getattr(event, "state", 0) & 0x4)
        keysym = str(getattr(event, "keysym", ""))
        lower_key = keysym.lower()
        navigation_keys = {
            "left",
            "right",
            "up",
            "down",
            "home",
            "end",
            "prior",
            "next",
            "shift_l",
            "shift_r",
            "control_l",
            "control_r",
            "alt_l",
            "alt_r",
            "escape",
        }
        if ctrl_pressed and lower_key in {"a", "c"}:
            return None
        if lower_key in navigation_keys:
            return None
        return "break"



    def _sync_canned_source_controls(self):
        latest = self.canned_input_mode.get() == "latest_file"
        fixed_state = "disabled" if latest else "normal"
        latest_state = "normal" if latest else "disabled"
        for widget in getattr(self, "canned_fixed_source_widgets", []):
            try:
                if latest:
                    widget.grid_remove()
                else:
                    widget.grid()
                widget.configure(state=fixed_state)
            except Exception:
                pass
        for widget in getattr(self, "canned_latest_source_widgets", []):
            try:
                if latest:
                    widget.grid()
                else:
                    widget.grid_remove()
                widget.configure(state=latest_state)
            except Exception:
                pass
        if not self.canned_input_pattern.get().strip():
            self.canned_input_pattern.set("*.xlsx")

    def browse_canned_input(self):
        path = filedialog.askopenfilename(
            title="Choose canned report input file",
            filetypes=[("Excel/CSV files", "*.xlsx *.xls *.csv"), ("All files", "*.*")],
        )
        if path:
            self.canned_input_mode.set("fixed_file")
            self.canned_input.set(path)
            self._sync_canned_source_controls()
            self.load_canned_filter_values()

    def browse_canned_input_folder(self):
        path = filedialog.askdirectory(title="Choose latest-file input folder")
        if path:
            self.canned_input_mode.set("latest_file")
            self.canned_input_folder.set(path)
            self._sync_canned_source_controls()
            self.load_canned_filter_values()

    def browse_canned_output_dir(self):
        path = filedialog.askdirectory(title="Choose canned report output folder")
        if path:
            self.canned_output.set(path)

    def _resolve_canned_input_path(self):
        if self.canned_input_mode.get() == "latest_file":
            folder_raw = self.canned_input_folder.get().strip()
            if not folder_raw:
                raise ValueError("Choose the input folder for latest-file mode.")
            return resolve_latest_input_file(Path(folder_raw), self.canned_input_pattern.get().strip() or "*.xlsx")
        input_raw = self.canned_input.get().strip()
        if not input_raw:
            raise ValueError("Choose a fixed CSV/XLSX input file.")
        return Path(input_raw)

    def load_canned_filter_values(self):
        try:
            source_path = self._resolve_canned_input_path()
        except Exception as exc:
            messagebox.showwarning("Input Needed", str(exc))
            return
        if self._busy:
            messagebox.showwarning("Busy", "Wait for the current operation to finish first.")
            return
        self._busy = True
        self.canned_filter_values_source = str(source_path)
        self.status.set(f"Loading canned report values from {source_path.name}...")
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self.progress_text.set("...")
        threading.Thread(target=self.work_load_canned_filter_values, daemon=True).start()

    def work_load_canned_filter_values(self):
        try:
            input_path = self._resolve_canned_input_path()
            normalized, diagnostics = load_and_normalize_dataset(input_path)
            values = self._extract_automation_filter_values(normalized)
            self.root.after(0, lambda: self.apply_canned_filter_values(values, diagnostics, input_path))
        except Exception as exc:
            self.logger.exception("Canned report filter value loading failed")
            self.root.after(0, lambda: self.finish_canned_filter_load(error=exc))

    def apply_canned_filter_values(self, values, diagnostics, input_path=None):
        self.canned_filter_values = values
        for key, widget in self.canned_filter_widgets.items():
            widget["values"] = values.get(key, [])
        summary = {
            "message": "Dataset values loaded into Canned Reports dropdowns.",
            "resolved_input_file": str(input_path) if input_path else None,
            "detected_layout": diagnostics.get("source_layout"),
            "selected_sheet": diagnostics.get("selected_sheet") or diagnostics.get("sheet_name"),
            "normalized_rows": diagnostics.get("normalized_rows"),
            "available_values": {key: len(val) for key, val in values.items()},
            "manual_override": "Dropdowns remain editable; type comma-separated values when needed.",
        }
        self.update_canned_metadata(summary)
        self.finish_canned_filter_load()

    def _maybe_auto_load_canned_filter_values(self):
        if self._busy:
            return
        try:
            source_path = self._resolve_canned_input_path()
        except Exception:
            return
        if not Path(source_path).exists():
            return
        if self.canned_filter_values and self.canned_filter_values_source == str(source_path):
            return
        self.load_canned_filter_values()

    def finish_canned_filter_load(self, error=None):
        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=100)
        self.progress["value"] = 0
        self.progress_text.set("0%")
        self._busy = False
        if error is not None:
            self.status.set(self._default_status_text)
            messagebox.showerror("Load Failed", f"{error}\n\nSee log for details:\n{self.log_path}")
            return
        self.status.set("Canned report filter values loaded.")

    def refresh_canned_reports(self, select_name=None):
        if not hasattr(self, "canned_reports_tree"):
            return
        self.saved_configs = self._load_saved_configs_map()
        seeded = self._seed_default_canned_report_if_needed(self.saved_configs)
        selected = select_name or self._selected_canned_report_name()
        if seeded and not selected:
            selected = "Nightly Payup Curves"
        for item in self.canned_reports_tree.get_children():
            self.canned_reports_tree.delete(item)
        for name, config in sorted(self.saved_configs.items()):
            _, workflow = self._workflow_label_for_config(config)
            if workflow != "payup_curve_pack":
                continue
            requests = config.get("chart_requests") if isinstance(config.get("chart_requests"), list) else []
            input_mode = str(config.get("input_mode") or ("latest_file" if config.get("input_dir") else "fixed_file"))
            output = str(config.get("output_dir") or "")
            self.canned_reports_tree.insert(
                "",
                tk.END,
                iid=name,
                text=str(config.get("report_name") or name),
                values=(workflow, len(requests), input_mode, output),
            )
        items = list(self.canned_reports_tree.get_children())
        if selected in items:
            target = selected
        elif items:
            target = str(items[0])
        else:
            target = ""
        if target:
            self.canned_reports_tree.selection_set(target)
            self.canned_reports_tree.focus(target)
            config = self.saved_configs.get(target)
            if config:
                self._apply_canned_config_to_form(target, config)
        else:
            self.update_canned_metadata(
                {"message": "No canned reports saved yet. Create one or load the example."}
            )

    def _seed_default_canned_report_if_needed(self, configs):
        if any(self._workflow_label_for_config(config)[1] == "payup_curve_pack" for config in configs.values()):
            return False
        if "Nightly Payup Curves" in configs:
            return False
        configs["Nightly Payup Curves"] = self._default_canned_report_config()
        self._write_saved_configs_map(configs)
        return True

    def _default_canned_report_config(self):
        return {
            "workflow": "payup_curve_pack",
            "input_mode": "latest_file",
            "input_dir": "D:/MBS_Nightly_Input",
            "input_pattern": "*.xlsx",
            "output_dir": str(resolve_default_overnight_output_dir().parent / "canned_reports"),
            "report_name": "Nightly Payup Curves",
            "max_charts_per_request": 50,
            "max_total_charts": 250,
            "max_series_per_chart": 50,
            "chart_requests": [
                {
                    "name": "LB125 2022 All Coupons",
                    "chart_type": "time_series",
                    "programs": ["FNCL"],
                    "loan_balance_buckets": ["LB125"],
                    "origination_years": [2022],
                    "coupons": "all",
                },
                {
                    "name": "LB225 1.5 Through 7.0 Snapshot",
                    "chart_type": "latest_snapshot_curve",
                    "programs": ["FNCL"],
                    "loan_balance_buckets": ["LB225"],
                    "origination_years": [2022],
                    "coupon_min": 1.5,
                    "coupon_max": 7.0,
                },
                {
                    "name": "NY Coupon Curve",
                    "chart_type": "latest_snapshot_curve",
                    "programs": ["FNCL"],
                    "geographies": ["NY"],
                    "origination_years": [2022],
                    "coupon_min": 1.5,
                    "coupon_max": 7.0,
                },
                {
                    "name": "LTV Time Series",
                    "chart_type": "time_series",
                    "programs": ["FNCL"],
                    "origination_years": [2022],
                    "coupons": "all",
                    "story_tags": ["LTV"],
                },
            ],
            "gui_schema_version": 2,
            "example_config": True,
        }

    def load_example_canned_report(self):
        self.saved_configs = self._load_saved_configs_map()
        existing = self.saved_configs.get("Nightly Payup Curves")
        if existing is not None:
            _, workflow = self._workflow_label_for_config(existing)
            if workflow == "payup_curve_pack":
                overwrite = messagebox.askyesno(
                    "Reload Example",
                    (
                        "Reload the built-in example canned report?\n\n"
                        "This will replace the chart requests in 'Nightly Payup Curves' with the latest example "
                        "(FNCL + 2022 Vintage filters), while keeping your input/output folders and safety limits."
                    ),
                )
                if not overwrite:
                    self.refresh_canned_reports(select_name="Nightly Payup Curves")
                    return
                self.saved_configs["Nightly Payup Curves"] = self._refreshed_example_canned_report(existing)
                self._write_saved_configs_map(self.saved_configs)
                self.refresh_saved_configs(select_name="Nightly Payup Curves")
                self.refresh_canned_reports(select_name="Nightly Payup Curves")
                messagebox.showinfo(
                    "Example Reloaded",
                    "Example canned report 'Nightly Payup Curves' was reloaded with the latest chart requests.",
                )
                return
            messagebox.showwarning(
                "Name Already Exists",
                "A config named 'Nightly Payup Curves' already exists and will not be overwritten. "
                "Rename that config or create a new canned report manually.",
            )
            return
        self.saved_configs["Nightly Payup Curves"] = self._default_canned_report_config()
        self._write_saved_configs_map(self.saved_configs)
        self.refresh_saved_configs(select_name="Nightly Payup Curves")
        self.refresh_canned_reports(select_name="Nightly Payup Curves")
        messagebox.showinfo("Example Loaded", "Example canned report 'Nightly Payup Curves' was added.")

    def _refreshed_example_canned_report(self, existing):
        """Replace example chart requests while preserving machine-specific paths."""

        updated = self._default_canned_report_config()
        for key in (
            "input_mode",
            "input_path",
            "input_dir",
            "input_pattern",
            "resolved_input_path",
            "output_dir",
            "max_charts_per_request",
            "max_total_charts",
            "max_series_per_chart",
        ):
            if key in existing and existing.get(key) not in (None, ""):
                updated[key] = existing[key]
        updated["example_config"] = True
        return updated

    def _selected_canned_report_name(self):
        if not hasattr(self, "canned_reports_tree"):
            return ""
        selection = self.canned_reports_tree.selection()
        if selection:
            return str(selection[0])
        return self.canned_config_name.get().strip()

    def on_canned_report_selected(self, _event=None):
        name = self._selected_canned_report_name()
        if not name:
            return
        config = self.saved_configs.get(name)
        if not config:
            self.saved_configs = self._load_saved_configs_map()
            config = self.saved_configs.get(name)
        if config:
            self._apply_canned_config_to_form(name, config)

    def edit_selected_canned_report(self):
        self.on_canned_report_selected()
        self._set_canned_setup_visible(True)

    def new_canned_report(self):
        self._set_canned_setup_visible(True)
        self.canned_config_name.set("")
        self.canned_report_name.set("New Payup Curve Pack")
        self.canned_input_mode.set("fixed_file")
        self.canned_input.set("")
        self.canned_input_folder.set("")
        self.canned_input_pattern.set("*.xlsx")
        self.canned_output.set(str(resolve_default_overnight_output_dir().parent / "canned_reports"))
        self.canned_max_charts_per_request.set("50")
        self.canned_max_total_charts.set("250")
        self.canned_max_series_per_chart.set("50")
        self.canned_chart_requests = []
        self.canned_request_edit_index = None
        self.refresh_canned_chart_requests()
        self.clear_canned_chart_request_editor()
        self._sync_canned_source_controls()
        self.update_canned_metadata({"message": "New canned report draft created. Add at least one chart request, then Save Config."})

    def duplicate_selected_canned_report(self):
        name = self._selected_canned_report_name()
        if not name or name not in self.saved_configs:
            messagebox.showwarning("No Selection", "Select a canned report to duplicate.")
            return
        base = copy.deepcopy(self.saved_configs[name])
        new_name = self._unique_config_name(f"{name} Copy")
        base["report_name"] = f"{base.get('report_name') or name} Copy"
        self.saved_configs[new_name] = base
        self._write_saved_configs_map(self.saved_configs)
        self.refresh_saved_configs()
        self.refresh_canned_reports(select_name=new_name)
        self._apply_canned_config_to_form(new_name, base)
        self._set_canned_setup_visible(True)
        self.update_canned_metadata({"message": f"Duplicated canned report '{name}' as '{new_name}'."})

    def delete_selected_canned_report(self):
        name = self._selected_canned_report_name()
        if not name or name not in self.saved_configs:
            messagebox.showwarning("No Selection", "Select a canned report to delete.")
            return
        if not messagebox.askyesno("Delete Canned Report", f"Delete canned report config '{name}'?"):
            return
        config = self.saved_configs.get(name, {})
        _, workflow = self._workflow_label_for_config(config)
        if workflow != "payup_curve_pack":
            messagebox.showwarning("Cannot Delete Here", "Only payup_curve_pack canned reports can be deleted from this tab.")
            return
        del self.saved_configs[name]
        self._write_saved_configs_map(self.saved_configs)
        self.refresh_saved_configs()
        self.refresh_canned_reports()
        self.new_canned_report()
        self._set_canned_setup_visible(False)
        self.update_canned_metadata({"message": f"Deleted canned report config '{name}'."})

    def _unique_config_name(self, base_name):
        name = base_name.strip() or "Canned Report"
        if name not in self.saved_configs:
            return name
        index = 2
        while f"{name} {index}" in self.saved_configs:
            index += 1
        return f"{name} {index}"

    def _apply_canned_config_to_form(self, name, config):
        self.canned_config_name.set(name)
        self.canned_report_name.set(str(config.get("report_name") or name))
        input_mode = str(config.get("input_mode") or "").strip().lower()
        if input_mode == "latest_file" or config.get("input_dir"):
            self.canned_input_mode.set("latest_file")
            self.canned_input_folder.set(str(config.get("input_dir", "")))
            self.canned_input_pattern.set(str(config.get("input_pattern", "*.xlsx") or "*.xlsx"))
            self.canned_input.set(str(config.get("resolved_input_path") or config.get("input_path") or ""))
        else:
            self.canned_input_mode.set("fixed_file")
            self.canned_input.set(str(config.get("input_path", "")))
            self.canned_input_folder.set("")
            self.canned_input_pattern.set("*.xlsx")
        self._sync_canned_source_controls()
        self.canned_output.set(str(config.get("output_dir") or resolve_default_overnight_output_dir().parent / "canned_reports"))
        self.canned_max_charts_per_request.set(str(config.get("max_charts_per_request", 50)))
        self.canned_max_total_charts.set(str(config.get("max_total_charts", 250)))
        self.canned_max_series_per_chart.set(str(config.get("max_series_per_chart", 50)))
        requests = config.get("chart_requests") if isinstance(config.get("chart_requests"), list) else []
        self.canned_chart_requests = [copy.deepcopy(req) for req in requests if isinstance(req, dict)]
        self.canned_request_edit_index = None
        self.refresh_canned_chart_requests()
        self.clear_canned_chart_request_editor()
        self.update_canned_metadata(
            {
                "message": "Canned payup report loaded.",
                "config_name": name,
                "workflow": "payup_curve_pack",
                "report_name": self.canned_report_name.get(),
                "chart_request_count": len(self.canned_chart_requests),
            }
        )
        self.root.after(100, self._maybe_auto_load_canned_filter_values)

    def _collect_canned_config_from_form(self):
        name = self.canned_config_name.get().strip()
        if not name:
            raise ValueError("Config name is required.")
        report_name = self.canned_report_name.get().strip() or name
        max_per = self._parse_optional_int(self.canned_max_charts_per_request.get()) or 50
        max_total = self._parse_optional_int(self.canned_max_total_charts.get()) or 250
        max_series = self._parse_optional_int(self.canned_max_series_per_chart.get()) or 50
        if max_per <= 0 or max_total <= 0 or max_series <= 0:
            raise ValueError("Safety limits must be greater than zero.")
        if not self.canned_chart_requests:
            raise ValueError("Add at least one chart request before saving a canned report.")
        for request in self.canned_chart_requests:
            self._validate_canned_chart_request(request)

        payload = {
            "workflow": "payup_curve_pack",
            "output_dir": self.canned_output.get().strip() or str(resolve_default_overnight_output_dir().parent / "canned_reports"),
            "report_name": report_name,
            "max_charts_per_request": max_per,
            "max_total_charts": max_total,
            "max_series_per_chart": max_series,
            "chart_requests": copy.deepcopy(self.canned_chart_requests),
            "gui_schema_version": 2,
        }
        if self.canned_input_mode.get() == "latest_file":
            folder_raw = self.canned_input_folder.get().strip()
            if not folder_raw:
                raise ValueError("Choose an input folder before saving latest-file mode.")
            payload.update(
                {
                    "input_mode": "latest_file",
                    "input_dir": folder_raw,
                    "input_pattern": self.canned_input_pattern.get().strip() or "*.xlsx",
                }
            )
        else:
            input_raw = self.canned_input.get().strip()
            if not input_raw:
                raise ValueError("Choose a fixed input file before saving.")
            payload.update({"input_mode": "fixed_file", "input_path": input_raw})
        return name, payload

    def save_canned_report_config(self):
        try:
            name, payload = self._collect_canned_config_from_form()
            self.saved_configs = self._load_saved_configs_map()
            existing = self.saved_configs.get(name)
            if existing:
                _, workflow = self._workflow_label_for_config(existing)
                if workflow != "payup_curve_pack":
                    raise ValueError(
                        f"Config name '{name}' already belongs to workflow '{workflow}'. "
                        "Choose a different name so existing BUY/SELL configs are not corrupted."
                    )
            self.saved_configs[name] = payload
            self._write_saved_configs_map(self.saved_configs)
            self.refresh_saved_configs(select_name=name)
            self.refresh_canned_reports(select_name=name)
            self.update_canned_metadata({"message": f"Canned report config '{name}' saved.", "config": payload})
            messagebox.showinfo("Saved", f"Canned report config '{name}' saved.")
        except Exception as exc:
            messagebox.showerror("Save Failed", str(exc))

    def refresh_canned_chart_requests(self):
        if not hasattr(self, "canned_requests_tree"):
            return
        for item in self.canned_requests_tree.get_children():
            self.canned_requests_tree.delete(item)
        for index, request in enumerate(self.canned_chart_requests):
            self.canned_requests_tree.insert(
                "",
                tk.END,
                iid=str(index),
                text=str(request.get("name") or f"Request {index + 1}"),
                values=(request.get("chart_type", "time_series"), self._summarize_canned_request_filters(request)),
            )

    def _selected_canned_request_index(self):
        selection = self.canned_requests_tree.selection() if hasattr(self, "canned_requests_tree") else []
        if not selection:
            return None
        try:
            return int(selection[0])
        except Exception:
            return None

    def on_canned_request_selected(self, _event=None):
        return

    def _canned_request_editor_is_visible(self):
        return bool(
            hasattr(self, "canned_request_editor_frame")
            and self.canned_request_editor_frame.winfo_ismapped()
        )

    def _canned_request_editor_has_filter_input(self):
        filter_vars = (
            self.canned_req_programs,
            self.canned_req_coupons,
            self.canned_req_coupon_min,
            self.canned_req_coupon_max,
            self.canned_req_years,
            self.canned_req_year_min,
            self.canned_req_year_max,
            self.canned_req_geos,
            self.canned_req_loan_balances,
            self.canned_req_story_families,
            self.canned_req_story_tags,
            self.canned_req_raw_stories,
        )
        return any(var.get().strip() for var in filter_vars)

    def new_canned_chart_request(self):
        if self._canned_request_editor_is_visible() and self._canned_request_editor_has_filter_input():
            # Users naturally click "Add" after filling the form. Treat that as save,
            # rather than clearing their draft and making the request appear to vanish.
            self.save_canned_chart_request()
            return
        self.clear_canned_chart_request_editor(hide_editor=False)
        self.canned_request_edit_index = None
        self.canned_req_name.set(f"Chart Request {len(self.canned_chart_requests) + 1}")
        if hasattr(self, "btn_save_canned_chart_request"):
            self.btn_save_canned_chart_request.configure(text="Add Request to List")
        self._set_canned_request_editor_visible(True)

    def edit_selected_canned_chart_request(self):
        index = self._selected_canned_request_index()
        if index is None or not (0 <= index < len(self.canned_chart_requests)):
            messagebox.showwarning("No Selection", "Select a chart request to edit.")
            return
        if (
            self._canned_request_editor_is_visible()
            and self.canned_request_edit_index == index
        ):
            # If the selected request is already open in the editor, a second click
            # should save the changes instead of reloading the old values.
            self.save_canned_chart_request()
            return
        self._apply_canned_request_to_editor(index, self.canned_chart_requests[index])
        self._set_canned_request_editor_visible(True)

    def duplicate_selected_canned_chart_request(self):
        index = self._selected_canned_request_index()
        if index is None or not (0 <= index < len(self.canned_chart_requests)):
            messagebox.showwarning("No Selection", "Select a chart request to duplicate.")
            return
        request = copy.deepcopy(self.canned_chart_requests[index])
        request["name"] = f"{request.get('name') or 'Chart Request'} Copy"
        self.canned_chart_requests.insert(index + 1, request)
        self.refresh_canned_chart_requests()
        self.canned_requests_tree.selection_set(str(index + 1))
        self._apply_canned_request_to_editor(index + 1, request)
        self._set_canned_request_editor_visible(True)

    def delete_selected_canned_chart_request(self):
        index = self._selected_canned_request_index()
        if index is None or not (0 <= index < len(self.canned_chart_requests)):
            messagebox.showwarning("No Selection", "Select a chart request to delete.")
            return
        del self.canned_chart_requests[index]
        self.canned_request_edit_index = None
        self.refresh_canned_chart_requests()
        self.clear_canned_chart_request_editor()

    def clear_canned_chart_request_editor(self, hide_editor=True):
        self.canned_request_edit_index = None
        self.canned_req_name.set("")
        self.canned_req_chart_type.set("time_series")
        self.canned_req_programs.set("")
        self.canned_req_coupons.set("")
        self.canned_req_coupon_min.set("")
        self.canned_req_coupon_max.set("")
        self.canned_req_years.set("")
        self.canned_req_year_min.set("")
        self.canned_req_year_max.set("")
        self.canned_req_geos.set("")
        self.canned_req_loan_balances.set("")
        self.canned_req_story_families.set("")
        self.canned_req_story_tags.set("")
        self.canned_req_raw_stories.set("")
        if hasattr(self, "canned_request_advanced_frame"):
            self._set_canned_request_advanced_filters_visible(False)
        if hasattr(self, "btn_save_canned_chart_request"):
            self.btn_save_canned_chart_request.configure(text="Add Request to List")
        if hide_editor and hasattr(self, "canned_request_editor_frame"):
            self._set_canned_request_editor_visible(False)

    def _apply_canned_request_to_editor(self, index, request):
        self.canned_request_edit_index = index
        self.canned_req_name.set(str(request.get("name") or ""))
        self.canned_req_chart_type.set(str(request.get("chart_type") or "time_series"))
        self.canned_req_programs.set(self._join_config_list(request.get("programs")))
        self.canned_req_coupons.set("all" if str(request.get("coupons")).lower() == "all" else self._join_config_list(request.get("coupons")))
        self.canned_req_coupon_min.set("" if request.get("coupon_min") is None else str(request.get("coupon_min")))
        self.canned_req_coupon_max.set("" if request.get("coupon_max") is None else str(request.get("coupon_max")))
        self.canned_req_years.set(self._join_config_list(request.get("origination_years")))
        self.canned_req_year_min.set("" if request.get("origination_year_min") is None else str(request.get("origination_year_min")))
        self.canned_req_year_max.set("" if request.get("origination_year_max") is None else str(request.get("origination_year_max")))
        self.canned_req_geos.set(self._join_config_list(request.get("geographies")))
        self.canned_req_loan_balances.set(self._join_config_list(request.get("loan_balance_buckets")))
        self.canned_req_story_families.set(self._join_config_list(request.get("story_families")))
        self.canned_req_story_tags.set(self._join_config_list(request.get("story_tags")))
        self.canned_req_raw_stories.set(self._join_config_list(request.get("raw_story_names")))
        self._set_canned_request_advanced_filters_visible(
            bool(self.canned_req_programs.get() or self.canned_req_story_families.get() or self.canned_req_raw_stories.get())
        )
        if hasattr(self, "btn_save_canned_chart_request"):
            self.btn_save_canned_chart_request.configure(text="Save Request Changes")

    def save_canned_chart_request(self):
        try:
            request = self._collect_canned_chart_request_from_editor()
            self._validate_canned_chart_request(request)
            index = self.canned_request_edit_index
            if index is None or not (0 <= index < len(self.canned_chart_requests)):
                self.canned_chart_requests.append(request)
                index = len(self.canned_chart_requests) - 1
            else:
                self.canned_chart_requests[index] = request
            self.refresh_canned_chart_requests()
            self.canned_requests_tree.selection_set(str(index))
            self.canned_requests_tree.focus(str(index))
            self.canned_requests_tree.see(str(index))
            self.canned_request_edit_index = index
            self.update_canned_metadata({"message": "Chart request saved in draft. Click Save Config to persist it.", "request": request})
            self._set_canned_request_editor_visible(False)
        except Exception as exc:
            messagebox.showerror("Invalid Chart Request", str(exc))

    def _collect_canned_chart_request_from_editor(self):
        name = self.canned_req_name.get().strip()
        if not name:
            raise ValueError("Chart request name is required.")
        request = {
            "name": name,
            "chart_type": self.canned_req_chart_type.get().strip() or "time_series",
        }
        self._set_if_values(request, "programs", self._parse_str_csv(self.canned_req_programs.get()))
        coupons_raw = self.canned_req_coupons.get().strip()
        if coupons_raw.lower() == "all":
            request["coupons"] = "all"
        else:
            self._set_if_values(request, "coupons", self._parse_float_csv(coupons_raw))
        self._set_if_value(request, "coupon_min", self._parse_optional_float(self.canned_req_coupon_min.get()))
        self._set_if_value(request, "coupon_max", self._parse_optional_float(self.canned_req_coupon_max.get()))
        self._set_if_values(request, "origination_years", self._parse_int_csv(self.canned_req_years.get()))
        self._set_if_value(request, "origination_year_min", self._parse_optional_int(self.canned_req_year_min.get()))
        self._set_if_value(request, "origination_year_max", self._parse_optional_int(self.canned_req_year_max.get()))
        self._set_if_values(request, "geographies", self._parse_str_csv(self.canned_req_geos.get()))
        self._set_if_values(request, "loan_balance_buckets", self._parse_str_csv(self.canned_req_loan_balances.get()))
        self._set_if_values(request, "story_families", self._parse_str_csv(self.canned_req_story_families.get()))
        self._set_if_values(request, "story_tags", self._parse_str_csv(self.canned_req_story_tags.get()))
        self._set_if_values(request, "raw_story_names", self._parse_str_csv(self.canned_req_raw_stories.get()))
        return request

    @staticmethod
    def _set_if_values(target, key, values):
        if values:
            target[key] = values

    @staticmethod
    def _set_if_value(target, key, value):
        if value is not None:
            target[key] = value

    def _validate_canned_chart_request(self, request):
        if request.get("chart_type") not in {"time_series", "latest_snapshot_curve"}:
            raise ValueError("Chart type must be time_series or latest_snapshot_curve.")
        if not self._canned_request_has_explicit_filter(request):
            raise ValueError("Chart request must include at least one explicit filter. Do not rely on the request name.")
        min_coupon = request.get("coupon_min")
        max_coupon = request.get("coupon_max")
        if min_coupon is not None and max_coupon is not None and float(min_coupon) > float(max_coupon):
            raise ValueError("Coupon min must be less than or equal to coupon max.")
        min_year = request.get("origination_year_min")
        max_year = request.get("origination_year_max")
        if min_year is not None and max_year is not None and int(min_year) > int(max_year):
            raise ValueError("Origination year min must be less than or equal to max.")

    @staticmethod
    def _canned_request_has_explicit_filter(request):
        fields = {
            "programs",
            "coupons",
            "coupon_min",
            "coupon_max",
            "origination_years",
            "origination_year_min",
            "origination_year_max",
            "geographies",
            "loan_balance_buckets",
            "story_families",
            "story_tags",
            "raw_story_names",
        }
        for key in fields:
            value = request.get(key)
            if value is None:
                continue
            if isinstance(value, str) and value.strip():
                return True
            if isinstance(value, (list, tuple, set, dict)) and len(value) > 0:
                return True
            if not isinstance(value, (str, list, tuple, set, dict)):
                return True
        return False

    def _summarize_canned_request_filters(self, request):
        parts = []
        for key in (
            "programs",
            "coupons",
            "coupon_min",
            "coupon_max",
            "origination_years",
            "origination_year_min",
            "origination_year_max",
            "geographies",
            "loan_balance_buckets",
            "story_families",
            "story_tags",
            "raw_story_names",
        ):
            value = request.get(key)
            if value in (None, "", []):
                continue
            text = self._join_config_list(value)
            parts.append(f"{key}={text}")
        return "; ".join(parts) or "No explicit filters"

    def update_canned_metadata(self, metadata, metadata_path=None):
        self.canned_metadata_text.delete("1.0", tk.END)
        self.canned_metadata_text.insert("1.0", json.dumps(metadata, indent=2, ensure_ascii=False))
        self.canned_metadata_text.see("1.0")
        self.current_canned_metadata_file_path = Path(metadata_path) if metadata_path else None
        if self.current_canned_metadata_file_path and self.current_canned_metadata_file_path.exists():
            self.btn_open_canned_metadata_file.configure(state="normal")
        else:
            self.btn_open_canned_metadata_file.configure(state="disabled")

    def copy_canned_metadata(self):
        text = self.canned_metadata_text.get("1.0", "end-1c")
        if not text.strip() or text.strip() == "No canned report run yet.":
            messagebox.showwarning("No Metadata", "Run or load a canned report first.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update_idletasks()
        self.status.set("Canned report metadata copied to clipboard.")

    def open_canned_metadata_file(self):
        metadata_path = Path(self.current_canned_metadata_file_path) if self.current_canned_metadata_file_path else None
        if metadata_path is None and self.last_canned_output_path:
            metadata_path = Path(self.last_canned_output_path) / "diagnostics" / "run_metadata.json"
        if metadata_path is None or not metadata_path.exists():
            messagebox.showwarning("Metadata Missing", "No canned report run metadata file is available yet.")
            return
        try:
            os.startfile(str(metadata_path))
        except Exception as exc:
            messagebox.showerror("Open Failed", str(exc))

    def open_canned_output(self):
        output_path = Path(self.last_canned_output_path) if self.last_canned_output_path else Path(self.canned_output.get().strip() or ".")
        if not output_path.is_absolute():
            output_path = self._automation_runtime_base_dir() / output_path
        if not output_path.exists():
            messagebox.showwarning("Output Missing", f"Folder does not exist yet:\n{output_path}")
            return
        try:
            os.startfile(str(output_path))
        except Exception as exc:
            messagebox.showerror("Open Failed", str(exc))

    def run_selected_canned_report(self):
        try:
            name, payload = self._collect_canned_config_from_form()
        except Exception as exc:
            messagebox.showwarning("Run Setup Needed", str(exc))
            return

        self.saved_configs = self._load_saved_configs_map()
        existing = self.saved_configs.get(name)
        if existing:
            _, workflow = self._workflow_label_for_config(existing)
            if workflow != "payup_curve_pack":
                messagebox.showwarning(
                    "Wrong Workflow",
                    (
                        f"Config name '{name}' belongs to workflow '{workflow}'.\n\n"
                        "Choose a different canned report config name."
                    ),
                )
                return

        # Run Selected Now should execute exactly what is visible in the form.
        # Persist first so the shared run-config/headless path remains the one
        # execution path used by GUI, .bat, and Task Scheduler.
        self.saved_configs[name] = payload
        self._write_saved_configs_map(self.saved_configs)
        self.refresh_saved_configs(select_name=name)
        self.refresh_canned_reports(select_name=name)
        self.pending_canned_config_run_name = name
        self.logger.info("Canned report run requested from GUI: %s", name)
        self.status.set(f"Starting canned report '{name}' from current form settings...")
        self.start(self.work_canned_report)

    def work_canned_report(self):
        config_name = self.pending_canned_config_run_name
        try:
            self.root.after(0, lambda: self._set_progress(1, 5, f"Loading canned report '{config_name}'..."))
            result = run_saved_batch(
                config_name=config_name,
                config_store_path=self.config_store_path,
                base_dir=self._automation_runtime_base_dir(),
            )
            metadata = result.get("metadata") or {}
            output_path = Path(result["output_path"]) if result.get("output_path") else None
            metadata_path = Path(result["run_metadata_path"]) if result.get("run_metadata_path") else None
            self.last_canned_output_path = output_path
            self.last_canned_metadata_path = metadata_path
            self.last_automation_output_path = output_path
            self.root.after(0, lambda: self._set_progress(4, 5, "Writing canned report package..."))
            self.root.after(0, lambda: self.update_canned_metadata(metadata, metadata_path))
            client_summary = metadata.get("client_summary") if isinstance(metadata.get("client_summary"), dict) else {}
            charts_generated = int(client_summary.get("charts_generated") or 0)
            skipped = int(client_summary.get("skipped_requests") or 0)
            complete_message = f"Canned report complete: {charts_generated} charts generated."
            if skipped:
                complete_message += f" {skipped} request(s) skipped."
            self.root.after(0, lambda: self._set_progress(5, 5, complete_message))
            self.logger.info("Canned report run completed successfully: %s", config_name)
            if charts_generated:
                self.done("Canned report package completed. Open CLIENT_REPORT_INDEX.xlsx first.", path=str(output_path) if output_path else None)
            else:
                self.done(
                    "Canned report completed, but no charts were generated. Check chart request filters in Metadata.",
                    path=str(output_path) if output_path else None,
                    warn=True,
                )
        except Exception as exc:
            self.logger.exception("Canned report run failed")
            self.done(f"Error: {exc}", err=True)


    # --- LOGIC ---

    def _on_analysis_mode_changed(self, _event=None):
        try:
            selected_label = self.analysis_nb.tab(self.analysis_nb.select(), "text")
            if not self._busy:
                self.status.set(f"Analysis mode: {selected_label}")
        except Exception:
            pass

    @staticmethod
    def _format_analysis_value(value):
        text = str(value or "").strip()
        if not text or text.lower() in {"nan", "none", "nat"}:
            return ""
        return text

    def _build_analysis_suggestions(self, labels):
        raw_values = [self._format_analysis_value(value) for value in labels]
        raw_values = [value for value in raw_values if value]

        token_values = set()
        for value in raw_values:
            cleaned = value.replace("|", " ").replace("/", " ").replace(",", " ")
            parts = [part.strip() for part in cleaned.split() if part.strip()]
            for part in parts:
                if 2 <= len(part) <= 16:
                    token_values.add(part)

        suggestions = list(dict.fromkeys(raw_values + sorted(token_values)))
        return suggestions[:2000]

    def _populate_price_analysis_controls(self):
        if self.df_prices is None:
            return
        suggestions = self._build_analysis_suggestions(self.df_prices.columns)
        self.cb_price_filter["values"] = suggestions
        self.cb_curve_filter["values"] = suggestions
        if not self.filt_p.get().strip() and suggestions:
            self.filt_p.set(suggestions[0])
        if not self.curve_filter.get().strip() and suggestions:
            self.curve_filter.set(suggestions[0])

    def _populate_generic_analysis_controls(self):
        if self.df_generic is None:
            return
        suggestions = self._build_analysis_suggestions(self.df_generic.columns)
        self.cb_generic_filter["values"] = suggestions
        if not self.filt_g.get().strip() and suggestions:
            self.filt_g.set(suggestions[0])

    def _show_missing_input(self, title, message):
        messagebox.showwarning(title, message)
        self.status.set(message)

    def browse(self, v):

        p = filedialog.askopenfilename()

        if p: v.set(p)

    def browse_automation_input(self):
        selected = filedialog.askopenfilename(
            filetypes=[
                ("Data files", "*.xlsx *.xls *.csv"),
                ("Excel files", "*.xlsx *.xls"),
                ("CSV files", "*.csv"),
                ("All files", "*.*"),
            ]
        )
        if selected:
            self.auto_input_mode.set("fixed_file")
            self.auto_input.set(selected)
            self.auto_input_folder.set("")
            self._sync_automation_source_controls()
            self.load_automation_filter_values()

    def browse_automation_input_folder(self):
        selected = filedialog.askdirectory()
        if selected:
            self.auto_input_mode.set("latest_file")
            self.auto_input_folder.set(selected)
            self._sync_automation_source_controls()

    def browse_output_dir(self):
        selected = filedialog.askdirectory()
        if selected:
            self.auto_output.set(selected)

    def _automation_uses_latest_file(self):
        return str(self.auto_input_mode.get()).strip().lower() == "latest_file"

    def _sync_automation_source_controls(self):
        latest_mode = self._automation_uses_latest_file()
        fixed_state = "disabled" if latest_mode else "normal"
        latest_state = "normal" if latest_mode else "disabled"
        for widget in getattr(self, "auto_fixed_source_widgets", []):
            try:
                widget.configure(state=fixed_state)
            except Exception:
                pass
        for widget in getattr(self, "auto_latest_source_widgets", []):
            try:
                widget.configure(state=latest_state)
            except Exception:
                pass
        if not self.auto_input_pattern.get().strip():
            self.auto_input_pattern.set("*.xlsx")

    def _resolve_automation_input_path(self):
        if self._automation_uses_latest_file():
            folder_raw = self.auto_input_folder.get().strip()
            if not folder_raw:
                raise ValueError("Choose the input folder for latest-file mode.")
            pattern_raw = self.auto_input_pattern.get().strip() or "*.xlsx"
            return resolve_latest_input_file(Path(folder_raw), pattern_raw)

        input_raw = self.auto_input.get().strip()
        if not input_raw:
            raise ValueError("Choose a fixed CSV/XLSX dataset file.")
        return Path(input_raw)

    def _reset_progress(self):
        self.progress.configure(mode="determinate", maximum=100)
        self.progress["value"] = 0
        self.progress_text.set("0%")

    def _set_progress(self, completed, total, message=None):
        total_value = max(int(total or 0), 1)
        completed_value = max(0, min(int(completed or 0), total_value))
        percent = int(round((completed_value / total_value) * 100))
        self.progress.configure(mode="determinate", maximum=total_value)
        self.progress["value"] = completed_value
        self.progress_text.set(f"{percent}%")
        if message:
            self.status.set(str(message))

    def _automation_progress_callback(self, completed, total, message):
        self.root.after(0, lambda: self._set_progress(completed, total, message))

    def _automation_runtime_base_dir(self):
        """Use the client runtime folder when saved configs contain relative paths."""

        try:
            return self.config_store_path.parent.parent
        except Exception:
            return None

    def _reload_saved_configs_preserving_selection(self):
        current = self.auto_config_name.get().strip()
        self.saved_configs = self._load_saved_configs_map()
        names = self._idea_scan_config_names(self.saved_configs)
        try:
            self.cb_auto_configs["values"] = names
        except Exception:
            pass
        if current in names:
            self.auto_config_name.set(current)
            return current, self.saved_configs.get(current)
        return "", None

    def _selected_saved_config(self):
        name, config = self._reload_saved_configs_preserving_selection()
        if name and config is not None:
            return name, config
        return None, None

    def _is_idea_scan_config(self, config):
        try:
            _, workflow = self._workflow_label_for_config(config or {})
        except Exception:
            workflow = str((config or {}).get("workflow") or "idea_scan").strip().lower() or "idea_scan"
        return workflow == "idea_scan"

    def _idea_scan_config_names(self, configs=None):
        configs = configs if configs is not None else self.saved_configs
        return sorted(name for name, config in configs.items() if self._is_idea_scan_config(config))

    def _workflow_label_for_config(self, config):
        try:
            resolution = resolve_saved_workflow(config or {})
            workflow = resolution.workflow
        except Exception:
            workflow = str((config or {}).get("workflow") or "idea_scan").strip().lower() or "idea_scan"
        labels = {
            "idea_scan": "BUY/SELL idea scan",
            "payup_curve_pack": "Payup curve pack",
            "weekly_report": "Weekly canned report",
            "report_suite": "Report suite",
        }
        return labels.get(workflow, workflow), workflow

    def _refresh_automation_run_label(self):
        name = self.auto_config_name.get().strip()
        config = self.saved_configs.get(name) if name else None
        if not config:
            self.btn_run_automation.configure(text="RUN BUY/SELL SCAN")
            return
        label, workflow = self._workflow_label_for_config(config)
        if workflow == "idea_scan":
            self.btn_run_automation.configure(text="RUN BUY/SELL SCAN")
        else:
            self.btn_run_automation.configure(text="OPEN CANNED REPORTS TAB")
        if hasattr(self, "status") and not self._busy:
            self.status.set(f"Selected config: {name} ({label}).")

    def on_saved_config_selected(self, _event=None):
        name, config = self._selected_saved_config()
        if not name or config is None:
            self._refresh_automation_run_label()
            return
        try:
            self._apply_automation_form(config)
            self._refresh_automation_run_label()
        except Exception as exc:
            self._refresh_automation_run_label()
            messagebox.showwarning("Config Load Warning", f"Config '{name}' was selected but could not be previewed:\n{exc}")

    def _on_root_configure(self, event):
        if event.widget is not self.root:
            return
        current_size = (int(event.width), int(event.height))
        if self._resize_last_size == current_size:
            return
        self._resize_last_size = current_size



    def stop(self):

        self.stop_event.set()

    @staticmethod
    def _parse_int_csv(raw):
        raw = raw.strip()
        if not raw:
            return []
        return [int(item.strip()) for item in raw.split(",") if item.strip()]

    @staticmethod
    def _parse_float_csv(raw):
        raw = raw.strip()
        if not raw:
            return []
        return [float(item.strip()) for item in raw.split(",") if item.strip()]

    @staticmethod
    def _parse_str_csv(raw):
        raw = raw.strip()
        if not raw:
            return []
        return [item.strip() for item in raw.split(",") if item.strip()]

    @staticmethod
    def _parse_optional_int(raw):
        value = raw.strip()
        if not value:
            return None
        return int(value)

    @staticmethod
    def _parse_optional_float(raw):
        value = raw.strip()
        if not value:
            return None
        return float(value)

    @staticmethod
    def _parse_optional_date(raw, field_name):
        value = raw.strip()
        if not value:
            return None
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"{field_name} must be in YYYY-MM-DD format.") from exc
        return value

    @staticmethod
    def _config_bool(value, default=True):
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, str):
            raw = value.strip().lower()
            if raw in {"1", "true", "yes", "y", "on"}:
                return True
            if raw in {"0", "false", "no", "n", "off"}:
                return False
        return bool(value)

    @staticmethod
    def _format_filter_value(value, numeric_kind=None):
        if value is None:
            return ""
        try:
            if pd.isna(value):
                return ""
        except Exception:
            pass
        if numeric_kind in {"year", "coupon"}:
            try:
                numeric_value = float(value)
                if numeric_kind == "year":
                    return str(int(numeric_value))
                if numeric_value.is_integer():
                    return f"{numeric_value:.1f}"
                return f"{numeric_value:.3f}".rstrip("0").rstrip(".")
            except (TypeError, ValueError):
                pass
        return str(value).strip()

    @staticmethod
    def _sort_numeric_strings(values):
        def sort_key(value):
            try:
                return (0, float(value))
            except (TypeError, ValueError):
                return (1, str(value))

        return sorted(values, key=sort_key)

    def _extract_automation_filter_values(self, normalized):
        def unique_strings(column, numeric=False, limit=None, numeric_kind=None):
            if column not in normalized.columns:
                return []
            raw_values = normalized[column].dropna().unique().tolist()
            values = []
            for item in raw_values:
                text = self._format_filter_value(item, numeric_kind=numeric_kind)
                if text and text.lower() not in {"nan", "none", "nat"}:
                    values.append(text)
            values = sorted(set(values)) if not numeric else self._sort_numeric_strings(set(values))
            if limit is not None:
                return values[:limit]
            return values

        return {
            "programs": unique_strings("program"),
            "origination_years": unique_strings("origination_year", numeric=True, numeric_kind="year"),
            "geographies": unique_strings("geography"),
            "coupons": unique_strings("coupon", numeric=True, numeric_kind="coupon"),
            "loan_balance_buckets": unique_strings("loan_balance_bucket"),
            "story_families": unique_strings("story_family"),
            "story_tags": unique_strings("story_tag"),
            "raw_story_names": unique_strings("raw_story_name", limit=2000),
        }

    def load_automation_filter_values(self):
        try:
            source_path = self._resolve_automation_input_path()
        except Exception as exc:
            messagebox.showwarning("Input Needed", str(exc))
            return
        if self._busy:
            messagebox.showwarning("Busy", "Wait for the current operation to finish first.")
            return

        self._busy = True
        self.status.set(f"Loading filter values from {source_path.name}...")
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self.progress_text.set("...")
        self.btn_load_filter_values.config(state='disabled')
        threading.Thread(target=self.work_load_automation_filter_values, daemon=True).start()

    def work_load_automation_filter_values(self):
        try:
            input_path = self._resolve_automation_input_path()
            normalized, diagnostics = load_and_normalize_dataset(input_path)
            values = self._extract_automation_filter_values(normalized)
            self.root.after(0, lambda: self.apply_automation_filter_values(values, diagnostics, input_path))
        except Exception as exc:
            self.logger.exception("Automation filter value loading failed")
            self.root.after(0, lambda: self.finish_automation_filter_load(error=exc))

    def apply_automation_filter_values(self, values, diagnostics, input_path=None):
        self.auto_filter_values = values
        for key, widget in self.auto_filter_widgets.items():
            widget["values"] = values.get(key, [])
        if hasattr(self, "canned_filter_widgets"):
            self.canned_filter_values = values
            for key, widget in self.canned_filter_widgets.items():
                widget["values"] = values.get(key, [])

        year_values = values.get("origination_years", [])
        if year_values:
            self.auto_year_min.set(year_values[0])
            self.auto_year_max.set(year_values[-1])

        summary = {
            "message": "Dataset values loaded into filter dropdowns.",
            "input_mode": "Latest file from folder" if self._automation_uses_latest_file() else "Fixed file path",
            "resolved_input_file": str(input_path) if input_path else None,
            "detected_layout": diagnostics.get("source_layout"),
            "layout_detail": diagnostics.get("source_layout_detail"),
            "selected_sheet": diagnostics.get("selected_sheet") or diagnostics.get("sheet_name"),
            "normalized_rows": diagnostics.get("normalized_rows"),
            "available_values": {key: len(val) for key, val in values.items()},
            "manual_override": "All filter dropdowns remain editable; type comma-separated values to override.",
        }
        self.update_automation_metadata(summary)
        self.finish_automation_filter_load()

    def finish_automation_filter_load(self, error=None):
        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=100)
        self.progress["value"] = 0
        self.progress_text.set("0%")
        self._busy = False
        self.btn_load_filter_values.config(state='normal')

        if error is not None:
            self.status.set(self._default_status_text)
            messagebox.showerror("Load Failed", f"{error}\n\nSee log for details:\n{self.log_path}")
            return

        self.status.set("Filter values loaded and dropdowns updated.")

    def _load_saved_configs_map(self):
        if not self.config_store_path.exists():
            return {}
        try:
            raw = self.config_store_path.read_text(encoding="utf-8")
            payload = json.loads(raw.lstrip("\ufeff"))
        except Exception:
            try:
                payload = json.loads(self.config_store_path.read_text(encoding="utf-8-sig"))
            except Exception:
                return {}
        if isinstance(payload, dict) and isinstance(payload.get("configs"), dict):
            return payload["configs"]
        if isinstance(payload, dict):
            return {k: v for k, v in payload.items() if isinstance(v, dict)}
        return {}

    def _write_saved_configs_map(self, configs):
        payload = {"configs": configs}
        self.config_store_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_store_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def refresh_saved_configs(self, select_name=None):
        self.saved_configs = self._load_saved_configs_map()
        self._seed_default_canned_report_if_needed(self.saved_configs)
        names = self._idea_scan_config_names(self.saved_configs)
        self.cb_auto_configs["values"] = names
        if hasattr(self, "canned_reports_tree"):
            self.refresh_canned_reports(select_name=select_name)
        if not names:
            self.auto_config_name.set("")
            if hasattr(self, "btn_run_automation"):
                self._refresh_automation_run_label()
            return
        if select_name and select_name in names:
            self.auto_config_name.set(select_name)
            if hasattr(self, "btn_run_automation"):
                self._refresh_automation_run_label()
            return
        current = self.auto_config_name.get().strip()
        if current in names:
            self.auto_config_name.set(current)
            if hasattr(self, "btn_run_automation"):
                self._refresh_automation_run_label()
            return
        self.auto_config_name.set(names[0])
        if hasattr(self, "btn_run_automation"):
            self._refresh_automation_run_label()

    def _collect_automation_form(self):
        self._apply_idea_run_profile_flags()
        year_min = self._parse_optional_int(self.auto_year_min.get())
        year_max = self._parse_optional_int(self.auto_year_max.get())
        if year_min is not None and year_max is not None and year_min > year_max:
            raise ValueError("Origination year min must be less than or equal to max.")

        top_n = self._parse_optional_int(self.auto_top_n.get()) or 10
        min_observations = self._parse_optional_int(self.auto_min_observations.get()) or DEFAULT_MIN_OBSERVATIONS
        if top_n <= 0:
            raise ValueError("Top N must be greater than zero.")
        if min_observations <= 0:
            raise ValueError("Min observations must be greater than zero.")

        payload = {
            "workflow": "idea_scan",
            "output_dir": self.auto_output.get().strip() or str(resolve_default_overnight_output_dir()),
            "ranking_method": self._ranking_label_to_method(self.auto_rank_by.get()),
            "run_profile": self.auto_run_profile.get(),
            "top_n": top_n,
            "use_default_focus": bool(self.auto_use_default_focus.get()),
            "include_full_chart_history": bool(self.auto_include_full_chart_history.get()),
            "min_observations": min_observations,
            "package_name": self.auto_package_name.get().strip() or None,
            "filters": {
                "programs": self._parse_str_csv(self.auto_programs.get()),
                "geographies": self._parse_str_csv(self.auto_geos.get()),
                "loan_balance_buckets": self._parse_str_csv(self.auto_loan_balances.get()),
                "coupons": self._parse_float_csv(self.auto_coupons.get()),
                "origination_years": self._parse_int_csv(self.auto_years.get()),
                "origination_year_min": year_min,
                "origination_year_max": year_max,
                "story_families": self._parse_str_csv(self.auto_story_families.get()),
                "story_tags": self._parse_str_csv(self.auto_story_tags.get()),
                "raw_story_names": self._parse_str_csv(self.auto_raw_stories.get()),
            },
            "include_parse_failures": bool(self.auto_include_parse_failures.get()),
        }
        if self._automation_uses_latest_file():
            folder_raw = self.auto_input_folder.get().strip()
            if not folder_raw:
                raise ValueError("Choose an input folder before saving a latest-file config.")
            payload.update(
                {
                    "input_mode": "latest_file",
                    "input_dir": folder_raw,
                    "input_pattern": self.auto_input_pattern.get().strip() or "*.xlsx",
                }
            )
        else:
            input_raw = self.auto_input.get().strip()
            if not input_raw:
                raise ValueError("Choose a fixed dataset file before saving this config.")
            payload["input_path"] = input_raw
        payload["gui_schema_version"] = 2
        return payload

    def _collect_saved_config_payload(self):
        """Collect a GUI save payload without destroying non-idea workflows."""

        selected_name = self.auto_config_name.get().strip()
        existing = self.saved_configs.get(selected_name) if selected_name else None
        if existing:
            _, workflow = self._workflow_label_for_config(existing)
            if workflow != "idea_scan":
                payload = dict(existing)
                if self._automation_uses_latest_file():
                    folder_raw = self.auto_input_folder.get().strip()
                    if not folder_raw:
                        raise ValueError("Choose an input folder before saving a latest-file config.")
                    payload.pop("input_path", None)
                    payload.update(
                        {
                            "input_mode": "latest_file",
                            "input_dir": folder_raw,
                            "input_pattern": self.auto_input_pattern.get().strip() or "*.xlsx",
                        }
                    )
                else:
                    input_raw = self.auto_input.get().strip()
                    if not input_raw:
                        raise ValueError("Choose a fixed dataset file before saving this config.")
                    payload.pop("input_dir", None)
                    payload.pop("input_pattern", None)
                    payload.update({"input_mode": "fixed_file", "input_path": input_raw})
                payload["output_dir"] = self.auto_output.get().strip() or str(resolve_default_overnight_output_dir())
                package_name = self.auto_package_name.get().strip()
                if package_name:
                    payload["package_name"] = package_name
                elif "package_name" in payload:
                    payload["package_name"] = None
                payload["gui_schema_version"] = 2
                return payload

        return self._collect_automation_form()

    def _apply_automation_form(self, config):
        workflow = str(config.get("workflow", "")).strip().lower()
        if workflow == "idea_scan":
            filters = config.get("filters") if isinstance(config.get("filters"), dict) else {}
            input_mode = str(config.get("input_mode") or "").strip().lower()
            if input_mode == "latest_file" or config.get("input_dir"):
                self.auto_input_mode.set("latest_file")
                self.auto_input_folder.set(str(config.get("input_dir", "")))
                self.auto_input_pattern.set(str(config.get("input_pattern", "*.xlsx") or "*.xlsx"))
                self.auto_input.set(str(config.get("resolved_input_path") or config.get("input_path") or ""))
            else:
                self.auto_input_mode.set("fixed_file")
                self.auto_input.set(str(config.get("input_path", "")))
                self.auto_input_folder.set("")
                self.auto_input_pattern.set("*.xlsx")
            self._sync_automation_source_controls()
            self.auto_output.set(self._normalize_output_default(config.get("output_dir")))
            self.auto_package_name.set(str(config.get("package_name") or ""))
            self.auto_rank_by.set(self._ranking_method_to_label(str(config.get("ranking_method", "z_score"))))
            self.auto_top_n.set(str(config.get("top_n", 10)))
            self.auto_min_observations.set(str(config.get("min_observations", DEFAULT_MIN_OBSERVATIONS)))
            self.auto_use_default_focus.set(self._config_bool(config.get("use_default_focus", True), default=True))
            self.auto_include_full_chart_history.set(
                self._config_bool(config.get("include_full_chart_history", True), default=True)
            )
            self.auto_include_parse_failures.set(
                self._config_bool(config.get("include_parse_failures", True), default=True)
            )
            self.auto_run_profile.set(
                str(config.get("run_profile") or self._idea_run_profile_from_flags(
                    self.auto_use_default_focus.get(),
                    self.auto_include_full_chart_history.get(),
                    self.auto_include_parse_failures.get(),
                ))
            )
            self.auto_programs.set(self._join_config_list(filters.get("programs")))
            self.auto_geos.set(self._join_config_list(filters.get("geographies")))
            self.auto_loan_balances.set(self._join_config_list(filters.get("loan_balance_buckets")))
            self.auto_coupons.set(self._join_config_list(filters.get("coupons")))
            self.auto_years.set(self._join_config_list(filters.get("origination_years")))
            self.auto_year_min.set("" if filters.get("origination_year_min") is None else str(filters.get("origination_year_min")))
            self.auto_year_max.set("" if filters.get("origination_year_max") is None else str(filters.get("origination_year_max")))
            self.auto_story_families.set(self._join_config_list(filters.get("story_families")))
            self.auto_story_tags.set(self._join_config_list(filters.get("story_tags")))
            self.auto_raw_stories.set(self._join_config_list(filters.get("raw_story_names")))
            self._set_auto_filters_visible(self._automation_filter_values_present())
            return

        if workflow in {"payup_curve_pack", "payup_curves"}:
            input_mode = str(config.get("input_mode") or "").strip().lower()
            if input_mode == "latest_file" or config.get("input_dir"):
                self.auto_input_mode.set("latest_file")
                self.auto_input_folder.set(str(config.get("input_dir", "")))
                self.auto_input_pattern.set(str(config.get("input_pattern", "*.xlsx") or "*.xlsx"))
                self.auto_input.set(str(config.get("resolved_input_path") or config.get("input_path") or ""))
            else:
                self.auto_input_mode.set("fixed_file")
                self.auto_input.set(str(config.get("input_path", "")))
                self.auto_input_folder.set("")
                self.auto_input_pattern.set("*.xlsx")
            self._sync_automation_source_controls()
            self.auto_output.set(self._normalize_output_default(config.get("output_dir")))
            self.auto_package_name.set(str(config.get("package_name") or ""))

            chart_requests = config.get("chart_requests") if isinstance(config.get("chart_requests"), list) else []
            preview = {
                "message": "Saved payup curve pack loaded.",
                "workflow": "payup_curve_pack",
                "report_name": config.get("report_name"),
                "input_mode": self.auto_input_mode.get(),
                "input_path": self.auto_input.get(),
                "input_dir": self.auto_input_folder.get(),
                "output_dir": self.auto_output.get(),
                "chart_requests": [
                    {
                        "name": request.get("name"),
                        "chart_type": request.get("chart_type"),
                        "filters": {
                            key: request.get(key)
                            for key in (
                                "programs",
                                "coupons",
                                "coupon_min",
                                "coupon_max",
                                "origination_years",
                                "origination_year_min",
                                "origination_year_max",
                                "geographies",
                                "loan_balance_buckets",
                                "story_families",
                                "story_tags",
                                "raw_story_names",
                            )
                            if request.get(key) not in (None, "", [])
                        },
                    }
                    for request in chart_requests
                    if isinstance(request, dict)
                ],
                "note": "This workflow runs the saved chart request list. Edit chart requests in the saved config JSON until GUI editing is added.",
            }
            self.update_automation_metadata(preview)
            return

        # Backward compatibility for older weekly-automation presets saved before Phase 6.
        self.auto_input_mode.set("fixed_file")
        self.auto_input.set(str(config.get("auto_input", "")))
        self.auto_input_folder.set("")
        self.auto_input_pattern.set("*.xlsx")
        self._sync_automation_source_controls()
        self.auto_output.set(self._normalize_output_default(config.get("auto_output")))
        self.auto_package_name.set("")
        self.auto_rank_by.set(self._ranking_method_to_label(str(config.get("auto_rank_by", "Z-Score"))))
        self.auto_top_n.set(str(config.get("auto_best_n") or config.get("auto_worst_n") or "10"))
        self.auto_min_observations.set(str(DEFAULT_MIN_OBSERVATIONS))
        self.auto_use_default_focus.set(True)
        self.auto_include_full_chart_history.set(True)
        self.auto_include_parse_failures.set(True)
        self.auto_run_profile.set("Standard (Recommended)")
        self.auto_programs.set("")
        self.auto_geos.set(str(config.get("auto_geos", "")))
        self.auto_loan_balances.set("")
        self.auto_coupons.set(str(config.get("auto_coupons", "")))
        self.auto_years.set(str(config.get("auto_years", "")))
        self.auto_year_min.set("")
        self.auto_year_max.set("")
        self.auto_story_families.set(str(config.get("auto_buckets", "")))
        self.auto_story_tags.set("")
        self.auto_raw_stories.set("")
        self._set_auto_filters_visible(self._automation_filter_values_present())

    @staticmethod
    def _join_config_list(value):
        if value is None:
            return ""
        if isinstance(value, (list, tuple, set)):
            return ",".join(str(item) for item in value)
        return str(value)

    @staticmethod
    def _normalize_output_default(value):
        text = str(value or "").strip()
        normalized = text.replace("\\", "/").strip("/")
        if not normalized or normalized in {"output", "output/overnight_ideas"}:
            return str(resolve_default_overnight_output_dir())
        return text

    @staticmethod
    def _ranking_label_to_method(label):
        mapping = {
            "Z-Score": "z_score",
            "Raw Value": "value",
            "Pay-up": "payup",
            "Current Pay-up": "payup",
        }
        return mapping.get(str(label).strip(), "z_score")

    @staticmethod
    def _ranking_method_to_label(method):
        mapping = {
            "z_score": "Z-Score",
            "z-score": "Z-Score",
            "value": "Raw Value",
            "raw_value": "Raw Value",
            "payup": "Pay-up",
            "pay-up": "Pay-up",
            "current pay-up": "Pay-up",
            "mean": "Raw Value",
            "mean_payup": "Pay-up",
        }
        return mapping.get(str(method).strip().lower(), "Z-Score")

    def _build_idea_scan_definition(self):
        self._apply_idea_run_profile_flags()
        input_path = self._resolve_automation_input_path()

        year_min = self._parse_optional_int(self.auto_year_min.get())
        year_max = self._parse_optional_int(self.auto_year_max.get())
        if year_min is not None and year_max is not None and year_min > year_max:
            raise ValueError("Origination year min must be less than or equal to max.")

        top_n = self._parse_optional_int(self.auto_top_n.get()) or 10
        min_observations = self._parse_optional_int(self.auto_min_observations.get()) or DEFAULT_MIN_OBSERVATIONS
        if top_n <= 0:
            raise ValueError("Top N must be greater than zero.")
        if min_observations <= 0:
            raise ValueError("Min observations must be greater than zero.")

        return IdeaScanRunDefinition(
            input_path=Path(input_path),
            output_dir=Path(self.auto_output.get().strip() or str(resolve_default_overnight_output_dir())),
            input_mode="latest_file" if self._automation_uses_latest_file() else "fixed_file",
            input_dir=Path(self.auto_input_folder.get().strip()) if self._automation_uses_latest_file() else None,
            input_pattern=self.auto_input_pattern.get().strip() or "*.xlsx",
            ranking_method=self._ranking_label_to_method(self.auto_rank_by.get()),
            top_n=top_n,
            use_default_focus=bool(self.auto_use_default_focus.get()),
            include_full_chart_history=bool(self.auto_include_full_chart_history.get()),
            min_observations=min_observations,
            package_name=self.auto_package_name.get().strip() or None,
            programs=self._parse_str_csv(self.auto_programs.get()),
            geographies=self._parse_str_csv(self.auto_geos.get()),
            loan_balance_buckets=self._parse_str_csv(self.auto_loan_balances.get()),
            coupons=self._parse_float_csv(self.auto_coupons.get()),
            origination_years=self._parse_int_csv(self.auto_years.get()),
            origination_year_min=year_min,
            origination_year_max=year_max,
            story_families=self._parse_str_csv(self.auto_story_families.get()),
            story_tags=self._parse_str_csv(self.auto_story_tags.get()),
            raw_story_names=self._parse_str_csv(self.auto_raw_stories.get()),
            include_parse_failures=bool(self.auto_include_parse_failures.get()),
        )

    def save_automation_config(self):
        initial = self.auto_config_name.get().strip()
        name = simpledialog.askstring(
            "Save Config",
            "Configuration name:",
            initialvalue=initial,
            parent=self.root,
        )
        if name is None:
            return
        name = name.strip()
        if not name:
            messagebox.showwarning("Invalid Name", "Configuration name cannot be empty.")
            return

        self.refresh_saved_configs()
        if name in self.saved_configs:
            if not self._is_idea_scan_config(self.saved_configs[name]):
                messagebox.showwarning(
                    "Different Workflow",
                    (
                        f"'{name}' is a canned report config, not a BUY/SELL idea scan.\n\n"
                        "Edit canned reports from Automation > Canned Reports so workflow types do not get mixed."
                    ),
                )
                return
            overwrite = messagebox.askyesno("Overwrite Config", f"Config '{name}' already exists. Overwrite it?")
            if not overwrite:
                return

        try:
            self.saved_configs[name] = self._collect_saved_config_payload()
            self._write_saved_configs_map(self.saved_configs)
            self.refresh_saved_configs(select_name=name)
            messagebox.showinfo("Saved", f"Config '{name}' saved.")
        except Exception as exc:
            messagebox.showerror("Save Failed", str(exc))

    def load_selected_automation_config(self):
        name = self.auto_config_name.get().strip()
        if not name:
            messagebox.showwarning("No Selection", "Select a configuration first.")
            return

        self.refresh_saved_configs()
        config = self.saved_configs.get(name)
        if config is None:
            messagebox.showwarning("Missing Config", f"Config '{name}' was not found.")
            return
        if not self._is_idea_scan_config(config):
            messagebox.showwarning(
                "Use Canned Reports",
                (
                    f"'{name}' is a canned report config.\n\n"
                    "Open Automation > Canned Reports to edit or run canned payup reports."
                ),
            )
            return

        self._apply_automation_form(config)
        self._refresh_automation_run_label()
        messagebox.showinfo("Loaded", f"Config '{name}' loaded.")



    # Loaders

    def load_prices(self):

        if not self.p1.get().strip():
            self._show_missing_input("Input Needed", "Choose a Price History CSV/XLSX file before loading.")
            return

        self.status.set("Loading Price Data...")

        threading.Thread(target=self.worker_load_prices, daemon=True).start()



    def worker_load_prices(self):

        try:

            self.df_prices = mbs_backend.load_timeseries_data(self.p1.get(), self.status.set, is_price_mode=True)

            self.path_prices = self.p1.get()

            self.root.after(0, self._populate_price_analysis_controls)

            if self.spread_source.get() == "Price":

                self.root.after(0, self.refresh_spread_combos)

            self.done("Price Data Loaded!")

        except Exception as e: self.done(f"Error: {e}", err=True)



    def load_generic(self):

        if not self.p4.get().strip():
            self._show_missing_input("Input Needed", "Choose a General/OAS CSV/XLSX file before loading.")
            return

        self.status.set("Loading General Data...")

        threading.Thread(target=self.worker_load_generic, daemon=True).start()



    def worker_load_generic(self):

        try:

            self.df_generic = mbs_backend.load_timeseries_data(self.p4.get(), self.status.set, is_price_mode=False)

            self.path_generic = self.p4.get()

            self.root.after(0, self._populate_generic_analysis_controls)

            if self.spread_source.get() == "OAS":

                self.root.after(0, self.refresh_spread_combos)

            self.done("General Data Loaded!")

        except Exception as e: self.done(f"Error: {e}", err=True)



    def load_residuals(self):

        if not self.p2.get().strip():
            self._show_missing_input("Input Needed", "Choose a Residuals CSV/XLSX file before loading.")
            return

        self.status.set("Loading Residuals...")

        threading.Thread(target=self.worker_load_residuals, daemon=True).start()

        

    def worker_load_residuals(self):

        try:

            self.df_residuals = mbs_backend.load_residuals_data(self.p2.get(), self.status.set)

            bonds = sorted(list(self.df_residuals['Bond'].unique()))

            self.root.after(0, lambda: self.update_res_combo(bonds))

            self.path_residuals = self.p2.get()

            self.done("Residuals Loaded!")

        except Exception as e: self.done(f"Error: {e}", err=True)



    def refresh_spread_combos(self):

        mode = self.spread_source.get()

        bonds = []

        if mode == "Price" and self.df_prices is not None:

            bonds = list(self.df_prices.columns)

        elif mode == "OAS" and self.df_generic is not None:

            bonds = list(self.df_generic.columns)

        

        self.full_spread_list = bonds 

        self.cb_a['values'] = bonds; self.cb_b['values'] = bonds

        self.cb_a.set(''); self.cb_b.set('')

        if len(bonds) > 1: self.cb_a.current(0); self.cb_b.current(1)
        if not self._busy:
            self.status.set(f"Spread selector loaded {len(bonds)} instruments from {mode}.")



    def filter_spread_combos(self, *args):

        search_txt = self.search_spread.get().lower()

        if hasattr(self, 'full_spread_list'):

            filtered = [b for b in self.full_spread_list if search_txt in str(b).lower()]

            self.cb_a['values'] = filtered

            self.cb_b['values'] = filtered



    def update_res_combo(self, bonds):

        self.full_res_list = bonds

        self.cb_res_bond['values'] = bonds

        if bonds: self.cb_res_bond.current(0)
        if not self._busy:
            self.status.set(f"Residual selector loaded {len(bonds)} bonds.")

        

    def filter_res_combo(self, *args):

        search_txt = self.search_res.get().lower()

        if hasattr(self, 'full_res_list'):

            filtered = [b for b in self.full_res_list if search_txt in str(b).lower()]

            self.cb_res_bond['values'] = filtered



    # Runners

    def run_prices(self):

        if self.df_prices is None:
            self._show_missing_input("No Price Data", "Load a Price History dataset before generating price charts.")
            return

        self.start(self.work_prices)



    def work_prices(self):

        try:

            out_dir = mbs_backend.generate_charts(

                self.df_prices, self.path_prices, self.norm_p.get(),

                self.filt_p.get().strip(), self.period_p.get(), is_price_mode=True, 

                stop_event=self.stop_event, status_cb=self.status.set

            )

            self.done("Price Charts Complete!", path=out_dir)

        except Exception as e: self.done(f"Error: {e}", err=True)



    def run_generic(self):

        if self.df_generic is None:
            self._show_missing_input("No General/OAS Data", "Load a General/OAS dataset before generating charts.")
            return

        self.start(self.work_generic)



    def work_generic(self):

        try:

            out_dir = mbs_backend.generate_charts(

                self.df_generic, self.path_generic, self.norm_g.get(),

                self.filt_g.get().strip(), self.period_g.get(), is_price_mode=False,

                stop_event=self.stop_event, status_cb=self.status.set

            )

            self.done("General Charts Complete!", path=out_dir)

        except Exception as e: self.done(f"Error: {e}", err=True)



    def run_spread(self):

        mode = self.spread_source.get()

        df = self.df_prices if mode == "Price" else self.df_generic

        path = self.path_prices if mode == "Price" else self.path_generic

        if df is None:

            label = "Price History" if mode == "Price" else "General/OAS"
            messagebox.showwarning("No Data", f"Load data in the {label} sub-tab before plotting a spread.")

            return

        if not self.cb_a.get().strip() or not self.cb_b.get().strip():

            messagebox.showwarning("Selection Needed", "Select both Bond A and Bond B before plotting a spread.")

            return

        try:

            out_path = mbs_backend.generate_spread_chart(

                df, self.cb_a.get(), self.cb_b.get(), path, 

                self.period_p.get() if mode=="Price" else self.period_g.get(), 

                is_price_mode=(mode=="Price")

            )

            os.startfile(out_path)

        except Exception as e: messagebox.showerror("Error", str(e))



    def run_curve(self):

        if self.df_prices is None:

            messagebox.showwarning("No Data", "Load Price History data before generating pay-up curves.")

            return

        if not self.curve_filter.get():

            messagebox.showwarning("Input Needed", "Choose or type a story filter, for example '2022 FL' or 'NY'.")

            return

            

        try:

            out_path = mbs_backend.generate_curve_analysis(

                self.df_prices, self.path_prices, 

                self.curve_filter.get(), self.curve_mode.get(), self.period_c.get()

            )

            # Pass the path directly so done() can open it

            self.done("Curve Analysis Generated!", path=out_path)

        except Exception as e: messagebox.showerror("Error", str(e))



    def run_res_chart(self):

        if self.df_residuals is None:
            self._show_missing_input("No Residuals Data", "Load a Residuals file before charting a specific bond.")
            return

        if not self.cb_res_bond.get().strip():
            messagebox.showwarning("Selection Needed", "Select a residual bond before generating the line chart.")
            return

        try:

            path = mbs_backend.generate_residual_line_chart(

                self.df_residuals, self.cb_res_bond.get(), self.path_residuals, self.period_res.get()

            )

            os.startfile(path)

        except Exception as e: messagebox.showerror("Error", str(e))

        

    def run_res_scatter(self):

        if self.df_residuals is None:
            self._show_missing_input("No Residuals Data", "Load a Residuals file before generating the market overview.")
            return

        self.start(self.work_res_scatter)

        

    def work_res_scatter(self):

        try:

            out = mbs_backend.process_residuals_scatter(

                self.df_residuals, self.path_residuals, self.period_res.get(), self.stop_event, self.status.set

            )

            self.done("Scatter Generated!", path=out)

        except Exception as e: self.done(f"Error: {e}", err=True)

    def run_automation(self):

        selected_name, selected_config = self._selected_saved_config()
        selected_workflow = None
        if selected_config is not None:
            _, selected_workflow = self._workflow_label_for_config(selected_config)
            if selected_workflow != "idea_scan":
                messagebox.showwarning(
                    "Use Canned Reports",
                    (
                        f"'{selected_name}' is a canned report config.\n\n"
                        "Use Automation > Canned Reports > Run Selected Now for canned reports. "
                        "This tab runs BUY/SELL idea scans."
                    ),
                )
                return

        # This tab is intentionally BUY/SELL-only. Canned reports have their
        # own tab so operators do not accidentally run the wrong workflow.
        run_saved_config = selected_config is not None and selected_workflow != "idea_scan"
        self.pending_saved_config_run_name = selected_name if run_saved_config else None

        if not run_saved_config:
            try:
                self._resolve_automation_input_path()
            except Exception as exc:
                messagebox.showwarning("Input Needed", str(exc))
                return

        if run_saved_config:
            label, workflow = self._workflow_label_for_config(selected_config)
            self.logger.info("Saved config run requested from GUI: %s (%s)", selected_name, workflow)
            self.status.set(f"Starting saved config '{selected_name}' ({label})...")
        else:
            if selected_name and selected_workflow == "idea_scan":
                self.logger.info("Idea scan run requested from GUI form with selected config: %s", selected_name)
                self.status.set(f"Starting idea scan from current form values ({selected_name})...")
            else:
                self.logger.info("Ad hoc idea scan run requested from GUI")
                self.status.set("Starting ad hoc idea scan...")
        self.start(self.work_automation)

    def run_idea_scan_from_workspace(self):
        self.pending_saved_config_run_name = None
        try:
            self._resolve_automation_input_path()
        except Exception as exc:
            messagebox.showwarning("Input Needed", str(exc))
            return
        self.logger.info("Idea scan run requested from Ideas Workspace")
        self.status.set("Starting idea scan from current workspace values...")
        self.start(self.work_automation)

    def work_automation(self):

        try:
            if self.pending_saved_config_run_name:
                self._work_saved_config_automation(self.pending_saved_config_run_name)
                return

            self.root.after(0, lambda: self._set_progress(1, 6, "Validating config and input source..."))
            definition = self._build_idea_scan_definition()
            result = run_idea_scan_definition(definition, progress_callback=self._automation_progress_callback)
            self.last_automation_output_path = result.output_dir
            self.last_automation_metadata_path = result.run_metadata_path
            charts_generated = int(result.package_result.metadata.get("charts_generated", 0))
            if charts_generated:
                complete_message = f"Idea scan complete: {charts_generated} charts generated."
            else:
                complete_message = "Idea scan finished, but no charts were generated."
            self.root.after(0, lambda: self._set_progress(6, 6, complete_message))
            self.root.after(0, lambda: self.update_automation_metadata(result.run_metadata, result.run_metadata_path))
            self.logger.info("Automation run completed successfully")
            client_summary = result.run_metadata.get("client_summary") if isinstance(result.run_metadata, dict) else {}
            open_path = (
                client_summary.get("summary_workbook")
                if isinstance(client_summary, dict)
                else None
            ) or str(result.output_dir)
            success_message = self._automation_completion_message("BUY/SELL Idea Scan", client_summary)

            if charts_generated:
                self.done(success_message, path=str(open_path))
            else:
                self.done(
                    success_message
                    + "\n\nNo charts were generated. Check filters, Top N, and Min observations in Run Metadata.",
                    path=str(open_path),
                    warn=True,
                )

        except Exception as e:
            self.logger.exception("Automation run failed")

            self.done(f"Error: {e}", err=True)

    def _work_saved_config_automation(self, config_name):
        self.root.after(0, lambda: self._set_progress(1, 5, f"Loading saved config '{config_name}'..."))
        config = self.saved_configs.get(config_name)
        label, workflow = self._workflow_label_for_config(config or {})
        self.root.after(0, lambda: self._set_progress(2, 5, f"Running {label}..."))

        result = run_saved_batch(
            config_name=config_name,
            config_store_path=self.config_store_path,
            base_dir=self._automation_runtime_base_dir(),
        )

        metadata = result.get("metadata") or {}
        output_path = Path(result["output_path"]) if result.get("output_path") else None
        metadata_path = Path(result["run_metadata_path"]) if result.get("run_metadata_path") else None
        self.last_automation_output_path = output_path
        self.last_automation_metadata_path = metadata_path

        client_summary = metadata.get("client_summary") if isinstance(metadata.get("client_summary"), dict) else {}
        charts_generated = int(
            client_summary.get("charts_generated")
            or (metadata.get("package_metadata") or {}).get("charts_generated", 0)
            or 0
        )
        skipped_requests = int(client_summary.get("skipped_requests") or 0)
        self.root.after(0, lambda: self._set_progress(4, 5, "Writing reports, charts, and metadata..."))
        self.root.after(0, lambda: self.update_automation_metadata(metadata, metadata_path))

        if workflow == "payup_curve_pack":
            if charts_generated:
                complete_message = f"Payup curve pack complete: {charts_generated} charts generated."
            else:
                complete_message = "Payup curve pack finished, but no charts were generated."
            if skipped_requests:
                complete_message += f" {skipped_requests} request(s) skipped."
            success_message = "Payup curve package completed. Open CLIENT_REPORT_INDEX.xlsx first."
            warning_message = (
                "Payup curve package completed, but no charts were generated. "
                "Check chart request filters in Run Metadata."
            )
        elif workflow == "idea_scan":
            complete_message = (
                f"Idea scan complete: {charts_generated} charts generated."
                if charts_generated
                else "Idea scan finished, but no charts were generated."
            )
            success_message = "Idea scan package completed. Open CLIENT_REPORT_BUY_SELL.xlsx first."
            warning_message = (
                "Idea scan completed, but no charts were generated. "
                "Check filters, Top N, and Min observations in Run Metadata."
            )
        else:
            complete_message = f"Saved config '{config_name}' completed."
            success_message = f"Saved config '{config_name}' completed."
            warning_message = success_message

        self.root.after(0, lambda: self._set_progress(5, 5, complete_message))
        self.logger.info("Saved config run completed successfully: %s", config_name)
        completion_summary = self._automation_completion_message(label, client_summary)
        open_path = (
            client_summary.get("summary_workbook")
            or client_summary.get("client_report_index")
            or str(output_path)
            if output_path
            else None
        )

        if charts_generated or workflow not in {"idea_scan", "payup_curve_pack"}:
            self.done(completion_summary or success_message, path=str(open_path) if open_path else None)
        else:
            self.done(
                (completion_summary or warning_message) + "\n\nNo charts were generated. Check Run Metadata.",
                path=str(open_path) if open_path else None,
                warn=True,
            )

    @staticmethod
    def _automation_completion_message(title, client_summary):
        if not isinstance(client_summary, dict):
            return str(title or "Run completed.")
        lines = [f"{title} completed."]
        result = client_summary.get("result")
        if result:
            lines.append(f"Result: {result}")
        if client_summary.get("buy_ideas") is not None:
            lines.append(f"BUY ideas: {client_summary.get('buy_ideas')}")
        if client_summary.get("sell_ideas") is not None:
            lines.append(f"SELL ideas: {client_summary.get('sell_ideas')}")
        if client_summary.get("chart_requests") is not None:
            lines.append(f"Chart requests: {client_summary.get('chart_requests')}")
        if client_summary.get("charts_generated") is not None:
            lines.append(f"Charts generated: {client_summary.get('charts_generated')}")
        if client_summary.get("skipped_requests") is not None:
            lines.append(f"Skipped / empty requests: {client_summary.get('skipped_requests')}")
        report = client_summary.get("summary_workbook") or client_summary.get("client_report_index")
        if report:
            lines.append("")
            lines.append(f"Opening report: {Path(report).name}")
        return "\n".join(lines)

    def update_automation_metadata(self, metadata, metadata_path=None):

        self.auto_metadata_text.delete("1.0", tk.END)

        self.auto_metadata_text.insert("1.0", json.dumps(metadata, indent=2, ensure_ascii=False))

        self.auto_metadata_text.see("1.0")

        self.current_automation_metadata_file_path = Path(metadata_path) if metadata_path else None

        if self.current_automation_metadata_file_path and self.current_automation_metadata_file_path.exists():
            self.btn_open_metadata_file.configure(state="normal")
        else:
            self.btn_open_metadata_file.configure(state="disabled")

    def copy_automation_metadata(self):

        text = self.auto_metadata_text.get("1.0", "end-1c")

        if not text.strip() or text.strip() == "No runs yet.":

            messagebox.showwarning("No Metadata", "Run a saved config first, then copy the generated metadata.")

            return

        self.root.clipboard_clear()

        self.root.clipboard_append(text)

        self.root.update_idletasks()

        self.status.set("Run metadata copied to clipboard.")

    def open_automation_metadata_file(self):

        metadata_path = (
            Path(self.current_automation_metadata_file_path)
            if self.current_automation_metadata_file_path
            else None
        )

        if metadata_path is None and self.last_automation_output_path:

            metadata_path = Path(self.last_automation_output_path) / "diagnostics" / "run_metadata.json"

        if metadata_path is None or not metadata_path.exists():

            messagebox.showwarning(
                "Metadata File Missing",
                "No run metadata file is available yet. Run a saved config first.",
            )

            return

        try:

            os.startfile(str(metadata_path))

        except Exception as exc:

            messagebox.showerror("Open Failed", str(exc))

    def open_automation_output(self):

        if self.last_automation_output_path:
            output_path = Path(self.last_automation_output_path)
        else:
            output_raw = self.auto_output.get().strip() or str(resolve_default_overnight_output_dir())

            output_path = Path(output_raw)

            if not output_path.is_absolute():

                output_path = Path.cwd() / output_path

        if not output_path.exists():

            messagebox.showwarning("Output Missing", f"Folder does not exist yet:\n{output_path}")

            return

        try:

            os.startfile(str(output_path))

        except Exception as exc:

            messagebox.showerror("Open Failed", str(exc))

    def start(self, target):

        self.stop_event.clear(); self.btn_stop.config(state='normal')
        self._busy = True
        self.root.after(0, self._reset_progress)

        threading.Thread(target=target, daemon=True).start()



    def done(self, msg, path=None, err=False, warn=False):

        self._busy = False
        self.btn_stop.config(state='disabled'); self.status.set(self._default_status_text)
        if err:
            try:
                self.progress.stop()
                self._reset_progress()
            except Exception:
                pass

        if err:
            self.logger.error("GUI error surfaced: %s", msg)
            messagebox.showerror("Error", f"{msg}\n\nSee log for details:\n{self.log_path}")

        elif warn:

            messagebox.showwarning("Completed With Warning", msg)

            if path:

                try: os.startfile(path)

                except: pass

        else: 

            messagebox.showinfo("Success", msg)

            if path:

                try: os.startfile(path) # This is the magic line that opens the file

                except: pass



def create_root():
    if HAS_TTKBOOTSTRAP and ttkbootstrap is not None and hasattr(ttkbootstrap, "Window"):
        theme_name = os.getenv("MBS_THEME", "superhero")
        try:
            return ttkbootstrap.Window(themename=theme_name)
        except Exception:
            return ttkbootstrap.Window()
    return tk.Tk()


if __name__ == "__main__":

    root = create_root(); app = MBSApp(root); root.mainloop()

