"""
BPRProcessor — ties PDF ingestion → OCR → field extraction → DB → validation.
"""
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

from ingest.pdf_processor import PDFProcessor
from ingest.image_preprocess import ImagePreprocessor
from ocr.tesseract_engine import TesseractEngine
from extract.field_extractor import (
    extract_cover, extract_personnel, extract_signatures,
    extract_checkboxes, extract_timestamps, extract_calculations,
    parse_date, parse_number, extract_soll_range,
)
from extract import generic_extractor as generic
from validate.engine import ValidationEngine
from db.models import Batch, Page, Field, Signature, Personnel
from db.session import get_session


# ── section identification ────────────────────────────────────────────────────
_SECTION_MARKERS = [
    ('Beteiligte Personen',               '1'),
    ('MITGELTENDE REGELUNGEN',            '2'),
    ('DEFINITIONEN',                      '3'),
    ('PROZESSVORBEREITUNG',               '4'),
    ('Zyklus',                            '5.1'),
    ('Produktionsbereich',                '5.2'),
    ('Verwendete Intermediate',           '5.3'),
    ('Bilanzierung',                      '5.3.1'),
    ('Temperierung B10-PP (Zyklus 1)',    '5.4'),
    ('Temperierung B10-PP (Zyklus 2)',    '5.5'),
    ('Pooling',                           '5.6'),
    ('Hergestelltes Intermediat B20-ST',  '5.7'),
    ('Probenanalytik',                    '5.7.4'),
    ('Haltezeit',                         '5.7.6'),
    ('ProzessOfen',                       '5.8'),
    ('Berechnung der Beladung',           '5.9'),
    ('Setup des Backsystems',             '5.10'),
    ('Vorbereitung',                      '5.11'),
    ('Überprüfung der Puffermengen',      '5.12'),
    ('Berechnung des Loadvolumens',       '5.12.3'),
    ('Überprüfung der tatsächlichen',     '5.12.4'),
    ('Überprüfung der Haltezeit',         '5.12.5'),
    ('Überprüfung der Temperierung',      '5.12.6'),
    ('Hergestelltes Intermediat B20-PP',  '5.13'),
    ('Nachbereitung',                     '5.14'),
    ('BEMERKUNGEN',                       '6'),
    ('ABWEICHUNGEN',                      '8'),
    ('REVIEW',                            '9'),
    ('ABKÜRZUNGSVERZEICHNIS',             '10'),
]


def _identify_section(text: str, page_num: int) -> str:
    t = text.lower()
    for marker, sec_id in _SECTION_MARKERS:
        if marker.lower() in t:
            return sec_id
    return f'p{page_num}'


# ── specialist field extractors per section ───────────────────────────────────
_NAMED_FIELDS: dict[str, list[tuple[str, str, str]]] = {
    # section → [(field_name, regex_pattern, unit)]
    '5.2': [
        ('hygienezone',   r'Hygienezone.*?Soll\s*[≤<]\s*3\s*HZ\s+(\d+)', 'HZ'),
    ],
    '5.6.2': [
        ('wippgeschwindigkeit', r'Wippgeschwindigkeit.*?(\d{2,3})',       'Hübe/min'),
        ('start_ueberfuehrung', r'Start Überführung\s+(\d{1,2}:\d{2})',  ''),
        ('ende_ueberfuehrung',  r'Ende Überführung\s+(\d{1,2}:\d{2})',   ''),
        ('start_homogenisieren',r'Start Homogenisieren\s+(\d{1,2}:\d{2})',''),
        ('ende_homogenisieren', r'Ende Homogenisieren\s+(\d{1,2}:\d{2})', ''),
    ],
    '5.8': [
        ('baker_five_cm',   r'Baker Five.*?(\d+[.,]\d+)',  'cm'),
        ('baker_seven_cm',  r'Baker Seven.*?(\d+[.,]\d+)', 'cm'),
        ('v_ofen_bak_b20',  r'Baker Eigth.*?(\d+[.,]\d+)', 'L'),
        ('anzahl_zyklen',   r'Anzahl.*?Zyklen.*?(\d+)',    ''),
    ],
    '5.12.1': [
        ('ph_equi',          r'pH Equi.*?([\d.,]+)',         ''),
        ('lf_equi',          r'LF Equi.*?([\d.,]+)',         'mS/cm'),
        ('start_auftrag',    r'Start Auftrag\s+(\d{1,2}:\d{2})', ''),
        ('ende_elution',     r'Ende Elution\s+(\d{1,2}:\d{2})',  ''),
        ('erlaubte_standzeit',r'Erlaubte Standzeit.*?(\d{1,2}[./]\d{2}[./]\d{4}\s+\d{1,2}:\d{2})', ''),
        ('baker_four',       r'Baker Four.*?Soll.*?([\d.,]+)',    ''),
        ('baker_five_ms',    r'Baker Five.*?Soll.*?75.*?([\d.,]+)','mS/cm'),
    ],
    '5.12.3': [
        ('start_auftrag',          r'Start Auftrag\s+(\d{1,2}:\d{2})',         ''),
        ('ende_auftrag',           r'Ende Auftrag\s+(\d{1,2}:\d{2})',          ''),
        ('dauer_auftrag_stunden',  r'Dauer Auftrag\s+Stunden.*?=\s*([\d.,]+)', 'h'),
        ('mittlerer_fluss_vor_ofen',r'Mittlerer Fluss vor Ofen\s+([\d.,]+)',   'l/h'),
        ('mittlerer_fluss_pumpe_a', r'Mittlerer Fluss Pumpe A\s+([\d.,]+)',    'l/h'),
        ('load_vol',               r'Load Volumen.*?=\s*([\d.,]+)',             'L'),
    ],
    '5.12.4': [
        ('c_b20st_cake',    r'C\s+B20[- ]ST\s+Cake.*?=\s*([\d.,]+)',  'g/L'),
        ('actual_beladung', r'Beladung.*?=\s*([\d.,]+)',               'g/L'),
        ('v_netto_npz',     r'V\s+B20[- ]ST\s+Netto\s+nPZ.*?([\d.,]+)','L'),
    ],
}

_DATETIME_FIELD_LABELS = {
    'start_haltezeit':           r'Start Haltezeit\s+(\d{1,2}[./]\d{2}[./]\d{4}\s*/?\s*\d{1,2}:\d{2})',
    'erlaubte_haltezeit':        r'Erlaubte Haltezeit\s+(\d{1,2}[./]\d{2}[./]\d{4}\s*/?\s*\d{1,2}:\d{2})',
    'probenzug':                 r'(?:Probenzug|® Probenzug)\s+(\d{1,2}[./]\d{2}[./]\d{4}\s*/?\s*\d{1,2}:\d{2})',
    'start_prozessverzoegerung': r'Start Prozessverzögerung\s+(\d{1,2}:\d{2})',
    'ende_prozessverzoegerung':  r'Ende Prozessverzögerung\s+(\d{1,2}:\d{2})',
    'start_temperierung_z1':     r'Start Temperierung\s+\(Übertrag Kapitel 5\.4\.1\)\s+(\d{1,2}[./]\d{2}[./]\d{4}\s*/?\s*\d{1,2}:\d{2})',
    'ende_temperierung_z1':      r'Ende Temperierung\s+\(Übertrag Kapitel 5\.12\.1\)\s+(\d{1,2}[./]\d{2}[./]\d{4}\s*/?\s*\d{1,2}:\d{2})',
    'start_temperierung_z2':     r'Start Temperierung\s+\(Übertrag Kapitel 5\.5\.1\)\s+(\d{1,2}[./]\d{2}[./]\d{4}\s*/?\s*\d{1,2}:\d{2})',
    'ende_temperierung_z2':      r'Ende Temperierung\s+\(Übertrag Kapitel 5\.12\.1\)\s+(\d{1,2}[./]\d{2}[./]\d{4}\s*/?\s*\d{1,2}:\d{2})',
}

# ── slot counting for line-count rule ─────────────────────────────────────────
_SLOT_RE = re.compile(r'_\s+_\s+_')   # "_ _ _" → 3 slots


def _count_slots(text: str) -> int:
    slots = 0
    for m in _SLOT_RE.finditer(text):
        slots += m.group(0).count('_')
    return slots


class BPRProcessor:

    def __init__(self):
        self.pre     = ImagePreprocessor()
        self.ocr     = TesseractEngine()
        self.val_eng = ValidationEngine()

    # ── public entry point ────────────────────────────────────────────────────
    def process(self, pdf_path: str,
                progress: Callable[[int, int, str], None] | None = None) -> int:
        session = get_session()
        try:
            batch = Batch(file_path=pdf_path, status='processing',
                          created_at=datetime.utcnow())
            session.add(batch)
            # Commit the batch row right away so we don't hold a write lock
            # on the whole DB for the entire (minutes-long) OCR run.
            session.commit()

            pdf = PDFProcessor(pdf_path)
            total = pdf.page_count()

            def report(done_pages, step):
                # Reserve the last 5% of the bar for the validation pass.
                if progress:
                    progress(done_pages / total * 95, 100,
                             f"Page {pg + 1} of {total}  ·  {step}")

            for pg in range(total):
                report(pg, "rendering image…")
                img = pdf.get_page_image(pg)

                report(pg + 0.3, "cleaning up image…")
                # OCR image (binarised) and a colour display image that shares
                # the same geometry, so field boxes line up on the display.
                proc_img, disp_img = self.pre.process_full_page_with_display(img)
                img_path = pdf.page_image_path(pg)
                disp_img.save(img_path, "PNG")

                report(pg + 0.5, "reading text (OCR)…")
                # One OCR pass that yields word boxes; the plain text is
                # reconstructed from them for section identification.
                try:
                    words = self.ocr.extract_words_with_conf(proc_img)
                    text  = generic.words_to_text(words)
                except Exception:
                    words, text = [], self.ocr.extract_text(proc_img)

                # Fall back to embedded PDF text if OCR is empty
                if not text.strip():
                    text  = pdf.get_embedded_text(pg)
                    words = []

                report(pg + 0.9, "extracting fields…")
                section = _identify_section(text, pg + 1)

                # We deliberately do NOT persist the page's full text /
                # explanatory prose — only the extracted parameter→value
                # pairs are stored (explanations must not be kept).
                page = Page(batch_id=batch.id, page_num=pg + 1,
                            section=section, raw_text=None,
                            image_path=str(img_path),
                            ocr_width=proc_img.width,
                            ocr_height=proc_img.height)
                session.add(page)
                session.flush()

                self._ingest_page(batch, page, text, section, words, session)
                # Commit per page so the write lock is released frequently
                # rather than held for the entire document.
                session.commit()

            pdf.close()

            if progress:
                progress(97, 100, "Running validation rules…")

            self.val_eng.run(batch, session)
            session.commit()
            return batch.id

        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ── per-page field ingestion ──────────────────────────────────────────────
    def _ingest_page(self, batch: Batch, page: Page,
                     text: str, section: str, words: list, session):
        bid = batch.id
        pid = page.id

        def add_field(name, raw, parsed, unit='', conf=None, bbox=None):
            bx, by, bw, bh = bbox if bbox else (None, None, None, None)
            session.add(Field(
                batch_id=bid, page_id=pid, section=section,
                field_name=name, raw_value=str(raw),
                parsed_value=str(parsed), unit=unit, confidence=conf,
                bbox_x=bx, bbox_y=by, bbox_w=bw, bbox_h=bh,
            ))

        # ── PRIMARY: generic, form-agnostic parameter → value extraction ─────
        #   No parameter names or patterns are hard-coded here — this reads
        #   whatever label/value pairs the form presents and associates each
        #   response to its parameter, while dropping explanatory text.
        pairs = (generic.extract_fields(words) if words
                 else generic.extract_fields_from_text(text))
        for pr in pairs:
            add_field(pr['parameter'], pr['value'], pr['value'],
                      conf=pr.get('conf'), bbox=pr.get('bbox'))

        # ── cover page ──────────────────────────────────────────────────────
        if page.page_num == 1:
            info = extract_cover(text)
            batch.doc_nr           = info.get('doc_nr', batch.doc_nr)
            batch.revision         = info.get('revision', batch.revision)
            batch.project_code     = info.get('project_code', batch.project_code)
            batch.batch_no         = info.get('batch_no', batch.batch_no)
            batch.production_code  = info.get('production_code', batch.production_code)
            batch.production_code_ds = info.get('production_code_ds', batch.production_code_ds)
            batch.process_step     = info.get('prozessstufe', batch.process_step)
            batch.sap_material_nr  = info.get('sap_material_nr', batch.sap_material_nr)
            batch.man_nr           = info.get('man_nr', batch.man_nr)
            batch.gqq_generated_at = info.get('gqq_date', batch.gqq_generated_at)

            # Slot counting for batch_no
            slots = _count_slots(text)
            if slots:
                add_field('batch_no_expected_digits', slots, slots)

        # ── personnel page ──────────────────────────────────────────────────
        if 'Beteiligte Personen' in text or section == '1':
            for p in extract_personnel(text):
                session.add(Personnel(
                    batch_id=bid,
                    name=p['name'],
                    kuerzel=p['kuerzel'],
                ))

        # ── signatures (every page) ─────────────────────────────────────────
        for sig in extract_signatures(text, section):
            session.add(Signature(
                batch_id=bid, section=section,
                role=sig['role'], kuerzel=sig['kuerzel'],
                date=sig['date'], page_num=page.page_num,
            ))

        # ── checkboxes ───────────────────────────────────────────────────────
        for cb in extract_checkboxes(text):
            state = 'checked' if cb['checked'] else 'none'
            add_field('checkbox', cb['context'], state)

        # ── generic timestamps ───────────────────────────────────────────────
        for ts in extract_timestamps(text):
            raw = f"{ts['date']} / {ts['time']}"
            add_field(ts['label'], raw, raw)

        # ── named datetime fields ────────────────────────────────────────────
        for fname, pat in _DATETIME_FIELD_LABELS.items():
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                add_field(fname, m.group(1), m.group(1))

        # ── calculation values ────────────────────────────────────────────────
        calc = extract_calculations(text)
        for key, val in calc.items():
            add_field(key, val, val)

        # ── section-specific named fields ─────────────────────────────────────
        for spec_section, specs in _NAMED_FIELDS.items():
            if section != spec_section:
                continue
            for fname, pat, unit in specs:
                m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
                if m:
                    raw = m.group(1).strip()
                    num = parse_number(raw)
                    add_field(fname, raw, str(num) if num is not None else raw, unit)

        # ── mass-volume fields (generic, any section) ─────────────────────────
        for fname, pat, unit in [
            ('m_tara',   r'm\s+Tara\s+([\d.,]+)',   'kg'),
            ('m_brutto', r'm\s+Brutto\s+(?:vPZ\s+)?([\d.,]+)', 'kg'),
            ('m_netto',  r'm\s+Netto\s+(?:vPZ\s+)?([\d.,]+)',  'kg'),
            ('v_netto',  r'V\s+Netto\s+(?:vPZ\s+)?([\d.,]+)',  'L'),
            ('density',  r'ρ\s*=\s*([\d.,]+)',                  'kg/L'),
            ('m_b10pp_z1', r'm\s+B10-PP\s+Z1\s*\[g\]\s*=.*?=\s*([\d.,]+)', 'g'),
            ('m_b10pp_z2', r'm\s+B10-PP\s+Z2\s*\[g\]\s*=.*?=\s*([\d.,]+)', 'g'),
            ('m_b20st',    r'm\s+B20-ST\s*\[g\]\s*=.*?=\s*([\d.,]+)',       'g'),
            ('beladung',   r'Beladung\s*\[g\s*Cake/L.*?\]\s*=.*?=\s*([\d.,]+)', 'g/L'),
            ('v_ofen_bak_b20', r'V\s+Ofen\s+BAK\s+B20.*?([\d.,]+)',         'L'),
            ('v_netto_npz',    r'V\s+(?:B20-ST\s+)?Netto\s+nPZ.*?([\d.,]+)','L'),
        ]:
            m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
            if m:
                raw = m.group(1).strip()
                num = parse_number(raw)
                # only add if not already present from calc extractor
                existing = session.query(Field).filter(
                    Field.batch_id == bid,
                    Field.page_id  == pid,
                    Field.field_name == fname,
                ).first()
                if not existing:
                    add_field(fname, raw, str(num) if num is not None else raw, unit)
