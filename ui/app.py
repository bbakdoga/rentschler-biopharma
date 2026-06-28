"""
Main application window — built with tkinter (no extra dependencies).
"""
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

from PIL import Image, ImageTk

from db.session import get_session
from db.models import Batch, Page, ValidationResult, Field, Signature, Personnel
from config import OCR_CONFIDENCE_WARN
from ui.dashboard import ManagerDashboard

SEVERITY_COLOR = {
    'error':   '#FFCCCC',
    'warning': '#FFF2CC',
    'info':    '#DDEBF7',
}

# Distinct, high-contrast colours cycled for the viewer's bounding boxes and
# their matching field rows.
_BOX_COLORS = [
    '#E6194B', '#3CB44B', '#4363D8', '#F58231', '#911EB4', '#42D4F4',
    '#F032E6', '#BFAF00', '#469990', '#9A6324', '#800000', '#000075',
]


def _readable_fg(hex_color: str) -> str:
    """Black or white text, whichever is readable on the given background."""
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return '#000000' if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else '#FFFFFF'


def _is_uncertain(conf) -> bool:
    """True when a field's OCR confidence is known and below the threshold."""
    return conf is not None and conf < OCR_CONFIDENCE_WARN


class BPRApp:

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("BPR Validation Tool")
        self.root.geometry("1280x820")
        self.root.configure(bg='#F5F7FA')
        self._processing = False
        # Page-viewer state
        self._viewer_pages = []
        self._viewer_idx = 0
        self._viewer_photo = None
        self._viewer_box_items = {}
        self._viewer_item_to_idx = {}
        self._build()
        self._refresh_batches()

    # ── UI construction ───────────────────────────────────────────────────────
    def _build(self):
        self._style()

        # ── toolbar ──────────────────────────────────────────────────────────
        bar = tk.Frame(self.root, bg='#1F3864', height=52)
        bar.pack(fill='x')
        bar.pack_propagate(False)
        tk.Label(bar, text="BPR Validation Tool", bg='#1F3864', fg='white',
                 font=('Arial', 14, 'bold')).pack(side='left', padx=16, pady=12)
        self._toolbar_button(bar, "Dashboard", self._open_dashboard, '#1A5276', padx=4)
        self._toolbar_button(bar, "Export Excel", self._export, '#27AE60', padx=8)
        self._toolbar_button(bar, "Export Boxed PDF", self._export_boxed_pdf,
                             '#8E44AD', padx=4)
        self._upload_btn = self._toolbar_button(bar, "Upload PDF", self._upload, '#2980B9')
        self._toolbar_button(bar, "Delete Batch", self._delete_batch, '#C0392B')

        # ── progress bar (hidden until processing) ───────────────────────────
        self._prog_var = tk.DoubleVar()
        self._prog_frame = tk.Frame(self.root, bg='#F5F7FA')
        self._prog = ttk.Progressbar(self._prog_frame, variable=self._prog_var,
                                     maximum=100)
        self._prog.pack(side='left', fill='x', expand=True, padx=(8, 6), pady=4)
        self._prog_pct = tk.Label(self._prog_frame, text="0%", bg='#F5F7FA',
                                  fg='#1F3864', font=('Arial', 9, 'bold'), width=5)
        self._prog_pct.pack(side='right', padx=(0, 10))

        # ── main pane ─────────────────────────────────────────────────────────
        pane = ttk.PanedWindow(self.root, orient='horizontal')
        pane.pack(fill='both', expand=True, padx=6, pady=6)

        # left: batch list
        left = tk.Frame(pane, bg='white', relief='flat')
        pane.add(left, weight=1)
        tk.Label(left, text="Processed Batches", bg='white',
                 font=('Arial', 10, 'bold'), fg='#1F3864').pack(anchor='w', padx=8, pady=(8, 2))

        self._batch_tree = ttk.Treeview(left, columns=('bno', 'pc', 'status'),
                                         show='headings', selectmode='browse')
        for col, hdr, w in [('bno', 'Batch No.', 110),
                             ('pc',  'Prod.Code', 90),
                             ('status', 'Status', 80)]:
            self._batch_tree.heading(col, text=hdr)
            self._batch_tree.column(col, width=w, anchor='center')
        sb_l = ttk.Scrollbar(left, command=self._batch_tree.yview)
        self._batch_tree.configure(yscrollcommand=sb_l.set)
        sb_l.pack(side='right', fill='y')
        self._batch_tree.pack(fill='both', expand=True, padx=4, pady=4)
        self._batch_tree.bind('<<TreeviewSelect>>', self._on_select)
        self._batch_tree.tag_configure('validated', foreground='#1A7A3C')
        self._batch_tree.tag_configure('failed',    foreground='#C0392B')

        # right: detail tabs
        right = tk.Frame(pane, bg='#F5F7FA')
        pane.add(right, weight=4)

        # summary cards
        cards = tk.Frame(right, bg='#F5F7FA')
        cards.pack(fill='x', padx=6, pady=(4, 0))
        self._c_err  = self._card(cards, "Errors",   "—", '#C0392B')
        self._c_warn = self._card(cards, "Warnings", "—", '#E67E22')
        self._c_info = self._card(cards, "Info",     "—", '#2980B9')
        self._c_stat = self._card(cards, "Status",   "—", '#7F8C8D')

        # tabs
        nb = ttk.Notebook(right)
        nb.pack(fill='both', expand=True, padx=4, pady=4)
        self._nb = nb

        self._tab_val  = self._make_tab(nb, "Validation Results",
                                         ['#', 'Sev', 'Rule', '§', 'Pg', 'Message'],
                                         [30, 55, 70, 60, 35, 500])
        self._tab_sig  = self._make_tab(nb, "Signatures",
                                         ['Role', 'Section', 'Kürzel', 'Date', 'Page'],
                                         [90, 80, 60, 100, 40])
        self._tab_fld  = self._make_tab(nb, "Extracted Fields",
                                         ['Section', 'Field', 'Value', 'Unit'],
                                         [70, 200, 180, 60])
        self._tab_pers = self._make_tab(nb, "Personnel",
                                         ['Name', 'Kürzel'],
                                         [260, 80])
        self._make_viewer_tab(nb)

        for sev, color in SEVERITY_COLOR.items():
            self._tab_val.tag_configure(sev, background=color)

        # status bar
        self._status_var = tk.StringVar(value="Ready — upload a PDF to begin.")
        tk.Label(self.root, textvariable=self._status_var,
                 relief='sunken', anchor='w', bg='#ECF0F1',
                 font=('Arial', 9)).pack(fill='x', side='bottom')

    def _toolbar_button(self, parent, text, command, color, padx=4):
        """A colored, clickable label that behaves like a button.

        macOS ignores ``bg`` on native ``tk.Button`` widgets (they render
        white), so we style a ``tk.Label`` instead, which honors colors on
        every platform.
        """
        btn = tk.Label(parent, text=f"  {text}  ", bg=color, fg='white',
                       font=('Arial', 10), cursor='hand2', padx=6, pady=4)
        btn.pack(side='right', padx=padx, pady=10)
        btn._base_color = color
        btn._enabled = True

        def on_click(_e):
            if btn._enabled:
                command()

        btn.bind('<Button-1>', on_click)
        btn.bind('<Enter>', lambda _e: btn._enabled and btn.config(bg=self._darken(color)))
        btn.bind('<Leave>', lambda _e: btn.config(bg=color if btn._enabled else '#95A5A6'))
        return btn

    @staticmethod
    def _darken(hex_color, factor=0.85):
        r = int(int(hex_color[1:3], 16) * factor)
        g = int(int(hex_color[3:5], 16) * factor)
        b = int(int(hex_color[5:7], 16) * factor)
        return f'#{r:02X}{g:02X}{b:02X}'

    @staticmethod
    def _set_button_enabled(btn, enabled):
        btn._enabled = enabled
        btn.config(bg=btn._base_color if enabled else '#95A5A6',
                   cursor='hand2' if enabled else 'arrow')

    def _style(self):
        s = ttk.Style()
        s.theme_use('clam')
        s.configure('TNotebook.Tab', font=('Arial', 10))
        s.configure('Treeview',      font=('Arial', 10), rowheight=22)
        s.configure('Treeview.Heading', font=('Arial', 10, 'bold'))

    def _card(self, parent, title, value, color):
        f = tk.Frame(parent, bg=color, width=110, height=68)
        f.pack(side='left', padx=5, pady=4)
        f.pack_propagate(False)
        vl = tk.Label(f, text=value, bg=color, fg='white', font=('Arial', 20, 'bold'))
        vl.pack(pady=(8, 0))
        tk.Label(f, text=title, bg=color, fg='white', font=('Arial', 9)).pack()
        return {'val': vl, 'frame': f, 'color': color}

    def _make_tab(self, nb, title, headers, widths):
        frame = tk.Frame(nb, bg='white')
        nb.add(frame, text=title)
        cols = [h.lower().replace(' ', '_') for h in headers]
        tv   = ttk.Treeview(frame, columns=cols, show='headings')
        for col, hdr, w in zip(cols, headers, widths):
            tv.heading(col, text=hdr)
            tv.column(col, width=w, anchor='w')
        sb = ttk.Scrollbar(frame, command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        tv.pack(fill='both', expand=True)
        return tv

    # ── side-by-side page viewer ───────────────────────────────────────────────
    def _make_viewer_tab(self, nb):
        frame = tk.Frame(nb, bg='white')
        nb.add(frame, text="Page Viewer")

        # navigation bar
        nav = tk.Frame(frame, bg='#EAEDF1')
        nav.pack(fill='x')
        tk.Button(nav, text='◀ Prev', command=self._viewer_prev,
                  relief='flat').pack(side='left', padx=(6, 2), pady=4)
        tk.Button(nav, text='Next ▶', command=self._viewer_next,
                  relief='flat').pack(side='left', padx=2, pady=4)
        self._viewer_nav = tk.Label(nav, text='—', bg='#EAEDF1',
                                    fg='#1F3864', font=('Arial', 10, 'bold'))
        self._viewer_nav.pack(side='left', padx=12)

        pane = ttk.PanedWindow(frame, orient='horizontal')
        pane.pack(fill='both', expand=True)

        # left: scanned page + bounding boxes
        left = tk.Frame(pane, bg='#2B2B2B')
        pane.add(left, weight=3)
        self._viewer_canvas = tk.Canvas(left, bg='#2B2B2B', highlightthickness=0)
        self._viewer_canvas.pack(fill='both', expand=True)
        self._viewer_canvas.bind('<Configure>', lambda _e: self._viewer_draw())
        self._viewer_canvas.bind('<Button-1>', self._viewer_canvas_click)

        # right: extracted fields, colour-matched to the boxes
        rightf = tk.Frame(pane, bg='white')
        pane.add(rightf, weight=2)
        tk.Label(rightf, text="Extracted fields on this page", bg='white',
                 font=('Arial', 10, 'bold'), fg='#1F3864').pack(
                     anchor='w', padx=6, pady=(6, 2))
        tv = ttk.Treeview(rightf, columns=('param', 'value', 'conf'),
                          show='headings')
        tv.heading('param', text='Parameter'); tv.column('param', width=180, anchor='w')
        tv.heading('value', text='Value');     tv.column('value', width=110, anchor='w')
        tv.heading('conf', text='OCR');         tv.column('conf', width=66, anchor='center')
        sb = ttk.Scrollbar(rightf, command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        tv.pack(fill='both', expand=True, padx=(6, 0), pady=4)
        tv.bind('<<TreeviewSelect>>', self._viewer_on_select)
        self._viewer_tree = tv

        legend = tk.Label(
            rightf, bg='white', fg='#7F8C8D', font=('Arial', 8),
            text="Solid box = confident   ·   dashed box / ⚠ = uncertain OCR "
                 "(likely handwriting)")
        legend.pack(anchor='w', padx=6, pady=(0, 4))

    def _viewer_clear(self):
        self._viewer_pages = []
        self._viewer_idx = 0
        self._viewer_box_items = {}
        self._viewer_item_to_idx = {}
        if hasattr(self, '_viewer_tree'):
            self._viewer_tree.delete(*self._viewer_tree.get_children())
        if hasattr(self, '_viewer_canvas'):
            self._viewer_canvas.delete('all')
        if hasattr(self, '_viewer_nav'):
            self._viewer_nav.config(text='—')

    def _viewer_load_batch(self, batch_id: int):
        session = get_session()
        try:
            pages = (session.query(Page)
                     .filter(Page.batch_id == batch_id)
                     .order_by(Page.page_num).all())
            data = []
            for pg in pages:
                flds = (session.query(Field)
                        .filter(Field.page_id == pg.id,
                                Field.bbox_x.isnot(None))
                        .order_by(Field.id).all())
                data.append({
                    'page_num': pg.page_num, 'section': pg.section,
                    'image_path': pg.image_path,
                    'ocr_w': pg.ocr_width, 'ocr_h': pg.ocr_height,
                    'fields': [{'param': f.field_name,
                                'value': f.parsed_value or f.raw_value or '',
                                'box': (f.bbox_x, f.bbox_y, f.bbox_w, f.bbox_h),
                                'conf': f.confidence}
                               for f in flds],
                })
            self._viewer_pages = data
            self._viewer_idx = 0
            self._viewer_show_page()
        finally:
            session.close()

    def _viewer_prev(self):
        if self._viewer_pages and self._viewer_idx > 0:
            self._viewer_idx -= 1
            self._viewer_show_page()

    def _viewer_next(self):
        if self._viewer_pages and self._viewer_idx < len(self._viewer_pages) - 1:
            self._viewer_idx += 1
            self._viewer_show_page()

    def _viewer_show_page(self):
        tv = self._viewer_tree
        tv.delete(*tv.get_children())
        if not self._viewer_pages:
            self._viewer_nav.config(text='—')
            self._viewer_canvas.delete('all')
            return
        info = self._viewer_pages[self._viewer_idx]
        n_uncertain = sum(1 for f in info['fields'] if _is_uncertain(f['conf']))
        nav = (f"Page {info['page_num']} / {len(self._viewer_pages)}     "
               f"§{info['section'] or '?'}     "
               f"{len(info['fields'])} field(s)")
        if n_uncertain:
            nav += f"     ⚠ {n_uncertain} uncertain"
        self._viewer_nav.config(text=nav)
        for i, fld in enumerate(info['fields']):
            color = _BOX_COLORS[i % len(_BOX_COLORS)]
            tag = f'c{i}'
            tv.tag_configure(tag, background=color, foreground=_readable_fg(color))
            conf = fld['conf']
            if conf is None:
                ctext = '—'
            elif _is_uncertain(conf):
                ctext = f'⚠ {int(conf)}%'
            else:
                ctext = f'{int(conf)}%'
            tv.insert('', 'end', iid=str(i),
                      values=(fld['param'], fld['value'], ctext), tags=(tag,))
        self._viewer_draw()

    def _viewer_draw(self):
        c = self._viewer_canvas
        c.delete('all')
        self._viewer_box_items = {}
        self._viewer_item_to_idx = {}
        if not self._viewer_pages:
            return
        info = self._viewer_pages[self._viewer_idx]
        path = info['image_path']
        if not path or not Path(path).exists():
            c.create_text(16, 16, anchor='nw', fill='white',
                          text='(page image not available — re-process the document)')
            return
        try:
            img = Image.open(path).convert('RGB')
        except Exception:
            c.create_text(16, 16, anchor='nw', fill='white',
                          text='(could not open page image)')
            return

        iw, ih = img.size
        cw = max(c.winfo_width(), 50)
        ch = max(c.winfo_height(), 50)
        s = min(cw / iw, ch / ih)
        dw, dh = max(int(iw * s), 1), max(int(ih * s), 1)
        self._viewer_photo = ImageTk.PhotoImage(
            img.resize((dw, dh), Image.LANCZOS))
        ox, oy = (cw - dw) // 2, (ch - dh) // 2
        c.create_image(ox, oy, anchor='nw', image=self._viewer_photo)

        ocr_w = info['ocr_w'] or iw
        ocr_h = info['ocr_h'] or ih
        fx = (iw / ocr_w) * s
        fy = (ih / ocr_h) * s

        sel = self._viewer_tree.selection()
        sel_i = int(sel[0]) if sel else None
        for i, fld in enumerate(info['fields']):
            x, y, w, h = fld['box']
            color = _BOX_COLORS[i % len(_BOX_COLORS)]
            opts = {'outline': color, 'width': (4 if i == sel_i else 2)}
            if _is_uncertain(fld['conf']):       # dashed = OCR unsure
                opts['dash'] = (6, 4)
                opts['width'] = max(opts['width'], 3)
            item = c.create_rectangle(
                ox + x * fx, oy + y * fy,
                ox + (x + w) * fx, oy + (y + h) * fy, **opts)
            self._viewer_box_items[i] = item
            self._viewer_item_to_idx[item] = i
        if sel_i is not None and sel_i in self._viewer_box_items:
            c.tag_raise(self._viewer_box_items[sel_i])

    def _viewer_on_select(self, _event=None):
        for item in self._viewer_box_items.values():
            self._viewer_canvas.itemconfig(item, width=2)
        sel = self._viewer_tree.selection()
        if sel:
            item = self._viewer_box_items.get(int(sel[0]))
            if item:
                self._viewer_canvas.itemconfig(item, width=4)
                self._viewer_canvas.tag_raise(item)

    def _viewer_canvas_click(self, event):
        c = self._viewer_canvas
        for item in reversed(c.find_overlapping(event.x, event.y,
                                                event.x, event.y)):
            if item in self._viewer_item_to_idx:
                i = self._viewer_item_to_idx[item]
                self._viewer_tree.selection_set(str(i))
                self._viewer_tree.see(str(i))
                return

    # ── actions ───────────────────────────────────────────────────────────────
    def _upload(self):
        if self._processing:
            messagebox.showinfo("Busy",
                                "A document is already being processed. "
                                "Please wait for it to finish.")
            return
        path = filedialog.askopenfilename(
            title="Select BPR PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        if not path:
            return
        self._processing = True
        self._set_button_enabled(self._upload_btn, False)
        self._status_var.set(f"Processing {Path(path).name}…")
        self._prog_frame.pack(fill='x', side='bottom',
                              before=self.root.winfo_children()[-1])
        self._prog_var.set(0)
        self._prog_pct.config(text="0%")

        def run():
            try:
                from processor import BPRProcessor
                proc = BPRProcessor()

                def cb(cur, tot, msg=''):
                    pct = cur / tot * 100
                    self.root.after(0, self._update_progress, pct, msg)

                bid = proc.process(path, cb)
                self.root.after(0, self._done, bid)
            except Exception as e:
                self.root.after(0, messagebox.showerror, "Error", str(e))
                self.root.after(0, self._status_var.set, f"Error: {e}")
                self.root.after(0, self._prog_frame.pack_forget)
                self.root.after(0, self._finish_processing)

        threading.Thread(target=run, daemon=True).start()

    def _update_progress(self, pct, msg):
        self._prog_var.set(pct)
        self._prog_pct.config(text=f"{int(pct)}%")
        if msg:
            self._status_var.set(msg)

    def _finish_processing(self):
        self._processing = False
        self._set_button_enabled(self._upload_btn, True)

    def _done(self, batch_id: int):
        self._finish_processing()
        self._update_progress(100, "Processing complete.")
        self._prog_frame.pack_forget()
        self._status_var.set("Processing complete.")
        self._refresh_batches()
        # auto-select the new batch
        self._batch_tree.selection_set(str(batch_id))
        self._batch_tree.see(str(batch_id))
        self._load(batch_id)

    def _export(self):
        sel = self._batch_tree.selection()
        if not sel:
            messagebox.showwarning("No selection", "Select a batch first.")
            return
        bid = int(sel[0])
        path = filedialog.asksaveasfilename(
            title="Save Report",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")]
        )
        if not path:
            return
        try:
            from reports.excel_exporter import ExcelExporter
            ExcelExporter().export(bid, path)
            messagebox.showinfo("Exported", f"Report saved:\n{path}")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))

    def _export_boxed_pdf(self):
        """Save a vector-annotated copy of the selected batch's source PDF."""
        sel = self._batch_tree.selection()
        if not sel:
            messagebox.showwarning("No selection", "Select a batch first.")
            return

        bid = int(sel[0])
        path = filedialog.asksaveasfilename(
            title="Save PDF with Bounding Boxes",
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
        )
        if not path:
            return

        try:
            from reports.annotated_pdf_exporter import AnnotatedPDFExporter
            AnnotatedPDFExporter().export(bid, path)
            messagebox.showinfo("Exported", f"Annotated PDF saved:\n{path}")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))

    def _delete_batch(self):
        sel = self._batch_tree.selection()
        if not sel:
            messagebox.showwarning("No selection", "Select a batch first.")
            return
        bid = int(sel[0])
        if not messagebox.askyesno("Confirm", f"Delete batch {bid} and all its data?"):
            return
        session = get_session()
        try:
            b = session.get(Batch, bid)
            if b:
                session.delete(b)
                session.commit()
        finally:
            session.close()
        self._refresh_batches()
        for tv in (self._tab_val, self._tab_sig, self._tab_fld, self._tab_pers):
            tv.delete(*tv.get_children())
        for card in (self._c_err, self._c_warn, self._c_info, self._c_stat):
            card['val'].config(text='—')
        self._viewer_clear()

    # ── data loading ──────────────────────────────────────────────────────────
    def _refresh_batches(self):
        session = get_session()
        try:
            batches = (session.query(Batch)
                       .order_by(Batch.created_at.desc()).all())
            self._batch_tree.delete(*self._batch_tree.get_children())
            for b in batches:
                tag = b.status or ''
                self._batch_tree.insert('', 'end', iid=str(b.id),
                                        values=(b.batch_no or '—',
                                                b.production_code or '—',
                                                b.status or '—'),
                                        tags=(tag,))
        finally:
            session.close()

    def _on_select(self, _event):
        sel = self._batch_tree.selection()
        if sel:
            self._load(int(sel[0]))

    def _load(self, batch_id: int):
        session = get_session()
        try:
            batch = session.get(Batch, batch_id)
            if not batch:
                return

            results = (session.query(ValidationResult)
                       .filter(ValidationResult.batch_id == batch_id)
                       .order_by(ValidationResult.severity,
                                 ValidationResult.rule_id).all())

            err  = sum(1 for r in results if r.severity == 'error')
            warn = sum(1 for r in results if r.severity == 'warning')
            info = sum(1 for r in results if r.severity == 'info')

            self._c_err['val'].config(text=str(err))
            self._c_warn['val'].config(text=str(warn))
            self._c_info['val'].config(text=str(info))

            ok = err == 0
            self._c_stat['val'].config(text='PASS' if ok else 'FAIL')
            color = '#27AE60' if ok else '#C0392B'
            self._c_stat['frame'].config(bg=color)
            self._c_stat['val'].config(bg=color)

            # Validation results tab
            tv = self._tab_val
            tv.delete(*tv.get_children())
            for i, r in enumerate(results, 1):
                sev = r.severity or 'info'
                tv.insert('', 'end',
                          values=(i, sev.upper()[:4], r.rule_id or '',
                                  r.section or '', r.page_num or '',
                                  r.message or ''),
                          tags=(sev,))

            # Signatures tab
            tv = self._tab_sig
            tv.delete(*tv.get_children())
            sigs = (session.query(Signature)
                    .filter(Signature.batch_id == batch_id).all())
            for s in sigs:
                tv.insert('', 'end',
                          values=(s.role, s.section, s.kuerzel, s.date, s.page_num))

            # Fields tab
            tv = self._tab_fld
            tv.delete(*tv.get_children())
            fields = (session.query(Field)
                      .filter(Field.batch_id == batch_id).all())
            for f in fields:
                tv.insert('', 'end',
                          values=(f.section, f.field_name,
                                  f.parsed_value, f.unit))

            # Personnel tab
            tv = self._tab_pers
            tv.delete(*tv.get_children())
            pers = (session.query(Personnel)
                    .filter(Personnel.batch_id == batch_id).all())
            for p in pers:
                tv.insert('', 'end', values=(p.name, p.kuerzel))

            self._status_var.set(
                f"Batch {batch.batch_no or batch_id}  ·  "
                f"{err} error(s)  {warn} warning(s)  {info} info"
            )
        finally:
            session.close()
        self._viewer_load_batch(batch_id)
    def _open_dashboard(self):
        """Open (or raise) the manager dashboard window."""
        if hasattr(self, '_dashboard_win') and self._dashboard_win.winfo_exists():
            self._dashboard_win.lift()
            self._dashboard_win.focus_force()
            return
        self._dashboard_win = ManagerDashboard(self.root)
    # ── run ───────────────────────────────────────────────────────────────────
    def run(self):
        self.root.mainloop()
