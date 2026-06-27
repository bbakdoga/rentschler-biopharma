"""
Rule 5 – Production Code & Batch No. consistency.
The values on the cover page must match every later reference.
Also checks that 'Zuletzt verwendet für Production Code' on the ProzessOfen
page (§5.8) matches the cover-page production code.
"""
import re
from validate.rules.base_rule import BaseRule
from db.models import Batch, Field


def _normalize(s: str) -> str:
    return re.sub(r'\s+', '', s or '').strip()


class CodeConsistencyRule(BaseRule):
    rule_id   = "CODE-001"
    rule_name = "Production Code / Batch No. consistency"

    def validate(self, batch: Batch, session):
        results = []

        cover_pc  = _normalize(batch.production_code or '')
        cover_bn  = _normalize(batch.batch_no or '')

        if not cover_pc:
            results.append(self.warn(
                batch.id,
                "Production Code missing from cover page (OCR may have failed)"
            ))
        if not cover_bn:
            results.append(self.warn(
                batch.id,
                "Batch No. missing from cover page (OCR may have failed)"
            ))

        if not cover_pc and not cover_bn:
            return results

        # Fields that reference production code / batch
        ref_fields = (
            session.query(Field)
            .filter(Field.batch_id == batch.id,
                    Field.field_name.in_([
                        'production_code_ref',
                        'charge',
                        'zuletzt_used_pc',
                        'batch_ref',
                    ]))
            .all()
        )

        for f in ref_fields:
            val = _normalize(f.parsed_value or '')
            if not val:
                continue

            if 'pc' in f.field_name or 'production' in f.field_name:
                if cover_pc and val != cover_pc:
                    results.append(self.err(
                        batch.id,
                        f"Production Code mismatch: cover='{cover_pc}' but "
                        f"found='{val}' in §{f.section}",
                        section=f.section, field_name=f.field_name
                    ))
            else:
                if cover_bn and val != cover_bn:
                    results.append(self.err(
                        batch.id,
                        f"Batch No. mismatch: cover='{cover_bn}' but "
                        f"found='{val}' in §{f.section}",
                        section=f.section, field_name=f.field_name
                    ))

        return results
