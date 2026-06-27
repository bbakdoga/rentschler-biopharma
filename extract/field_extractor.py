"""
Pattern-based extraction for Rentschler-style BPR documents.
All regex patterns are anchored to the German form labels visible on the printed template.
"""
import re
from datetime import datetime
from typing import Optional


# ── shared patterns ──────────────────────────────────────────────────────────
DATE_RE      = re.compile(r'\b(\d{1,2})[./\-](\d{2})[./\-](\d{4})\b')
TIME_RE      = re.compile(r'\b(\d{1,2}):(\d{2})\b')
DATETIME_RE  = re.compile(
    r'(\d{1,2}[./]\d{2}[./]\d{4})\s*/?\s*(\d{1,2}:\d{2})'
)
NUMBER_RE    = re.compile(r'[-+]?\d+[,.]?\d*')
RANGE_RE     = re.compile(
    r'Soll\s*:\s*'
    r'(?:[\d.,]+\s+)?'                   # optional nominal value
    r'\(?\s*([\d.,]+)\s*[-–]\s*([\d.,]+)\s*\)?'
)
KUERZEL_RE   = re.compile(r'\b([a-z]{2,5})\b', re.IGNORECASE)


def parse_date(text: str) -> Optional[datetime]:
    m = DATE_RE.search(text)
    if m:
        try:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return datetime(y, mo, d)
        except ValueError:
            pass
    return None


def parse_number(text: str) -> Optional[float]:
    t = text.strip().replace(',', '.')
    m = NUMBER_RE.search(t)
    if m:
        try:
            return float(m.group())
        except ValueError:
            pass
    return None


def extract_soll_range(text: str) -> Optional[tuple[float, float]]:
    m = RANGE_RE.search(text)
    if m:
        try:
            lo = float(m.group(1).replace(',', '.'))
            hi = float(m.group(2).replace(',', '.'))
            return (lo, hi)
        except ValueError:
            pass
    return None


# ── cover page ────────────────────────────────────────────────────────────────
_COVER_PATTERNS = {
    'prozessstufe':        r'Prozessstufe\s*[:\s]+([A-Z]\d+)',
    'sap_material_nr':     r'SAP-Materialnummer\s*[:\s]+(\d{5,})',
    'man_nr':              r'Zugehörige MAN\s*[:\s]+([A-Z0-9\-]+)',
    'production_code':     r'Production Code\s*[:\s]+([\d\s]+)',
    'production_code_ds':  r'Production Code DS\s*[:\s]+([\d\s]+)',
    'batch_no':            r'Batch No\.\s*[:\s]+([\d\s]+)',
    'doc_nr':              r'Dok-Nr\.\s*[:\s]*([A-Z0-9\-]+)',
    'revision':            r'Rev\.\s*(\d+)',
    'project_code':        r'Projektcode\s*[:\s]+([A-Z0-9]+)',
    'gqq_date':            r'generiert am\s*.*?\)\s*[:\s]*([\d.]+\s*/\s*\w+)',
}


def extract_cover(text: str) -> dict:
    result = {}
    for key, pattern in _COVER_PATTERNS.items():
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            result[key] = m.group(1).strip()
    return result


# ── personnel (page 4) ────────────────────────────────────────────────────────
def extract_personnel(text: str) -> list[dict]:
    """
    Heuristic: look for lines that end with a short alpha abbreviation (the Kürzel).
    Works for 'Hans Mustermann   han' style entries.
    """
    people = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        last = parts[-1]
        if 2 <= len(last) <= 5 and last.isalpha():
            name = ' '.join(parts[:-1])
            if len(name) >= 3:
                people.append({'name': name, 'kuerzel': last.lower()})
    return people


# ── signatures ────────────────────────────────────────────────────────────────
_SIG_RE = re.compile(
    r'(Bearbeitet|Gepr[üu]ft)\s*[:\s]*\(?Datum/K.rzel\)?[:\s]*'
    r'(\d{1,2}[./]\d{2}[./]\d{4})\s*/\s*([a-z]{2,5})',
    re.IGNORECASE
)

_SIG_LOOSE_RE = re.compile(
    # Sometimes OCR merges or adds spaces; this looser form catches those
    r'(Bearbeitet|Gepr[üu]ft)[^\n]{0,40}'
    r'(\d{1,2}[./]\d{2}[./]\d{4})\s*/\s*([a-z]{2,5})',
    re.IGNORECASE
)


def extract_signatures(text: str, section: str) -> list[dict]:
    sigs = []
    for pattern in (_SIG_RE, _SIG_LOOSE_RE):
        for m in pattern.finditer(text):
            role = m.group(1)
            role = 'Geprüft' if role.lower().startswith('gepr') else 'Bearbeitet'
            entry = {'role': role, 'date': m.group(2),
                     'kuerzel': m.group(3).lower(), 'section': section}
            # deduplicate
            if entry not in sigs:
                sigs.append(entry)
    return sigs


# ── checkbox states ───────────────────────────────────────────────────────────
_CHECKBOX_RE = re.compile(
    r'([O©®⊙⊕◉✓☑●Ø0°]\s*(?:Ja|Nein)|(?:Ja|Nein)\s*[O©®⊙⊕◉✓☑●Ø0°])',
    re.UNICODE | re.IGNORECASE
)
_SELECTED = set('©®⊙⊕◉✓☑●Ø')
_UNSELECTED = {'O', '0', 'o'}


def classify_checkbox(token: str) -> tuple[str, bool]:
    """Return (label, is_checked)."""
    upper = token.upper()
    label = 'Ja' if 'JA' in upper else 'Nein'
    char = token.strip()[0]
    checked = char in _SELECTED or (char not in _UNSELECTED and char.isalpha() is False)
    return label, checked


def extract_checkboxes(text: str) -> list[dict]:
    boxes = []
    for m in _CHECKBOX_RE.finditer(text):
        label, checked = classify_checkbox(m.group(0))
        # capture preceding label text for context (up to 80 chars)
        start = max(0, m.start() - 80)
        ctx = text[start:m.start()].replace('\n', ' ').strip()
        boxes.append({'context': ctx[-60:], 'label': label, 'checked': checked,
                      'pos': m.start()})
    return boxes


# ── timestamps ────────────────────────────────────────────────────────────────
_TS_RE = re.compile(
    r'((?:Start|Ende|Beginn)\s+[\w\s\-]+?)\s+'
    r'(\d{1,2}[./]\d{2}[./]\d{4})\s*/?\s*(\d{1,2}:\d{2})',
    re.IGNORECASE
)
_TS_UHR_RE = re.compile(
    r'([®⊙•●]?\s*[\w\s\-]{3,50}?)\s+'
    r'(\d{1,2}[./]\d{2}[./]\d{4})\s*/?\s*(\d{1,2}:\d{2})\s*Uhr',
    re.IGNORECASE
)


def extract_timestamps(text: str) -> list[dict]:
    seen = set()
    ts = []
    for pattern in (_TS_RE, _TS_UHR_RE):
        for m in pattern.finditer(text):
            key = (m.group(2), m.group(3))
            if key in seen:
                continue
            seen.add(key)
            ts.append({
                'label': m.group(1).strip().lower().replace(' ', '_'),
                'date':  m.group(2),
                'time':  m.group(3),
            })
    return ts


# ── mass / volume calculations ────────────────────────────────────────────────
_CALC_PATTERNS = {
    'm_tara':   r'm\s+Tara\s+([\d.,]+)',
    'm_brutto': r'm\s+Brutto(?:\s+(?:vPZ|nPZ))?\s+([\d.,]+)',
    'm_netto':  r'm\s+Netto(?:\s+(?:vPZ|nPZ))?\s+([\d.,]+)',
    'v_netto':  r'V\s+Netto(?:\s+(?:vPZ|nPZ))?\s+([\d.,]+)',
    'density':  r'ρ\s*=\s*([\d.,]+)',
    'c_value':  r'[Cc]\s+[A-Z0-9\-]+\s+\(Blocking IPC\)\s+([\d.,]+)',
    'beladung': r'(?:Beladung|Load)\s*\[?g[^\]]*\]?\s*=\s*.*?=\s*([\d.,]+)',
    'load_vol': r'Load\s+Volumen\s+\[L\].*?=\s*([\d.,]+)',
}


def extract_calculations(text: str) -> dict[str, float]:
    vals = {}
    for key, pat in _CALC_PATTERNS.items():
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            v = parse_number(m.group(1))
            if v is not None:
                vals[key] = v
    return vals
