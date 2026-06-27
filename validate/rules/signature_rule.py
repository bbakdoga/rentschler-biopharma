"""
Rule 2 – Kürzel / signature completeness.
Checks:
  • Every section has both a Bearbeitet and a Geprüft entry
  • No Kürzel field is blank
  • No date field is blank
  • Every Kürzel appears in the personnel table (if personnel list was extracted)
"""
from validate.rules.base_rule import BaseRule
from db.models import Batch, Signature, Personnel


class SignatureRule(BaseRule):
    rule_id   = "SIG-001"
    rule_name = "Signature / Kürzel completeness"

    def validate(self, batch: Batch, session):
        results = []

        personnel = session.query(Personnel).filter(
            Personnel.batch_id == batch.id
        ).all()
        known = {p.kuerzel.lower() for p in personnel if p.kuerzel}

        sigs = session.query(Signature).filter(Signature.batch_id == batch.id).all()

        for sig in sigs:
            loc = f"§{sig.section} p.{sig.page_num}"

            if not (sig.kuerzel or '').strip():
                results.append(self.err(
                    batch.id,
                    f"Missing Kürzel — {sig.role} {loc}",
                    section=sig.section, page_num=sig.page_num
                ))
            elif known and sig.kuerzel.lower() not in known:
                results.append(self.warn(
                    batch.id,
                    f"Unknown Kürzel '{sig.kuerzel}' (not in personnel list) — "
                    f"{sig.role} {loc}",
                    section=sig.section, page_num=sig.page_num
                ))

            if not (sig.date or '').strip():
                results.append(self.err(
                    batch.id,
                    f"Missing date — {sig.role} {loc}",
                    section=sig.section, page_num=sig.page_num
                ))

        # Each section must have both roles
        by_key: dict = {}
        for sig in sigs:
            key = (sig.section, sig.page_num)
            by_key.setdefault(key, set()).add(sig.role)

        for (sec, pg), roles in by_key.items():
            for required in ('Bearbeitet', 'Geprüft'):
                if required not in roles:
                    results.append(self.err(
                        batch.id,
                        f"Missing '{required}' signature in §{sec} p.{pg}",
                        section=sec, page_num=pg
                    ))

        if not sigs:
            results.append(self.warn(
                batch.id,
                "No signatures were extracted from this document — "
                "OCR may have failed on handwritten entries."
            ))

        return results
