import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import mbs_backend
import glob


class MBSApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MBS Analytics Tool (Client Edition v2.1)")
        self.root.geometry("800x750")

        self.stop_event = threading.Event()
        # Data containers
        self.df_prices = None
        self.df_generic = None
        self.df_residuals = None

        # Paths
        self.path_prices = ""
        self.path_generic = ""
        self.path_residuals = ""

        style = ttk.Style()
        style.theme_use('clam')

        # UI Tabs
        nb = ttk.Notebook(root)
        nb.pack(expand=True, fill='both', padx=10, pady=10)

        self.t1 = ttk.Frame(nb);
        nb.add(self.t1, text="1. Price History (32nds)")
        self.t4 = ttk.Frame(nb);
        nb.add(self.t4, text="2. General/OAS Charts")
        self.t3 = ttk.Frame(nb);
        nb.add(self.t3, text="3. Spread Calculator")
        self.t2 = ttk.Frame(nb);
        nb.add(self.t2, text="4. Residuals Analysis")

        self.setup_t1()  # Prices
        self.setup_t4()  # Generic/OAS
        self.setup_t3()  # Spreads (UPDATED)
        self.setup_t2()  # Residuals

        # Status Bar
        self.status = tk.StringVar(value="Ready.")
        bar = ttk.Frame(root, relief=tk.RAISED)
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Label(bar, textvariable=self.status).pack(side=tk.LEFT, padx=10)
        self.btn_stop = ttk.Button(bar, text="STOP", command=self.stop, state='disabled')
        self.btn_stop.pack(side=tk.RIGHT)

    # --- TAB 1: PRICES ---
    def setup_t1(self):
        f = ttk.LabelFrame(self.t1, text="Bond Price Data Input", padding=15)
        f.pack(fill='x', padx=10, pady=10)

        self.p1 = tk.StringVar()
        ttk.Entry(f, textvariable=self.p1).pack(side=tk.LEFT, fill='x', expand=True)
        ttk.Button(f, text="Browse", command=lambda: self.browse(self.p1)).pack(side=tk.RIGHT)

        f2 = ttk.Frame(self.t1);
        f2.pack(fill='x', padx=10)
        ttk.Label(f2, text="Time Period:").pack(side=tk.LEFT, pady=10)
        self.period_p = tk.StringVar(value="All History")
        times = ["All History", "YTD", "1 Year", "6 Months", "3 Months", "1 Month"]
        ttk.Combobox(f2, textvariable=self.period_p, values=times, state="readonly", width=15).pack(side=tk.LEFT,
                                                                                                    padx=5, pady=10)

        self.norm_p = tk.BooleanVar()
        ttk.Checkbutton(f2, text="Normalize (Start at 0)", variable=self.norm_p).pack(side=tk.RIGHT, pady=10, padx=5)

        f3 = ttk.LabelFrame(self.t1, text="Filter (Optional)", padding=5)
        f3.pack(fill='x', padx=10)
        self.filt_p = tk.StringVar()
        ttk.Entry(f3, textvariable=self.filt_p).pack(fill='x')

        ttk.Button(self.t1, text="LOAD PRICE DATA", command=self.load_prices).pack(pady=5)
        ttk.Button(self.t1, text="GENERATE PRICE CHARTS", command=self.run_prices).pack(pady=5)

    # --- TAB 2: GENERIC/OAS ---
    def setup_t4(self):
        f = ttk.LabelFrame(self.t4, text="General Data Input (OAS, Yields, etc.)", padding=15)
        f.pack(fill='x', padx=10, pady=10)

        self.p4 = tk.StringVar()
        ttk.Entry(f, textvariable=self.p4).pack(side=tk.LEFT, fill='x', expand=True)
        ttk.Button(f, text="Browse", command=lambda: self.browse(self.p4)).pack(side=tk.RIGHT)

        f2 = ttk.Frame(self.t4);
        f2.pack(fill='x', padx=10)
        ttk.Label(f2, text="Time Period:").pack(side=tk.LEFT, pady=10)
        self.period_g = tk.StringVar(value="All History")
        times = ["All History", "YTD", "1 Year", "6 Months", "3 Months", "1 Month"]
        ttk.Combobox(f2, textvariable=self.period_g, values=times, state="readonly", width=15).pack(side=tk.LEFT,
                                                                                                    padx=5, pady=10)

        self.norm_g = tk.BooleanVar()
        ttk.Checkbutton(f2, text="Normalize", variable=self.norm_g).pack(side=tk.RIGHT, pady=10, padx=5)

        f3 = ttk.LabelFrame(self.t4, text="Filter (Optional)", padding=5)
        f3.pack(fill='x', padx=10)
        self.filt_g = tk.StringVar()
        ttk.Entry(f3, textvariable=self.filt_g).pack(fill='x')

        ttk.Button(self.t4, text="LOAD GENERAL DATA", command=self.load_generic).pack(pady=5)
        ttk.Button(self.t4, text="GENERATE CHARTS", command=self.run_generic).pack(pady=5)

    # --- TAB 3: SPREADS (UPDATED) ---
    def setup_t3(self):
        # 1. Source Selection
        f_src = ttk.LabelFrame(self.t3, text="Select Data Source", padding=10)
        f_src.pack(fill='x', padx=10, pady=5)

        self.spread_source = tk.StringVar(value="Price")  # Default

        rb1 = ttk.Radiobutton(f_src, text="Price History (Tab 1 Data)", variable=self.spread_source, value="Price",
                              command=self.refresh_spread_combos)
        rb1.pack(side=tk.LEFT, padx=20)

        rb2 = ttk.Radiobutton(f_src, text="General/OAS (Tab 2 Data)", variable=self.spread_source, value="OAS",
                              command=self.refresh_spread_combos)
        rb2.pack(side=tk.LEFT, padx=20)

        # 2. Controls
        f = ttk.LabelFrame(self.t3, text="Interactive Spread", padding=15)
        f.pack(fill='both', expand=True, padx=10, pady=10)

        ttk.Label(f, text="Bond A (Long):").pack(anchor=tk.W)
        self.cb_a = ttk.Combobox(f);
        self.cb_a.pack(fill='x', pady=5)

        ttk.Label(f, text="Bond B (Short):").pack(anchor=tk.W)
        self.cb_b = ttk.Combobox(f);
        self.cb_b.pack(fill='x', pady=5)

        ttk.Button(f, text="📉 PLOT SPREAD", command=self.run_spread).pack(pady=20, ipadx=10)

    # --- TAB 4: RESIDUALS ---
    def setup_t2(self):
        f = ttk.LabelFrame(self.t2, text="Residuals Input", padding=15)
        f.pack(fill='x', padx=10, pady=10)
        self.p2 = tk.StringVar()
        ttk.Entry(f, textvariable=self.p2).pack(side=tk.LEFT, fill='x', expand=True)
        ttk.Button(f, text="Browse", command=lambda: self.browse(self.p2)).pack(side=tk.RIGHT)

        ttk.Button(self.t2, text="LOAD RESIDUALS FILE", command=self.load_residuals).pack(pady=5)

        f_sel = ttk.LabelFrame(self.t2, text="Chart Specific Bond", padding=15)
        f_sel.pack(fill='both', expand=True, padx=10, pady=10)

        ttk.Label(f_sel, text="Select Bond:").pack(anchor=tk.W)
        self.cb_res_bond = ttk.Combobox(f_sel)
        self.cb_res_bond.pack(fill='x', pady=5)

        ttk.Label(f_sel, text="Timeline:").pack(anchor=tk.W, pady=(10, 0))
        self.period_res = tk.StringVar(value="All History")
        times = ["All History", "YTD", "1 Year", "6 Months", "3 Months", "1 Month"]
        ttk.Combobox(f_sel, textvariable=self.period_res, values=times, state="readonly").pack(fill='x', pady=5)

        ttk.Button(f_sel, text="📈 CHART RESIDUAL (LINE)", command=self.run_res_chart).pack(pady=10)
        ttk.Button(self.t2, text="GENERATE MARKET OVERVIEW (Scatter)", command=self.run_res_scatter).pack(pady=5)

    # --- LOGIC ---
    def browse(self, v):
        p = filedialog.askopenfilename()
        if p: v.set(p)

    def stop(self):
        self.stop_event.set()

    # Loaders
    def load_prices(self):
        if not self.p1.get(): return
        self.status.set("Loading Price Data...")
        threading.Thread(target=self.worker_load_prices).start()

    def worker_load_prices(self):
        try:
            self.df_prices = mbs_backend.load_timeseries_data(self.p1.get(), self.status.set, is_price_mode=True)
            self.path_prices = self.p1.get()
            # If currently selected source is Price, update combos immediately
            if self.spread_source.get() == "Price":
                self.root.after(0, self.refresh_spread_combos)
            self.done("Price Data Loaded!")
        except Exception as e:
            self.done(f"Error: {e}", err=True)

    def load_generic(self):
        if not self.p4.get(): return
        self.status.set("Loading General Data...")
        threading.Thread(target=self.worker_load_generic).start()

    def worker_load_generic(self):
        try:
            self.df_generic = mbs_backend.load_timeseries_data(self.p4.get(), self.status.set, is_price_mode=False)
            self.path_generic = self.p4.get()
            # If currently selected source is OAS, update combos immediately
            if self.spread_source.get() == "OAS":
                self.root.after(0, self.refresh_spread_combos)
            self.done("General Data Loaded!")
        except Exception as e:
            self.done(f"Error: {e}", err=True)

    def load_residuals(self):
        if not self.p2.get(): return
        self.status.set("Loading Residuals...")
        threading.Thread(target=self.worker_load_residuals).start()

    def worker_load_residuals(self):
        try:
            self.df_residuals = mbs_backend.load_residuals_data(self.p2.get(), self.status.set)
            bonds = sorted(list(self.df_residuals['Bond'].unique()))
            self.root.after(0, lambda: self.update_res_combo(bonds))
            self.path_residuals = self.p2.get()
            self.done("Residuals Loaded!")
        except Exception as e:
            self.done(f"Error: {e}", err=True)

    def refresh_spread_combos(self):
        mode = self.spread_source.get()
        bonds = []
        if mode == "Price" and self.df_prices is not None:
            bonds = list(self.df_prices.columns)
        elif mode == "OAS" and self.df_generic is not None:
            bonds = list(self.df_generic.columns)

        self.cb_a['values'] = bonds
        self.cb_b['values'] = bonds
        self.cb_a.set('')
        self.cb_b.set('')

        if len(bonds) > 1:
            self.cb_a.current(0)
            self.cb_b.current(1)

    def update_res_combo(self, bonds):
        self.cb_res_bond['values'] = bonds
        if bonds: self.cb_res_bond.current(0)

    # Runners
    def run_prices(self):
        if self.df_prices is None: return
        self.start(self.work_prices)

    def work_prices(self):
        try:
            out_dir = mbs_backend.generate_charts(
                self.df_prices, self.path_prices, self.norm_p.get(),
                self.filt_p.get().strip(), self.period_p.get(),
                is_price_mode=True,
                stop_event=self.stop_event, status_cb=self.status.set
            )
            self.done("Price Charts Complete!", path=out_dir)
        except Exception as e:
            self.done(f"Error: {e}", err=True)

    def run_generic(self):
        if self.df_generic is None: return
        self.start(self.work_generic)

    def work_generic(self):
        try:
            out_dir = mbs_backend.generate_charts(
                self.df_generic, self.path_generic, self.norm_g.get(),
                self.filt_g.get().strip(), self.period_g.get(),
                is_price_mode=False,
                stop_event=self.stop_event, status_cb=self.status.set
            )
            self.done("General Charts Complete!", path=out_dir)
        except Exception as e:
            self.done(f"Error: {e}", err=True)

    def run_spread(self):
        mode = self.spread_source.get()
        df = None
        path = ""
        is_price = True

        if mode == "Price":
            df = self.df_prices
            path = self.path_prices
            is_price = True
            period = self.period_p.get()
        else:
            df = self.df_generic
            path = self.path_generic
            is_price = False
            period = self.period_g.get()

        if df is None:
            messagebox.showwarning("No Data", f"Please load data in Tab {1 if mode == 'Price' else 2} first.")
            return

        try:
            # Pass is_price_mode to backend to format axis correctly
            out_path = mbs_backend.generate_spread_chart(
                df, self.cb_a.get(), self.cb_b.get(), path, period, is_price_mode=is_price
            )
            os.startfile(out_path)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def run_res_chart(self):
        if self.df_residuals is None: return
        try:
            path = mbs_backend.generate_residual_line_chart(
                self.df_residuals, self.cb_res_bond.get(), self.path_residuals, self.period_res.get()
            )
            os.startfile(path)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def run_res_scatter(self):
        if self.df_residuals is None: return
        self.start(self.work_res_scatter)

    def work_res_scatter(self):
        try:
            out = mbs_backend.process_residuals_scatter(
                self.df_residuals, self.path_residuals, self.period_res.get(), self.stop_event, self.status.set
            )
            self.done("Scatter Generated!", path=out)
        except Exception as e:
            self.done(f"Error: {e}", err=True)

    def start(self, target):
        self.stop_event.clear();
        self.btn_stop.config(state='normal')
        threading.Thread(target=target).start()

    def done(self, msg, path=None, err=False):
        self.btn_stop.config(state='disabled');
        self.status.set("Ready.")
        if err:
            messagebox.showerror("Error", msg)
        else:
            messagebox.showinfo("Success", msg)
            if path:
                try:
                    os.startfile(path)
                except:
                    pass


if __name__ == "__main__":
    root = tk.Tk();
    app = MBSApp(root);
    root.mainloop()