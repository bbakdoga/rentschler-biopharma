#!/usr/bin/env python3
"""
Strict, per-field accuracy evaluation against a hand-built gold set.

Unlike score_vs_solution.py (which checks whether a ground-truth value appears
*somewhere* among everything captured — a lenient, recall-only, substring
match), this scores each field **by name and section** with an exact,
normalised comparison, and reports precision and recall. A value put under the
wrong label or wrong section counts as a miss, not a hit.

Workflow
--------
1. Scaffold a gold file from a processed batch (writes what the tool extracted,
   with a blank ``expected`` column for you to fill from the PDF):

       python scripts/eval.py --init <batch_id> > gold.csv

   Open gold.csv, fill the ``expected`` column with the correct value for the
   fields you care about (read them off the PDF), and delete rows you don't
   want to score. Leave ``expected`` blank to skip a row.

2. Score the batch against the gold file:

       python scripts/eval.py <batch_id> gold.csv

Gold CSV columns: section, field, tool_value, expected, note
  * ``section`` — e.g. ``5.3.1`` for a Field row, or ``(batch)`` for a
    batch-level attribute (batch_no, doc_nr, production_code, …).
  * ``field``   — the canonical field name (Field.field_name) or batch attr.
  * ``expected``— the correct value (you fill this in). Blank → row skipped.
  * ``tool_value`` / ``note`` — informational only; ignored when scoring.
"""
from pathlib import Path
import csv
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.session import get_session
from db.models import Field, Batch

# Canonical fields validation depends on, pulled from the source of truth so
# the gold template stays in sync. These are the names worth scoring; the
# generic extractor's many incidental captures are excluded unless --all.
from processor import (
    _MASS_VOLUME_FIELDS, _NAMED_FIELDS, _DATETIME_FIELD_LABELS,
)
from extract.field_extractor import _CALC_PATTERNS

_CANONICAL: set[str] = (
    {f for f, *_ in _MASS_VOLUME_FIELDS}
    | {f for specs in _NAMED_FIELDS.values() for f, *_ in specs}
    | set(_DATETIME_FIELD_LABELS)
    | set(_CALC_PATTERNS)
    | {"batch_no_expected_digits"}
)


# ── value normalisation ───────────────────────────────────────────────────────
_DATE_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_DATE_DE = re.compile(r"\b(\d{1,2})[.](\d{1,2})[.](\d{2,4})\b")
_NUM_RE = re.compile(r"^[-+]?\d+(?:\.\d+)?$")


def _as_date(s) -> str | None:
    s = str(s)
    m = _DATE_ISO.search(s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = _DATE_DE.search(s)
    if m:
        d, mo, y = m.groups()
        if len(y) == 2:
            y = "20" + y
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return None


def _as_num(s) -> float | None:
    t = str(s).strip().replace(",", ".")
    return float(t) if _NUM_RE.match(t) else None


def _norm_str(s) -> str:
    return "".join(str(s).split()).lower()


def values_match(expected, actual) -> bool:
    """Exact match after normalising dates (any format → ISO), numbers (',' vs
    '.', trailing zeros) and whitespace/case. '7' does NOT match '17'."""
    if expected is None or actual is None:
        return False
    d1, d2 = _as_date(expected), _as_date(actual)
    if d1 and d2:
        return d1 == d2
    n1, n2 = _as_num(expected), _as_num(actual)
    if n1 is not None and n2 is not None:
        return abs(n1 - n2) < 1e-6
    return _norm_str(expected) == _norm_str(actual)


# ── batch-level attributes (live on Batch, not the Field table) ───────────────
_BATCH_ATTRS = {
    "batch_no": "batch_no",
    "doc_nr": "doc_nr",
    "revision": "revision",
    "project_code": "project_code",
    "production_code": "production_code",
    "production_code_ds": "production_code_ds",
    "process_step": "process_step",
    "sap_material_nr": "sap_material_nr",
    "man_nr": "man_nr",
}
_BATCH_SECTIONS = {"(batch)", "batch", "cover", ""}


def _tool_values(session, batch_id, section, field) -> list[str]:
    """All values the tool stored for one (section, field) key. More than one
    means the extractor produced duplicates for that key — a red flag for the
    mispairing bug, surfaced by the scorer."""
    if section.strip().lower() in _BATCH_SECTIONS and field in _BATCH_ATTRS:
        b = session.get(Batch, batch_id)
        v = getattr(b, _BATCH_ATTRS[field], None) if b else None
        return [str(v)] if v not in (None, "") else []
    rows = (session.query(Field)
            .filter(Field.batch_id == batch_id,
                    Field.field_name == field,
                    Field.section == section)
            .all())
    vals = []
    for r in rows:
        v = r.parsed_value if r.parsed_value not in (None, "") else r.raw_value
        if v not in (None, ""):
            vals.append(str(v))
    return vals


# ── --init : scaffold a gold CSV from a batch ─────────────────────────────────
def cmd_init(batch_id: int, all_fields: bool = False) -> int:
    session = get_session()
    w = csv.writer(sys.stdout)
    w.writerow(["section", "field", "tool_value", "expected", "note"])

    b = session.get(Batch, batch_id)
    if b is None:
        print(f"Batch {batch_id} not found.", file=sys.stderr)
        return 1
    for field, attr in _BATCH_ATTRS.items():
        v = getattr(b, attr, None)
        if v not in (None, ""):
            w.writerow(["(batch)", field, v, "", "cover/batch attribute"])

    rows = (session.query(Field)
            .filter(Field.batch_id == batch_id)
            .order_by(Field.section, Field.field_name)
            .all())
    # One template row per (section, field). If a key has multiple values, note
    # it so you can see the duplicates while filling the gold set. By default
    # only canonical (validation-relevant) fields are emitted; --all dumps every
    # captured field, including the generic extractor's incidental ones.
    grouped: dict[tuple[str, str], list[str]] = {}
    for r in rows:
        if not all_fields and (r.field_name or "") not in _CANONICAL:
            continue
        v = r.parsed_value if r.parsed_value not in (None, "") else r.raw_value
        grouped.setdefault((r.section or "?", r.field_name or "?"), []).append(
            str(v) if v not in (None, "") else "")
    for (section, field), vals in grouped.items():
        note = "" if len(vals) == 1 else f"{len(vals)} values extracted (dup)"
        w.writerow([section, field, " | ".join(vals[:5]), "", note])
    session.close()
    return 0


# ── scoring ───────────────────────────────────────────────────────────────────
def cmd_score(batch_id: int, gold_path: str) -> int:
    p = Path(gold_path)
    if not p.exists():
        print(f"Gold file not found: {gold_path}", file=sys.stderr)
        return 1

    with p.open(newline="") as fh:
        gold = [row for row in csv.DictReader(fh)
                if (row.get("expected") or "").strip()]
    if not gold:
        print("No rows with a filled-in 'expected' value. Fill the gold file "
              "first (see --init).", file=sys.stderr)
        return 1

    session = get_session()
    correct = wrong = missing = dup = 0
    fails: list[str] = []
    for row in gold:
        section = (row.get("section") or "").strip()
        field = (row.get("field") or "").strip()
        expected = row["expected"].strip()
        vals = _tool_values(session, batch_id, section, field)

        if not vals:
            missing += 1
            fails.append(f"  MISSING  §{section:<7} {field:<26} "
                         f"expected={expected}")
            continue
        if len(vals) > 1:
            dup += 1
        hit = any(values_match(expected, v) for v in vals)
        if hit:
            correct += 1
        else:
            wrong += 1
            shown = vals[0] if len(vals) == 1 else " | ".join(vals[:3])
            fails.append(f"  WRONG    §{section:<7} {field:<26} "
                         f"expected={expected:<14} got={shown}")
    session.close()

    n = len(gold)
    produced = correct + wrong            # gold fields the tool produced a value for
    recall = correct / n * 100 if n else 0
    precision = correct / produced * 100 if produced else 0
    print(f"Batch {batch_id} vs {gold_path}  ({n} scored fields)")
    print(f"  correct : {correct}/{n}")
    print(f"  wrong   : {wrong}")
    print(f"  missing : {missing}")
    print(f"  recall    (correct / all gold)      = {recall:.0f}%")
    print(f"  precision (correct / tool produced) = {precision:.0f}%")
    if dup:
        print(f"  ⚠ {dup} field(s) had multiple extracted values "
              f"(possible mispairing)")
    if fails:
        print("\n  failures:")
        for line in fails:
            print(line)
    return 0


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    if args[0] == "--init":
        rest = args[1:]
        all_fields = "--all" in rest
        rest = [a for a in rest if a != "--all"]
        if len(rest) == 1:
            return cmd_init(int(rest[0]), all_fields=all_fields)
    if len(args) == 2:
        return cmd_score(int(args[0]), args[1])
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
