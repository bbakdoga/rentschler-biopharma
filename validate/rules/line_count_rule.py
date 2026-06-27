"""
Rule 6 – Digit count matches expected slots.
Intermediat IDs in this document have a base number followed by suffix
underscored slots, e.g. "B20-PP 3019 _ _ _" → 3 digits expected.
We store the number of expected digits as field metadata (expected_digits).
"""
import re
from validate.rules.base_rule import BaseRule
from db.models import Batch, Field

DIGIT_RE = re.compile(r'\d')


class LineCountRule(BaseRule):
    rule_id   = "LC-001"
    rule_name = "Digit / slot count consistency"

    def validate(self, batch: Batch, session):
        results = []

        # Intermediat fields carry expected_digits in their unit column
        intermediat_fields = (
            session.query(Field)
            .filter(Field.batch_id == batch.id,
                    Field.field_name.like('intermediat_%'))
            .all()
        )

        for f in intermediat_fields:
            try:
                expected = int(f.unit or 0)
            except ValueError:
                continue
            if expected == 0:
                continue

            val = f.parsed_value or ''
            actual = len(DIGIT_RE.findall(val))
            if actual != expected:
                results.append(self.err(
                    batch.id,
                    f"Expected {expected} digit(s) in '{f.field_name}', "
                    f"found {actual} in value '{val}' — §{f.section}",
                    section=f.section, field_name=f.field_name
                ))

        # Also check that the batch_no itself has the right digit count
        # based on how many underscored slots appear on the cover
        bn = re.sub(r'\s+', '', batch.batch_no or '')
        expected_bn_field = (
            session.query(Field)
            .filter(Field.batch_id == batch.id,
                    Field.field_name == 'batch_no_expected_digits')
            .first()
        )
        if expected_bn_field and expected_bn_field.parsed_value:
            try:
                exp_digits = int(expected_bn_field.parsed_value)
                actual_digits = len(DIGIT_RE.findall(bn))
                if actual_digits != exp_digits:
                    results.append(self.err(
                        batch.id,
                        f"Batch No. has {actual_digits} digits but "
                        f"{exp_digits} slots were printed on the cover page"
                    ))
            except ValueError:
                pass

        return results
