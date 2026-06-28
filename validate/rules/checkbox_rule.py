"""
Rule 3 – Checkbox completeness.
A checkbox field carries state 'checked' / 'unchecked' / 'unknown'. Only an
EXPLICIT empty box ('unchecked', i.e. a ☐/□ glyph) is flagged as a missing
selection. An ambiguous OCR mark ('unknown' — a bare 'O'/circle that can't be
told apart from a bullet or the letter O) is NOT flagged: a handwritten check
can't be reliably recovered from transcribed text, and flagging those produced
dozens of false positives.
"""
from validate.rules.base_rule import BaseRule
from db.models import Batch, Field

# Glyphs that mark a box as genuinely empty (vs. an ambiguous OCR 'O').
_EMPTY_GLYPHS = ('☐', '□', '▢', '◻')


class CheckboxRule(BaseRule):
    rule_id   = "CHK-001"
    rule_name = "Checkbox selection completeness"

    def validate(self, batch: Batch, session):
        results = []

        checkbox_fields = (
            session.query(Field)
            .filter(Field.batch_id == batch.id,
                    Field.field_name == 'checkbox')
            .all()
        )

        for f in checkbox_fields:
            val = (f.parsed_value or '').lower()
            ctx = f.raw_value or ''
            # Flag the new explicit 'unchecked' state. For batches extracted
            # before the 3-state change (everything stored as 'none'), fall back
            # to only flagging when the context shows an explicit empty-box glyph
            # — so --revalidate already drops the false positives.
            flag = (val == 'unchecked'
                    or (val in ('none', '') and any(g in ctx for g in _EMPTY_GLYPHS)))
            if flag:
                results.append(self.err(
                    batch.id,
                    f"Unchecked checkbox — context: '{ctx}' in §{f.section}",
                    section=f.section,
                    field_name='checkbox'
                ))

        return results
