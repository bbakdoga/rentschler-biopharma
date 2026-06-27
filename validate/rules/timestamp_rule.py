"""
Rule 8 – Timestamp chronological ordering.
Chains that must be strictly ascending:
  §5.6.2  Start Überführung → Ende Überführung → Start Homogenisieren → Ende Homogenisieren
  §5.7.6  Start Prozessverzögerung → Ende Prozessverzögerung
  §5.7.3  Probenzug must be ≥ Start Haltezeit and ≤ Erlaubte Haltezeit
  §5.12.1 Start Auftrag → Ende Auftrag
  §5.12.3 Start Auftrag → Ende Auftrag
  §5.4.1  Transfer from Kühlraum → Start Temperierung → Ende (B10-PP Z1)
  §5.12.6 Start Temperierung → Ende Temperierung (both cycles)
"""
import re
from datetime import datetime
from validate.rules.base_rule import BaseRule
from db.models import Batch, Field

DT_RE = re.compile(r'(\d{1,2})[./](\d{2})[./](\d{4})\s*/?\s*(\d{1,2}):(\d{2})')


def _parse_dt(val: str):
    if not val:
        return None
    m = DT_RE.search(val)
    if m:
        try:
            d, mo, y, h, mi = (int(x) for x in m.groups())
            return datetime(y, mo, d, h, mi)
        except ValueError:
            pass
    return None


def _get_dt(session, batch_id, field_name, section=None):
    q = session.query(Field).filter(
        Field.batch_id == batch_id,
        Field.field_name == field_name,
    )
    if section:
        q = q.filter(Field.section == section)
    f = q.first()
    return _parse_dt(f.parsed_value if f else None), f


CHAINS = [
    # (section, [(label, field_name), ...])
    ('5.6.2', [
        ('Start Überführung',    'start_ueberfuehrung'),
        ('Ende Überführung',     'ende_ueberfuehrung'),
        ('Start Homogenisieren', 'start_homogenisieren'),
        ('Ende Homogenisieren',  'ende_homogenisieren'),
    ]),
    ('5.7.6', [
        ('Start Prozessverzögerung', 'start_prozessverzoegerung'),
        ('Ende Prozessverzögerung',  'ende_prozessverzoegerung'),
    ]),
    ('5.12.3', [
        ('Start Auftrag', 'start_auftrag'),
        ('Ende Auftrag',  'ende_auftrag'),
    ]),
    ('5.12.1', [
        ('Start Auftrag', 'start_auftrag'),
        ('Ende Elution',  'ende_elution'),
    ]),
]


class TimestampRule(BaseRule):
    rule_id   = "TS-001"
    rule_name = "Timestamp chronological ordering"

    def validate(self, batch: Batch, session):
        results = []
        bid = batch.id

        # ── ordered chains ──────────────────────────────────────────────────
        for section, steps in CHAINS:
            times = []
            for label, fname in steps:
                dt, _ = _get_dt(session, bid, fname, section)
                if dt:
                    times.append((label, dt))

            for i in range(1, len(times)):
                prev_lbl, prev_dt = times[i - 1]
                curr_lbl, curr_dt = times[i]
                if curr_dt < prev_dt:
                    results.append(self.err(
                        bid,
                        f"§{section}: '{curr_lbl}' ({curr_dt:%d.%m.%Y %H:%M}) "
                        f"is BEFORE '{prev_lbl}' ({prev_dt:%d.%m.%Y %H:%M})",
                        section=section
                    ))

        # ── Probenzug within Haltezeit window ───────────────────────────────
        for section in ('5.3.1', '5.7.2', '5.3.2'):
            start_dt, _ = _get_dt(session, bid, 'start_haltezeit', section)
            end_dt,   _ = _get_dt(session, bid, 'erlaubte_haltezeit', section)
            probe_dt, _ = _get_dt(session, bid, 'probenzug', section)

            if start_dt and probe_dt and probe_dt < start_dt:
                results.append(self.err(
                    bid,
                    f"§{section}: Probenzug ({probe_dt:%d.%m.%Y %H:%M}) "
                    f"is before Start Haltezeit ({start_dt:%d.%m.%Y %H:%M})",
                    section=section
                ))
            if end_dt and probe_dt and probe_dt > end_dt:
                results.append(self.err(
                    bid,
                    f"§{section}: Probenzug ({probe_dt:%d.%m.%Y %H:%M}) "
                    f"is after Erlaubte Haltezeit ({end_dt:%d.%m.%Y %H:%M})",
                    section=section
                ))

        # ── Temperierung duration check (§5.12.6): Soll 72–75 h ────────────
        for cycle, start_fname, end_fname in [
            ('Z1', 'start_temperierung_z1', 'ende_temperierung_z1'),
            ('Z2', 'start_temperierung_z2', 'ende_temperierung_z2'),
        ]:
            start_dt, _ = _get_dt(session, bid, start_fname, '5.12.6')
            end_dt,   _ = _get_dt(session, bid, end_fname,   '5.12.6')
            if start_dt and end_dt:
                dur_h = (end_dt - start_dt).total_seconds() / 3600
                if not (72 <= dur_h <= 75):
                    sev = 'error' if dur_h < 72 else 'warning'
                    msg = (
                        f"§5.12.6 Temperierung {cycle}: duration is "
                        f"{dur_h:.1f} h (Soll: 72–75 h)"
                    )
                    if sev == 'error':
                        results.append(self.err(bid, msg, section='5.12.6'))
                    else:
                        results.append(self.warn(bid, msg, section='5.12.6'))

        # ── Erlaubte Standzeit ≤ 82 h (§5.12.1) ────────────────────────────
        auftrag_start, _ = _get_dt(session, bid, 'start_auftrag', '5.12.1')
        erlaubte_standzeit, _ = _get_dt(session, bid, 'erlaubte_standzeit', '5.12.1')
        if auftrag_start and erlaubte_standzeit:
            dur_h = (erlaubte_standzeit - auftrag_start).total_seconds() / 3600
            if dur_h > 82:
                results.append(self.err(
                    bid,
                    f"§5.12.1: Erlaubte Standzeit is {dur_h:.1f} h (max 82 h)",
                    section='5.12.1'
                ))

        return results
