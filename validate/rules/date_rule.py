"""
Rule 1 – Date format & chronological order.
Checks:
  • Every date parses as DD.MM.YYYY (not garbage OCR)
  • No date is in the future
  • GQQ generation date ≤ every Bearbeitet date
  • Bearbeitet date ≤ Geprüft date within each section
"""
import re
from datetime import datetime
from validate.rules.base_rule import BaseRule
from db.models import Batch, Signature

DATE_RE = re.compile(r'^(\d{1,2})[./\-](\d{2})[./\-](\d{4})$')


def _parse(date_str: str):
    if not date_str:
        return None
    s = date_str.strip()
    m = DATE_RE.match(s) or re.search(r'(\d{1,2})[./](\d{2})[./](\d{4})', s)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    return None


class DateOrderRule(BaseRule):
    rule_id   = "DATE-001"
    rule_name = "Date format and chronological order"

    def validate(self, batch: Batch, session):
        results = []
        now = datetime.now()

        gqq_dt = _parse(batch.gqq_generated_at)

        sigs = session.query(Signature).filter(Signature.batch_id == batch.id).all()

        # Check format & future dates
        for sig in sigs:
            dt = _parse(sig.date)
            if not dt:
                results.append(self.err(
                    batch.id,
                    f"Unparseable date '{sig.date}' — {sig.role} in §{sig.section} p.{sig.page_num}",
                    section=sig.section, page_num=sig.page_num
                ))
                continue
            if dt > now:
                results.append(self.warn(
                    batch.id,
                    f"Future date '{sig.date}' — {sig.role} in §{sig.section}",
                    section=sig.section, page_num=sig.page_num
                ))
            # GQQ date must be ≤ every signature date
            if gqq_dt and dt < gqq_dt:
                results.append(self.err(
                    batch.id,
                    f"Signature date {sig.date} is BEFORE GQQ generation date "
                    f"{batch.gqq_generated_at} — {sig.role} §{sig.section}",
                    section=sig.section, page_num=sig.page_num
                ))

        # Bearbeitet ≤ Geprüft within each (section, page)
        by_key: dict = {}
        for sig in sigs:
            key = (sig.section, sig.page_num)
            by_key.setdefault(key, {})[sig.role] = sig

        for (sec, pg), roles in by_key.items():
            b = roles.get('Bearbeitet')
            g = roles.get('Geprüft')
            if b and g:
                b_dt = _parse(b.date)
                g_dt = _parse(g.date)
                if b_dt and g_dt and b_dt > g_dt:
                    results.append(self.err(
                        batch.id,
                        f"Bearbeitet ({b.date}) > Geprüft ({g.date}) in §{sec} p.{pg}",
                        section=sec, page_num=pg
                    ))

        return results
