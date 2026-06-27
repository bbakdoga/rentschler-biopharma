"""
Generic, form-agnostic label → value extraction.

This module deliberately contains **no** form-specific parameter names,
section titles, or hand-written field patterns.  It pairs each printed
label on a form with the value filled in next to it, using either:

  • the geometry of the OCR'd words (preferred — a large horizontal gap
    or a colon separates a label from its response), or
  • the column whitespace of plain text (fallback for embedded PDF text).

Because each form "looks slightly different", nothing here is anchored to a
particular document.  Explanatory / template prose that has no associated
response value is **not** returned, so it is never stored or exported.
"""
import re
import statistics

# What a filled-in "response" tends to look like: a date, a time, a number
# or percentage, or a checkbox mark.  Used to tell a real value apart from
# leftover prose.
_VALUE_TOKEN = re.compile(
    r'(\d{1,2}[./]\d{1,2}[./]\d{2,4}'   # date   e.g. 12.03.2024
    r'|\d{1,2}:\d{2}'                    # time   e.g. 14:05
    r'|[-+]?\d+(?:[.,]\d+)?\s*%?'        # number / percentage
    r'|[☑☒✓✗])'                          # checkbox mark
)


# ── line reconstruction from word boxes ───────────────────────────────────────
def _group_lines(words: list[dict]) -> list[list[dict]]:
    """Cluster OCR words into visual lines by their vertical position."""
    if not words:
        return []
    heights = [w['h'] for w in words if w.get('h')]
    tol = (statistics.median(heights) / 2) if heights else 8
    ordered = sorted(words, key=lambda w: (w['y'], w['x']))

    lines: list[list[dict]] = []
    cur: list[dict] = []
    cur_y: float | None = None
    for w in ordered:
        cy = w['y'] + w['h'] / 2
        if cur_y is None or abs(cy - cur_y) <= tol:
            cur.append(w)
            cur_y = cy if cur_y is None else (cur_y + cy) / 2
        else:
            lines.append(sorted(cur, key=lambda x: x['x']))
            cur, cur_y = [w], cy
    if cur:
        lines.append(sorted(cur, key=lambda x: x['x']))
    return lines


def _line_text(line_words: list[dict]) -> str:
    """Join one line's words, inserting a double space where the horizontal
    gap is wide enough to mark a column break (label │ value)."""
    if not line_words:
        return ''
    widths = [w['w'] / max(len(w['text']), 1) for w in line_words if w.get('w')]
    char_w = statistics.median(widths) if widths else 8
    out = [line_words[0]['text']]
    for i in range(1, len(line_words)):
        prev = line_words[i - 1]
        gap = line_words[i]['x'] - (prev['x'] + prev['w'])
        out.append('  ' if gap > char_w * 3 else ' ')
        out.append(line_words[i]['text'])
    return ''.join(out)


def words_to_text(words: list[dict]) -> str:
    """Reconstruct a plain-text page from word boxes (for section ID etc.)."""
    return '\n'.join(_line_text(line) for line in _group_lines(words))


# ── label / value splitting & filtering ───────────────────────────────────────
def _clean_label(s: str) -> str:
    s = re.sub(r'\s{2,}', ' ', s.strip())
    s = re.sub(r'[._\s]+$', '', s)       # strip dotted leaders / trailing fill
    return s.rstrip(':').strip()


def _clean_value(s: str) -> str:
    return re.sub(r'^[._\s]+', '', s.strip()).strip()


def _label_colon(line: str) -> int:
    """Index of the first colon that separates a label from a value, i.e. a
    colon that is *not* part of a time like ``14:05`` (digit:digit)."""
    for i, ch in enumerate(line):
        if ch == ':':
            prev = line[i - 1] if i > 0 else ''
            nxt = line[i + 1] if i + 1 < len(line) else ''
            if not (prev.isdigit() and nxt.isdigit()):
                return i
    return -1


def _split(line: str) -> tuple[str, str] | None:
    """Split a line into (label, value) on a colon or a column gap."""
    if not line.strip():
        return None
    # Prefer a label colon (ignoring colons inside times such as 14:05).
    ci = _label_colon(line)
    if ci != -1:
        label, value = line[:ci], line[ci + 1:]
        if label.strip() and value.strip():
            return label, value
    # Otherwise split on a column gap (2+ spaces).
    parts = re.split(r'\s{2,}', line.strip())
    if len(parts) >= 2 and parts[0].strip() and parts[-1].strip():
        if parts[0].strip() != parts[-1].strip():
            return parts[0], parts[-1]
    return None


def _accept(label: str, value: str) -> bool:
    """Keep only genuine parameter→response pairs; drop explanatory prose."""
    if not label or not value:
        return False
    if len(label) > 80:                  # a paragraph, not a field label
        return False
    nwords = len(value.split())
    if _VALUE_TOKEN.search(value):       # has a number/date/time/mark → a value
        return nwords <= 8               # but still not a whole paragraph
    # No numeric/date token: only accept a single compact token (a code or
    # Kürzel such as 'abc' / 'PASS'). Multi-word phrases without a value are
    # almost always explanatory prose, which must not be kept.
    if nwords == 1 and len(value) <= 20:
        return True
    return False


def _union_bbox(words: list[dict]) -> tuple[int, int, int, int]:
    """Smallest box covering all given word boxes → (x, y, w, h)."""
    x0 = min(w['x'] for w in words)
    y0 = min(w['y'] for w in words)
    x1 = max(w['x'] + w['w'] for w in words)
    y1 = max(w['y'] + w['h'] for w in words)
    return (x0, y0, x1 - x0, y1 - y0)


def _pair_from_words(line_words: list[dict]) -> dict | None:
    """Pair a label with its value at the word level, retaining the value's
    bounding box so it can be drawn on the page image."""
    if len(line_words) < 2:
        return None
    widths = [w['w'] / max(len(w['text']), 1) for w in line_words if w.get('w')]
    char_w = statistics.median(widths) if widths else 8

    split_idx: int | None = None
    # 1) A word ending in ':' marks the label/value boundary.
    for i in range(len(line_words) - 1):
        if line_words[i]['text'].endswith(':'):
            split_idx = i + 1
            break
    # 2) Otherwise the widest column gap, if it's clearly dominant.
    if split_idx is None:
        best_gap, best_i = 0.0, None
        for i in range(1, len(line_words)):
            prev = line_words[i - 1]
            gap = line_words[i]['x'] - (prev['x'] + prev['w'])
            if gap > best_gap:
                best_gap, best_i = gap, i
        if best_i is not None and best_gap > char_w * 3:
            split_idx = best_i

    if not split_idx or split_idx >= len(line_words):
        return None

    label = _clean_label(' '.join(w['text'] for w in line_words[:split_idx]))
    value_words = line_words[split_idx:]
    value = _clean_value(' '.join(w['text'] for w in value_words))
    if not _accept(label, value):
        return None
    # Lowest word confidence in the value → if any token is shaky (e.g. a
    # handwritten entry), the whole field is flagged as uncertain.
    confs = [w['conf'] for w in value_words
             if w.get('conf') is not None and w['conf'] >= 0]
    conf = min(confs) if confs else None
    return {'parameter': label, 'value': value,
            'bbox': _union_bbox(value_words), 'conf': conf}


def extract_fields(words: list[dict]) -> list[dict]:
    """Generic extraction from OCR word boxes.

    Returns [{'parameter', 'value', 'bbox': (x, y, w, h)}, …] in the OCR
    image's pixel coordinates.
    """
    pairs: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for line in _group_lines(words):
        pr = _pair_from_words(line)
        if not pr:
            continue
        key = (pr['parameter'].lower(), pr['value'].lower())
        if key in seen:
            continue
        seen.add(key)
        pairs.append(pr)
    return pairs


def extract_fields_from_text(text: str) -> list[dict]:
    """Generic extraction from plain text (embedded-PDF fallback path).

    No coordinates are available here, so each pair's ``bbox`` is ``None``.
    """
    pairs: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for line in text.splitlines():
        sp = _split(line)
        if not sp:
            continue
        label, value = _clean_label(sp[0]), _clean_value(sp[1])
        if not _accept(label, value):
            continue
        key = (label.lower(), value.lower())
        if key in seen:
            continue
        seen.add(key)
        # No per-character confidence in the embedded-text path → unknown.
        pairs.append({'parameter': label, 'value': value,
                      'bbox': None, 'conf': None})
    return pairs
