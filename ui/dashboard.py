"""
Manager Dashboard — Eagle's Eye View
Latest-report hero + fleet-level activity.
Pure tkinter, no extra dependencies beyond what the app already uses.
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import statistics
import csv

from db.session import get_session
from db.models import Batch, ValidationResult, Signature, Personnel, Field


# ── palette ──────────────────────────────────────────────────────────────────
C_BG        = '#F0F4F8'
C_SIDEBAR   = '#1A2744'
C_HEADER    = '#1F3864'
C_ACCENT    = '#2E86C1'
C_PASS      = '#1E8449'
C_PASS_LT   = '#D5F5E3'
C_FAIL      = '#C0392B'
C_FAIL_LT   = '#FADBD8'
C_WARN      = '#D68910'
C_WARN_LT   = '#FEF9E7'
C_PENDING   = '#7F8C8D'
C_PEND_LT   = '#EAECEE'
C_WHITE     = '#FFFFFF'
C_CARD      = '#FFFFFF'
C_GRID      = '#DDE3EC'
C_DIVIDER   = '#E5EAF0'
C_TEXT      = '#1C2833'
C_SUB       = '#85929E'
C_HERO_BG   = '#0D1F3C'
C_HERO_PASS = '#1ABC9C'
C_HERO_FAIL = '#E74C3C'

FONT_TITLE  = ('Segoe UI', 13, 'bold')
FONT_LABEL  = ('Segoe UI', 9)
FONT_SMALL  = ('Segoe UI', 8)
FONT_NUM    = ('Segoe UI', 22, 'bold')
FONT_NUM_SM = ('Segoe UI', 14, 'bold')
FONT_MONO   = ('Consolas', 9)


# ── helpers ───────────────────────────────────────────────────────────────────
def _pill(parent, text, bg, fg='white', font=None, padx=10, pady=3):
    """Rounded-looking label pill."""
    lbl = tk.Label(parent, text=text, bg=bg, fg=fg,
                   font=font or FONT_LABEL, padx=padx, pady=pady)
    return lbl


def _divider(parent, color=C_DIVIDER, height=1, pady=4):
    tk.Frame(parent, bg=color, height=height).pack(fill='x', pady=pady)


def _card_frame(parent, **kw):
    """White card with a subtle shadow effect via an offset dark frame."""
    outer = tk.Frame(parent, bg=C_GRID)
    inner = tk.Frame(outer, bg=C_CARD, **kw)
    inner.pack(fill='both', expand=True, padx=(0, 2), pady=(0, 2))
    return outer, inner


# ─────────────────────────────────────────────────────────────────────────────
class ManagerDashboard(tk.Toplevel):
    """Manager eagle's-eye dashboard: latest report hero + fleet metrics."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Manager Dashboard — BPR Eagle's Eye")
        self.geometry("1260x820")
        self.minsize(900, 620)
        self.resizable(True, True)
        self.configure(bg=C_BG)
        self._mode = tk.StringVar(value='daily')
        self._build()
        self._load_data()

    # ── construction ─────────────────────────────────────────────────────────
    def _build(self):
        s = ttk.Style()
        try:
            s.theme_use('clam')
        except Exception:
            pass
        s.configure('Treeview',         font=FONT_LABEL, rowheight=24,
                    background=C_WHITE, fieldbackground=C_WHITE)
        s.configure('Treeview.Heading', font=('Segoe UI', 9, 'bold'),
                    background=C_HEADER, foreground='white')
        s.map('Treeview', background=[('selected', C_ACCENT)])

        # ── top chrome ───────────────────────────────────────────────────────
        chrome = tk.Frame(self, bg=C_SIDEBAR, height=56)
        chrome.pack(fill='x')
        chrome.pack_propagate(False)

        tk.Label(chrome, text="  🏭  BPR Manager Dashboard",
                 bg=C_SIDEBAR, fg='white',
                 font=('Segoe UI', 13, 'bold')).pack(side='left', padx=8, pady=10)

        # timestamp
        self._ts_label = tk.Label(chrome, text='', bg=C_SIDEBAR, fg='#85C1E9',
                                  font=FONT_SMALL)
        self._ts_label.pack(side='left', padx=14)

        # right-side controls
        right_ctrl = tk.Frame(chrome, bg=C_SIDEBAR)
        right_ctrl.pack(side='right', padx=14)

        # mode toggle
        tk.Label(right_ctrl, text="Period:", bg=C_SIDEBAR, fg='#BDC3C7',
                 font=FONT_LABEL).pack(side='left', padx=(0, 4))
        for val, lbl in [('daily', 'Daily'), ('monthly', 'Monthly')]:
            rb = tk.Radiobutton(right_ctrl, text=lbl,
                                variable=self._mode, value=val,
                                bg=C_SIDEBAR, fg='white',
                                selectcolor=C_SIDEBAR,
                                activebackground=C_SIDEBAR,
                                activeforeground='white',
                                font=('Segoe UI', 9, 'bold'),
                                command=self._on_mode_change)
            rb.pack(side='left', padx=3)

        tk.Frame(right_ctrl, bg='#3D5A80', width=1, height=26).pack(
            side='left', padx=10)

        refresh = tk.Label(right_ctrl, text=' ↻ Refresh ',
                           bg='#2E86C1', fg='white',
                           font=('Segoe UI', 9, 'bold'),
                           cursor='hand2', padx=6, pady=3)
        refresh.pack(side='left')
        refresh.bind('<Button-1>', lambda _e: self._load_data())
        refresh.bind('<Enter>', lambda _e: refresh.config(bg='#1A5276'))
        refresh.bind('<Leave>', lambda _e: refresh.config(bg='#2E86C1'))

        # ── hero + KPI strip (top section, fixed height) ──────────────────
        top_section = tk.Frame(self, bg=C_BG)
        top_section.pack(fill='x', padx=10, pady=(10, 4))

        # hero card (latest report)
        self._hero_outer, self._hero_inner = _card_frame(top_section)
        self._hero_outer.pack(side='left', fill='y', padx=(0, 8))
        self._hero_inner.configure(width=340)
        self._hero_inner.pack_propagate(False)
        self._build_hero_panel(self._hero_inner)

        # fleet KPI grid (right of hero)
        kpi_outer, kpi_inner = _card_frame(top_section)
        kpi_outer.pack(side='left', fill='both', expand=True)
        self._kpi_inner = kpi_inner

        # ── main notebook ─────────────────────────────────────────────────
        nb = ttk.Notebook(self)
        nb.pack(fill='both', expand=True, padx=10, pady=(0, 8))
        self._nb = nb
        self._make_activity_tab(nb)
        self._make_history_tab(nb)
        self._make_person_tab(nb)
        self._make_risk_tab(nb)

    # ── hero panel skeleton (populated later) ────────────────────────────────
    def _build_hero_panel(self, parent):
        """Build placeholder labels that _populate_hero will fill."""
        tk.Label(parent, text="LATEST REPORT", bg=C_HERO_BG, fg='#85C1E9',
                 font=('Segoe UI', 8, 'bold'), padx=14).pack(
                     anchor='w', pady=(12, 2))
        # verdict badge row
        badge_row = tk.Frame(parent, bg=C_HERO_BG)
        badge_row.pack(fill='x', padx=14, pady=(0, 6))
        self._hero_badge = tk.Label(badge_row, text='—', bg=C_HERO_BG,
                                    fg='white', font=('Segoe UI', 26, 'bold'))
        self._hero_badge.pack(side='left')

        _divider(parent, color='#2E4A70', pady=0)

        # meta grid
        meta = tk.Frame(parent, bg=C_HERO_BG)
        meta.pack(fill='x', padx=14, pady=8)
        self._hero_meta: dict = {}
        for key in ('Batch No.', 'Doc-Nr.', 'Prod. Code', 'Step',
                    'Processed', 'Reviewer'):
            row = tk.Frame(meta, bg=C_HERO_BG)
            row.pack(fill='x', pady=1)
            tk.Label(row, text=f'{key}:', bg=C_HERO_BG, fg='#85C1E9',
                     font=FONT_SMALL, width=11, anchor='w').pack(side='left')
            val_lbl = tk.Label(row, text='—', bg=C_HERO_BG, fg='white',
                                font=FONT_SMALL, anchor='w')
            val_lbl.pack(side='left', fill='x', expand=True)
            self._hero_meta[key] = val_lbl

        _divider(parent, color='#2E4A70', pady=0)

        # error / warning / info counters
        counts = tk.Frame(parent, bg=C_HERO_BG)
        counts.pack(fill='x', padx=14, pady=8)
        self._hero_counts: dict = {}
        for label, color in [('Errors', C_HERO_FAIL),
                               ('Warnings', '#E67E22'),
                               ('Info', '#2E86C1')]:
            col = tk.Frame(counts, bg=C_HERO_BG)
            col.pack(side='left', expand=True)
            num = tk.Label(col, text='—', bg=C_HERO_BG, fg=color,
                           font=('Segoe UI', 18, 'bold'))
            num.pack()
            tk.Label(col, text=label, bg=C_HERO_BG, fg='#7FB3D3',
                     font=FONT_SMALL).pack()
            self._hero_counts[label] = num

        _divider(parent, color='#2E4A70', pady=0)

        # top issues list
        tk.Label(parent, text='Top Issues', bg=C_HERO_BG, fg='#85C1E9',
                 font=('Segoe UI', 8, 'bold'), padx=14).pack(
                     anchor='w', pady=(8, 2))
        self._hero_issues = tk.Frame(parent, bg=C_HERO_BG)
        self._hero_issues.pack(fill='x', padx=14, pady=(0, 10))

        # tint the whole hero
        parent.configure(bg=C_HERO_BG)
        for child in parent.winfo_children():
            try:
                child.configure(bg=C_HERO_BG)
            except Exception:
                pass

    # ── tab builders ─────────────────────────────────────────────────────────
    def _make_activity_tab(self, nb):
        f = tk.Frame(nb, bg=C_BG)
        nb.add(f, text='  📊  Activity  ')

        left = tk.Frame(f, bg=C_CARD)
        left.pack(side='left', fill='both', expand=True, padx=(8, 4), pady=8)

        hdr_row = tk.Frame(left, bg=C_CARD)
        hdr_row.pack(fill='x', padx=12, pady=(10, 0))
        tk.Label(hdr_row, text='Batch Throughput', bg=C_CARD, fg=C_HEADER,
                 font=FONT_TITLE).pack(side='left')
        self._act_subtitle = tk.Label(hdr_row, text='', bg=C_CARD, fg=C_SUB,
                                      font=FONT_SMALL)
        self._act_subtitle.pack(side='right')

        self._act_canvas = tk.Canvas(left, bg=C_CARD, highlightthickness=0)
        self._act_canvas.pack(fill='both', expand=True, padx=8, pady=(4, 10))
        self._act_canvas.bind('<Configure>', lambda _e: self._populate_activity())

        # legend strip
        leg = tk.Frame(left, bg=C_CARD)
        leg.pack(fill='x', padx=12, pady=(0, 8))
        for color, lbl in [(C_PASS, 'Passed'), (C_FAIL, 'Failed'),
                            (C_PENDING, 'Pending')]:
            tk.Frame(leg, bg=color, width=12, height=12).pack(
                side='left', padx=(0, 4))
            tk.Label(leg, text=lbl, bg=C_CARD, fg=C_TEXT,
                     font=FONT_SMALL).pack(side='left', padx=(0, 14))

        # right summary panel
        right = tk.Frame(f, bg=C_CARD, width=200)
        right.pack(side='right', fill='y', padx=(0, 8), pady=8)
        right.pack_propagate(False)
        tk.Label(right, text='Period', bg=C_CARD, fg=C_HEADER,
                 font=FONT_TITLE).pack(anchor='w', padx=12, pady=(10, 4))
        self._summary_frame = tk.Frame(right, bg=C_CARD)
        self._summary_frame.pack(fill='both', expand=True, padx=10)

    def _make_history_tab(self, nb):
        f = tk.Frame(nb, bg=C_BG)
        nb.add(f, text='  📋  Batch History  ')

        # top: rule frequency chart
        top_outer, top_card = _card_frame(f)
        top_outer.pack(fill='x', padx=8, pady=(8, 4))
        tk.Label(top_card, text='Most Triggered Validation Rules',
                 bg=C_CARD, fg=C_HEADER, font=FONT_TITLE).pack(
                     anchor='w', padx=12, pady=(10, 2))
        self._rule_canvas = tk.Canvas(top_card, bg=C_CARD,
                                      highlightthickness=0, height=180)
        self._rule_canvas.pack(fill='x', padx=8, pady=(0, 10))
        self._rule_canvas.bind(
            '<Configure>', lambda _e: self._draw_horizontal_bars(
                self._rule_canvas, getattr(self, '_rule_data', [])))

        # bottom: batch table
        bot_outer, bot_card = _card_frame(f)
        bot_outer.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        tk.Label(bot_card, text='All Batches', bg=C_CARD, fg=C_HEADER,
                 font=FONT_TITLE).pack(anchor='w', padx=12, pady=(10, 2))

        cols = ('batch', 'doc_nr', 'prod_code', 'status',
                'errors', 'warnings', 'processed')
        tv = ttk.Treeview(bot_card, columns=cols, show='headings')
        hdrs = [('batch',    'Batch No.',  110),
                ('doc_nr',   'Doc-Nr.',    140),
                ('prod_code','Prod. Code', 100),
                ('status',   'Status',      80),
                ('errors',   'Errors',      65),
                ('warnings', 'Warnings',    75),
                ('processed','Processed',  150)]
        for cid, hdr, w in hdrs:
            tv.heading(cid, text=hdr,
                       command=lambda c=cid: self._sort_table(c))
            tv.column(cid, width=w, anchor='center')
        tv.tag_configure('validated', foreground=C_PASS)
        tv.tag_configure('failed',    foreground=C_FAIL)
        tv.tag_configure('pending',   foreground=C_PENDING)
        sb_y = ttk.Scrollbar(bot_card, command=tv.yview)
        sb_x = ttk.Scrollbar(bot_card, orient='horizontal', command=tv.xview)
        tv.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)
        sb_y.pack(side='right', fill='y', pady=(0, 4))
        sb_x.pack(side='bottom', fill='x', padx=4)
        tv.pack(fill='both', expand=True, padx=4, pady=(0, 4))
        self._all_tree = tv
        self._sort_col = None
        self._sort_rev = False

    def _make_person_tab(self, nb):
        f = tk.Frame(nb, bg=C_BG)
        nb.add(f, text='  👤  Personnel  ')
        outer, card = _card_frame(f)
        outer.pack(fill='both', expand=True, padx=8, pady=8)
        tk.Label(card, text='Personnel Activity', bg=C_CARD, fg=C_HEADER,
                 font=FONT_TITLE).pack(anchor='w', padx=12, pady=(10, 2))
        cols = ('kuerzel', 'name', 'batches', 'roles', 'last_seen')
        tv = ttk.Treeview(card, columns=cols, show='headings')
        for cid, hdr, w in [('kuerzel', 'Kürzel', 80),
                              ('name',    'Name',   220),
                              ('batches', 'Batches', 75),
                              ('roles',   'Roles',  120),
                              ('last_seen', 'Last Seen', 130)]:
            tv.heading(cid, text=hdr)
            tv.column(cid, width=w, anchor='center')
        sb = ttk.Scrollbar(card, command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y', pady=(0, 4))
        tv.pack(fill='both', expand=True, padx=4, pady=(0, 4))
        self._person_tree = tv

    # ── data loading ─────────────────────────────────────────────────────────
    def _load_data(self):
        session = get_session()
        try:
            batches  = session.query(Batch).order_by(Batch.created_at.desc()).all()
            val_all  = session.query(ValidationResult).all()
            sigs     = session.query(Signature).all()
            pers_all = session.query(Personnel).all()
            fields   = session.query(Field).all()
        finally:
            session.close()

        self._batches  = batches
        self._val_all  = val_all
        self._sigs     = sigs
        self._pers_all = pers_all
        self._fields   = fields

        ts = datetime.now().strftime('Updated %H:%M  ·  %d %b %Y')
        self._ts_label.config(text=ts)

        self._populate_hero()
        self._populate_kpi_grid()
        self._populate_activity()
        self._populate_history()
        self._populate_personnel()
        self._populate_risk_heatmap()

    def _on_mode_change(self):
        self._populate_activity()

    # ── hero (latest report) ─────────────────────────────────────────────────
    def _populate_hero(self):
        if not self._batches:
            return
        b   = self._batches[0]          # most recent
        bid = b.id
        b_vals = [v for v in self._val_all if v.batch_id == bid]

        errors  = sum(1 for v in b_vals if v.severity == 'error')
        warns   = sum(1 for v in b_vals if v.severity == 'warning')
        infos   = sum(1 for v in b_vals if v.severity == 'info')

        status = b.status or 'pending'
        if status == 'validated':
            badge_txt, badge_fg = '✔  PASS', C_HERO_PASS
        elif status == 'failed':
            badge_txt, badge_fg = '✘  FAIL', C_HERO_FAIL
        else:
            badge_txt, badge_fg = '⏳  PENDING', '#F0B429'

        self._hero_badge.config(text=badge_txt, fg=badge_fg)

        ts = b.processed_at or b.created_at
        date_str = ts.strftime('%Y-%m-%d  %H:%M') if ts else '—'
        # reviewer from signatures
        reviewer_kz = set()
        for s in self._sigs:
            if s.batch_id == bid and s.role == 'Geprüft' and s.kuerzel:
                reviewer_kz.add(s.kuerzel.strip())

        self._hero_meta['Batch No.'].config(text=b.batch_no or '—')
        self._hero_meta['Doc-Nr.'].config(text=b.doc_nr or '—')
        self._hero_meta['Prod. Code'].config(text=b.production_code or '—')
        self._hero_meta['Step'].config(text=b.process_step or '—')
        self._hero_meta['Processed'].config(text=date_str)
        self._hero_meta['Reviewer'].config(
            text=', '.join(sorted(reviewer_kz)) or '—')

        self._hero_counts['Errors'].config(text=str(errors))
        self._hero_counts['Warnings'].config(text=str(warns))
        self._hero_counts['Info'].config(text=str(infos))

        # top 4 issues for this batch
        for w in self._hero_issues.winfo_children():
            w.destroy()
        errs_first = sorted(b_vals,
                             key=lambda v: (0 if v.severity == 'error'
                                            else 1 if v.severity == 'warning'
                                            else 2, v.rule_id or ''))
        for v in errs_first[:4]:
            sev_color = (C_HERO_FAIL if v.severity == 'error'
                         else '#E67E22' if v.severity == 'warning'
                         else '#2E86C1')
            row = tk.Frame(self._hero_issues, bg=C_HERO_BG)
            row.pack(fill='x', pady=1)
            tk.Label(row, text='●', bg=C_HERO_BG, fg=sev_color,
                     font=FONT_SMALL).pack(side='left', padx=(0, 4))
            msg = (v.message or v.rule_id or '')[:52]
            tk.Label(row, text=msg, bg=C_HERO_BG, fg='#BDC3C7',
                     font=FONT_SMALL, anchor='w').pack(side='left', fill='x')
        if not errs_first:
            tk.Label(self._hero_issues, text='No issues found  ✔',
                     bg=C_HERO_BG, fg=C_HERO_PASS, font=FONT_LABEL).pack(
                         anchor='w')

    # ── fleet KPI grid ───────────────────────────────────────────────────────
    def _populate_kpi_grid(self):
        for w in self._kpi_inner.winfo_children():
            w.destroy()

        batches = self._batches
        total   = len(batches)
        passed  = sum(1 for b in batches if b.status == 'validated')
        failed  = sum(1 for b in batches if b.status == 'failed')
        pending = total - passed - failed
        errors  = sum(1 for v in self._val_all if v.severity == 'error')
        warns   = sum(1 for v in self._val_all if v.severity == 'warning')
        cutoff  = datetime.utcnow() - timedelta(days=30)
        recent  = sum(1 for b in batches
                      if b.created_at and b.created_at >= cutoff)
        pass_rate = f'{int(passed / total * 100)}%' if total else '—'

        title = tk.Label(self._kpi_inner, text='Fleet Overview',
                         bg=C_CARD, fg=C_HEADER, font=FONT_TITLE)
        title.grid(row=0, column=0, columnspan=4, sticky='w', padx=14,
                   pady=(10, 8))

        kpis = [
            ('Total\nBatches',  str(total),     C_HEADER,   '#EBF5FB'),
            ('Passed',          str(passed),     C_PASS,     C_PASS_LT),
            ('Failed',          str(failed),     C_FAIL,     C_FAIL_LT),
            ('Pending',         str(pending),    C_PENDING,  C_PEND_LT),
            ('Errors\n(total)', str(errors),     C_FAIL,     C_FAIL_LT),
            ('Warnings\n(total)',str(warns),     C_WARN,     C_WARN_LT),
            ('Last 30 days',    str(recent),     C_ACCENT,   '#EBF5FB'),
            ('Pass Rate',       pass_rate,       C_PASS,     C_PASS_LT),
        ]
        for idx, (lbl, val, fg, bg) in enumerate(kpis):
            col = idx % 4
            row = (idx // 4) + 1
            cell = tk.Frame(self._kpi_inner, bg=bg,
                            width=130, height=72)
            cell.grid(row=row, column=col, padx=6, pady=4, sticky='nsew')
            cell.grid_propagate(False)
            tk.Label(cell, text=val, bg=bg, fg=fg,
                     font=('Segoe UI', 20, 'bold')).pack(pady=(8, 0))
            tk.Label(cell, text=lbl, bg=bg, fg=C_TEXT,
                     font=FONT_SMALL, justify='center').pack()

        for c in range(4):
            self._kpi_inner.columnconfigure(c, weight=1)

    # ── activity chart ───────────────────────────────────────────────────────
    def _populate_activity(self):
        mode = self._mode.get()
        buckets: dict = defaultdict(lambda: {'pass': 0, 'fail': 0, 'pending': 0})
        for b in self._batches:
            dt  = b.created_at or datetime.utcnow()
            key = dt.strftime('%Y-%m-%d' if mode == 'daily' else '%Y-%m')
            st  = b.status or 'pending'
            if st == 'validated':
                buckets[key]['pass'] += 1
            elif st == 'failed':
                buckets[key]['fail'] += 1
            else:
                buckets[key]['pending'] += 1

        limit = 30 if mode == 'daily' else 12
        keys  = sorted(buckets.keys())[-limit:]
        data  = [buckets[k] for k in keys]

        if mode == 'daily':
            labels = [datetime.strptime(k, '%Y-%m-%d').strftime('%d\n%b')
                      for k in keys]
            sub = f'Last {len(keys)} days'
        else:
            labels = [datetime.strptime(k, '%Y-%m').strftime('%b\n%Y')
                      for k in keys]
            sub = f'Last {len(keys)} months'

        if hasattr(self, '_act_subtitle'):
            self._act_subtitle.config(text=sub)
        if hasattr(self, '_act_canvas'):
            self._draw_bar_chart(self._act_canvas, labels, data)

        # summary panel
        if not hasattr(self, '_summary_frame'):
            return
        for w in self._summary_frame.winfo_children():
            w.destroy()
        period_pass = sum(d['pass']    for d in data)
        period_fail = sum(d['fail']    for d in data)
        period_pend = sum(d['pending'] for d in data)
        period_tot  = period_pass + period_fail + period_pend

        for lbl, val, fg, bg in [
            ('Total',    str(period_tot),  C_TEXT, C_PEND_LT),
            ('✔ Passed', str(period_pass), C_PASS, C_PASS_LT),
            ('✘ Failed', str(period_fail), C_FAIL, C_FAIL_LT),
            ('◌ Pending',str(period_pend), C_PENDING, C_PEND_LT),
            ('Pass Rate',
             f'{int(period_pass/period_tot*100)}%' if period_tot else '—',
             C_PASS, C_PASS_LT),
        ]:
            row = tk.Frame(self._summary_frame, bg=C_CARD)
            row.pack(fill='x', pady=2)
            tk.Label(row, text=lbl, bg=C_CARD, fg=C_TEXT,
                     font=FONT_LABEL, anchor='w', width=11).pack(side='left')
            pill = tk.Label(row, text=val, bg=bg, fg=fg,
                            font=('Segoe UI', 9, 'bold'), padx=8, pady=2)
            pill.pack(side='right')

    def _draw_bar_chart(self, canvas: tk.Canvas, labels: list, data: list):
        canvas.delete('all')
        canvas.update_idletasks()
        W = canvas.winfo_width()
        H = canvas.winfo_height()
        if W < 60 or H < 40:
            W, H = 680, 240
        ml, mr, mt, mb = 36, 16, 18, 44
        cw = W - ml - mr
        ch = H - mt - mb
        n  = len(labels)
        if not n:
            return
        max_v = max((d['pass'] + d['fail'] + d['pending'] for d in data), default=1)
        max_v = max(max_v, 1)
        grp_w = cw / n
        bar_w = max(grp_w * 0.6, 4)

        # background
        canvas.create_rectangle(0, 0, W, H, fill=C_CARD, outline='')

        # horizontal grid
        for i in range(5):
            frac = i / 4
            y_px = mt + ch - ch * frac
            canvas.create_line(ml, y_px, W - mr, y_px,
                               fill=C_GRID, dash=(3, 4))
            canvas.create_text(ml - 4, y_px, anchor='e',
                               text=str(int(max_v * frac)),
                               fill=C_SUB, font=FONT_SMALL)

        for i, (label, d) in enumerate(zip(labels, data)):
            xc = ml + (i + 0.5) * grp_w
            y_base = mt + ch
            for seg_v, seg_c in [(d['pending'], C_PENDING),
                                  (d['fail'],    C_FAIL),
                                  (d['pass'],    C_PASS)]:
                if seg_v == 0:
                    continue
                sh = (seg_v / max_v) * ch
                x0, x1 = xc - bar_w / 2, xc + bar_w / 2
                y0, y1 = y_base - sh, y_base
                canvas.create_rectangle(x0, y0, x1, y1,
                                        fill=seg_c, outline='', width=0)
                if sh > 13:
                    canvas.create_text((x0 + x1) / 2, (y0 + y1) / 2,
                                       text=str(seg_v), fill='white',
                                       font=('Segoe UI', 7, 'bold'))
                y_base = y0
            canvas.create_text(xc, mt + ch + 5, anchor='n',
                               text=label, fill=C_TEXT, font=FONT_SMALL)

    # ── history tab data ─────────────────────────────────────────────────────
    def _populate_history(self):
        # rule frequency
        rule_counts: dict = defaultdict(int)
        for v in self._val_all:
            if v.severity in ('error', 'warning') and v.rule_id:
                rule_counts[v.rule_id] += 1
        self._rule_data = sorted(rule_counts.items(),
                                  key=lambda x: x[1], reverse=True)[:10]
        self._draw_horizontal_bars(self._rule_canvas, self._rule_data)

        # batch table
        batch_errs  = Counter(v.batch_id for v in self._val_all
                               if v.severity == 'error')
        batch_warns = Counter(v.batch_id for v in self._val_all
                               if v.severity == 'warning')
        tv = self._all_tree
        tv.delete(*tv.get_children())
        for b in self._batches:
            ts  = b.processed_at or b.created_at
            ds  = ts.strftime('%Y-%m-%d  %H:%M') if ts else '—'
            st  = b.status or 'pending'
            tag = st if st in ('validated', 'failed', 'pending') else 'pending'
            tv.insert('', 'end', iid=str(b.id), tags=(tag,),
                      values=(b.batch_no or '—',
                              b.doc_nr or '—',
                              b.production_code or '—',
                              st.upper(),
                              batch_errs.get(b.id, 0),
                              batch_warns.get(b.id, 0),
                              ds))

    def _draw_horizontal_bars(self, canvas: tk.Canvas, items: list):
        canvas.delete('all')
        canvas.update_idletasks()
        W = canvas.winfo_width() or 700
        H = canvas.winfo_height() or 180
        canvas.create_rectangle(0, 0, W, H, fill=C_CARD, outline='')
        if not items:
            canvas.create_text(W // 2, H // 2,
                               text='No rule violations recorded',
                               fill=C_SUB, font=('Segoe UI', 11))
            return
        ml, mr, mt, mb = 180, 55, 10, 10
        n     = len(items)
        row_h = (H - mt - mb) / max(n, 1)
        max_c = items[0][1]
        for i, (rule_id, cnt) in enumerate(items):
            yc    = mt + (i + 0.5) * row_h
            bar_h = max(row_h * 0.48, 5)
            bw    = (cnt / max_c) * (W - ml - mr)
            canvas.create_text(ml - 8, yc, anchor='e', text=rule_id,
                               fill=C_TEXT, font=FONT_SMALL)
            color = C_FAIL if cnt > max_c * 0.6 else C_WARN
            # background track
            canvas.create_rectangle(ml, yc - bar_h / 2,
                                    W - mr, yc + bar_h / 2,
                                    fill='#F2F3F4', outline='')
            # value bar
            canvas.create_rectangle(ml, yc - bar_h / 2,
                                    ml + bw, yc + bar_h / 2,
                                    fill=color, outline='')
            canvas.create_text(ml + bw + 5, yc, anchor='w',
                               text=str(cnt), fill=C_TEXT,
                               font=('Segoe UI', 8, 'bold'))

    def _sort_table(self, col: str):
        tv   = self._all_tree
        rows = [(tv.set(iid, col), iid) for iid in tv.get_children('')]
        rev  = (self._sort_col == col and not self._sort_rev)
        try:
            rows.sort(key=lambda x: int(x[0]) if x[0].isdigit() else x[0].lower(),
                      reverse=rev)
        except Exception:
            rows.sort(key=lambda x: x[0].lower(), reverse=rev)
        for idx, (_, iid) in enumerate(rows):
            tv.move(iid, '', idx)
        self._sort_col = col
        self._sort_rev = rev

    # ── personnel ─────────────────────────────────────────────────────────────
    def _populate_personnel(self):
        kuerzel_names:   dict = defaultdict(set)
        kuerzel_roles:   dict = defaultdict(set)
        kuerzel_batches: dict = defaultdict(set)
        kuerzel_last:    dict = {}

        for p in self._pers_all:
            if p.kuerzel:
                kuerzel_names[p.kuerzel.strip()].add(p.name or '')

        for s in self._sigs:
            kz = (s.kuerzel or '').strip()
            if not kz:
                continue
            kuerzel_batches[kz].add(s.batch_id)
            if s.role:
                kuerzel_roles[kz].add(s.role)
            try:
                dt = datetime.strptime(s.date, '%d.%m.%Y') if s.date else None
            except Exception:
                dt = None
            if dt and (kz not in kuerzel_last or dt > kuerzel_last[kz]):
                kuerzel_last[kz] = dt

        tv = self._person_tree
        tv.delete(*tv.get_children())
        all_kz = set(kuerzel_names) | set(kuerzel_batches)
        rows = []
        for kz in all_kz:
            names    = ', '.join(sorted(kuerzel_names[kz] - {''})) or '—'
            cnt      = len(kuerzel_batches[kz])
            roles    = ', '.join(sorted(kuerzel_roles[kz])) or '—'
            last     = kuerzel_last.get(kz)
            last_str = last.strftime('%Y-%m-%d') if last else '—'
            rows.append((kz, names, cnt, roles, last_str))
        rows.sort(key=lambda x: x[2], reverse=True)
        for row in rows:
            tv.insert('', 'end', values=row)

    # ── risk heatmap ─────────────────────────────────────────────────────────
    def _make_risk_tab(self, nb):
        """Risk Heatmap: statistical outliers (3σ) + error-prone zones."""
        f = tk.Frame(nb, bg=C_BG)
        nb.add(f, text='  🔥  Risk Heatmap  ')

        # header with export button
        hdr = tk.Frame(f, bg=C_BG)
        hdr.pack(fill='x', padx=10, pady=(8, 4))
        tk.Label(hdr, text='Statistical Outliers & Error-Prone Fields',
                 bg=C_BG, fg=C_HEADER, font=FONT_TITLE).pack(side='left')
        
        export_btn = tk.Label(hdr, text=' 📄 Export Report ',
                              bg=C_ACCENT, fg='white',
                              font=('Segoe UI', 9, 'bold'),
                              cursor='hand2', padx=8, pady=4)
        export_btn.pack(side='right')
        export_btn.bind('<Button-1>', lambda _e: self._export_risk_report())
        export_btn.bind('<Enter>', lambda _e: export_btn.config(bg='#1A5276'))
        export_btn.bind('<Leave>', lambda _e: export_btn.config(bg=C_ACCENT))

        # main container
        main = tk.Frame(f, bg=C_BG)
        main.pack(fill='both', expand=True, padx=10, pady=(0, 8))

        # left: heatmap visualization
        left_outer, left = _card_frame(main)
        left_outer.pack(side='left', fill='both', expand=True, padx=(0, 4))

        tk.Label(left, text='Field Risk Score (3σ Outliers)',
                 bg=C_CARD, fg=C_HEADER, font=('Segoe UI', 11, 'bold')).pack(
                     anchor='w', padx=12, pady=(10, 4))
        
        self._risk_canvas = tk.Canvas(left, bg=C_CARD, highlightthickness=0)
        self._risk_canvas.pack(fill='both', expand=True, padx=8, pady=(4, 10))
        self._risk_canvas.bind('<Configure>', lambda _e: self._populate_risk_heatmap())
        self._risk_canvas.bind('<Button-1>', self._on_risk_click)

        # legend
        leg = tk.Frame(left, bg=C_CARD)
        leg.pack(fill='x', padx=12, pady=(0, 8))
        for color, lbl in [(C_PASS, 'Low Risk (0-1σ)'), 
                           (C_WARN, 'Medium Risk (1-3σ)'),
                           (C_FAIL, 'High Risk (>3σ)')]:
            tk.Frame(leg, bg=color, width=12, height=12).pack(
                side='left', padx=(0, 4))
            tk.Label(leg, text=lbl, bg=C_CARD, fg=C_TEXT,
                     font=FONT_SMALL).pack(side='left', padx=(0, 14))

        # right: drill-down table
        right_outer, right = _card_frame(main)
        right_outer.pack(side='right', fill='both', expand=False, padx=(4, 0))
        right.configure(width=420)
        right.pack_propagate(False)

        tk.Label(right, text='Outlier Details',
                 bg=C_CARD, fg=C_HEADER, font=('Segoe UI', 11, 'bold')).pack(
                     anchor='w', padx=12, pady=(10, 4))
        
        cols = ('field', 'batch', 'value', 'mean', 'sigma', 'risk')
        hdrs = ('Field', 'Batch', 'Value', 'Mean', 'σ', 'Risk')
        widths = (140, 80, 70, 60, 50, 60)
        
        tv = ttk.Treeview(right, columns=cols, show='headings', height=18)
        for cid, hdr, w in zip(cols, hdrs, widths):
            tv.heading(cid, text=hdr)
            tv.column(cid, width=w, anchor='center')
        
        sb = ttk.Scrollbar(right, command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y', pady=(0, 4))
        tv.pack(fill='both', expand=True, padx=4, pady=(0, 4))
        self._risk_tree = tv

    def _populate_risk_heatmap(self):
        """Calculate 3-sigma outliers and visualize risk zones."""
        if not hasattr(self, '_fields'):
            return
        
        canvas = self._risk_canvas
        if canvas.winfo_width() <= 1:
            return
        
        canvas.delete('all')
        
        # group numeric fields by name
        field_values = defaultdict(list)
        for fld in self._fields:
            if not fld.parsed_value:
                continue
            try:
                val = float(fld.parsed_value.replace(',', '.'))
                field_values[fld.field_name].append((fld.batch_id, val, fld))
            except (ValueError, AttributeError):
                continue
        
        # calculate statistics and outliers
        risk_data = []
        for fname, val_list in field_values.items():
            if len(val_list) < 3:  # need minimum data for stats
                continue
            
            values = [v[1] for v in val_list]
            mean_val = statistics.mean(values)
            
            try:
                stdev_val = statistics.stdev(values)
            except statistics.StatisticsError:
                stdev_val = 0
            
            if stdev_val == 0:
                continue
            
            # find outliers
            outliers = []
            for batch_id, val, fld in val_list:
                sigma_dist = abs(val - mean_val) / stdev_val
                if sigma_dist > 1.0:  # show values >1σ
                    risk = 'HIGH' if sigma_dist > 3.0 else 'MEDIUM'
                    outliers.append((batch_id, val, sigma_dist, risk, fld))
            
            if outliers:
                max_sigma = max(o[2] for o in outliers)
                risk_data.append((fname, len(outliers), max_sigma, mean_val, stdev_val, outliers))
        
        # store for drill-down
        self._risk_data = risk_data
        
        # sort by max sigma (highest risk first)
        risk_data.sort(key=lambda x: x[2], reverse=True)
        
        # draw heatmap bars
        w = canvas.winfo_width() - 40
        h = canvas.winfo_height() - 20
        
        if not risk_data:
            canvas.create_text(w / 2, h / 2, text='No statistical outliers detected',
                               fill=C_SUB, font=('Segoe UI', 12))
            self._risk_tree.delete(*self._risk_tree.get_children())
            return
        
        n_fields = len(risk_data)
        bar_h = min(30, (h - 20) / n_fields - 4)
        
        for i, (fname, count, max_sigma, mean_val, stdev, outliers) in enumerate(risk_data):
            y = 10 + i * (bar_h + 4)
            
            # risk color
            if max_sigma > 3.0:
                color = C_FAIL
            elif max_sigma > 1.0:
                color = C_WARN
            else:
                color = C_PASS
            
            # background track
            canvas.create_rectangle(10, y, w - 10, y + bar_h,
                                    fill='#EAECEE', outline='')
            
            # risk bar (proportional to sigma)
            bar_w = min((max_sigma / 5.0) * (w - 120), w - 120)
            canvas.create_rectangle(10, y, 10 + bar_w, y + bar_h,
                                    fill=color, outline='')
            
            # label
            label = fname[:25] + '...' if len(fname) > 25 else fname
            canvas.create_text(15, y + bar_h / 2, anchor='w',
                               text=label, fill='white' if bar_w > 100 else C_TEXT,
                               font=('Segoe UI', 9, 'bold'))
            
            # count + sigma
            info = f'{count} outlier{"s" if count > 1 else ""} · {max_sigma:.1f}σ'
            canvas.create_text(w - 15, y + bar_h / 2, anchor='e',
                               text=info, fill=C_TEXT,
                               font=('Segoe UI', 8, 'bold'))
        
        # populate drill-down table (top 50 outliers)
        tv = self._risk_tree
        tv.delete(*tv.get_children())
        
        all_outliers = []
        for fname, count, max_sigma, mean_val, stdev, outliers in risk_data:
            for batch_id, val, sigma_dist, risk, fld in outliers:
                all_outliers.append((fname, batch_id, val, mean_val, sigma_dist, risk, stdev))
        
        all_outliers.sort(key=lambda x: x[4], reverse=True)  # sort by sigma
        
        for fname, batch_id, val, mean_val, sigma_dist, risk, stdev in all_outliers[:50]:
            # get batch number
            batch = next((b for b in self._batches if b.id == batch_id), None)
            batch_str = batch.batch_no[:10] if batch and batch.batch_no else f'#{batch_id}'
            
            tv.insert('', 'end', values=(
                fname[:20],
                batch_str,
                f'{val:.2f}',
                f'{mean_val:.2f}',
                f'{sigma_dist:.1f}',
                risk
            ), tags=(risk,))
        
        # color-code rows
        tv.tag_configure('HIGH', background=C_FAIL_LT)
        tv.tag_configure('MEDIUM', background=C_WARN_LT)

    def _on_risk_click(self, event):
        """Handle click on risk heatmap for drill-down."""
        if not hasattr(self, '_risk_data') or not self._risk_data:
            return
        
        canvas = self._risk_canvas
        h = canvas.winfo_height() - 20
        n_fields = len(self._risk_data)
        bar_h = min(30, (h - 20) / n_fields - 4)
        
        y = event.y
        idx = int((y - 10) / (bar_h + 4))
        
        if 0 <= idx < len(self._risk_data):
            fname, count, max_sigma, mean_val, stdev, outliers = self._risk_data[idx]
            msg = f"Field: {fname}\n\n"
            msg += f"Mean: {mean_val:.2f}\n"
            msg += f"Std Dev: {stdev:.2f}\n"
            msg += f"Outliers: {count}\n"
            msg += f"Max Deviation: {max_sigma:.1f}σ\n\n"
            msg += "Click 'Export Report' to save detailed analysis."
            messagebox.showinfo("Risk Analysis", msg)

    def _export_risk_report(self):
        """Export risk analysis as CSV compliance report."""
        if not hasattr(self, '_risk_data') or not self._risk_data:
            messagebox.showwarning("No Data", "No risk data to export.")
            return
        
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"risk_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        
        if not path:
            return
        
        try:
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['BPR Risk Analysis Report'])
                writer.writerow(['Generated:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
                writer.writerow([])
                writer.writerow(['Field Name', 'Batch ID', 'Batch No', 'Value', 'Mean', 'Std Dev', 'Sigma Distance', 'Risk Level'])
                
                for fname, count, max_sigma, mean_val, stdev, outliers in self._risk_data:
                    for batch_id, val, sigma_dist, risk, fld in outliers:
                        batch = next((b for b in self._batches if b.id == batch_id), None)
                        batch_no = batch.batch_no if batch else f'#{batch_id}'
                        
                        writer.writerow([
                            fname, batch_id, batch_no,
                            f'{val:.2f}', f'{mean_val:.2f}', f'{stdev:.2f}',
                            f'{sigma_dist:.2f}', risk
                        ])
            
            messagebox.showinfo("Success", f"Risk report exported to:\n{path}")
        except Exception as e:
            messagebox.showerror("Export Failed", f"Error: {e}")

