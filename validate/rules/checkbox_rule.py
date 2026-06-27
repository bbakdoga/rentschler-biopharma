"""
Rule 3 – Checkbox completeness.
For every O Ja / O Nein pair detected on a page, exactly one must be selected.
We store checkboxes as fields with field_name='checkbox' and parsed_value='ja_checked' / 'nein_checked' / 'none'.
"""
from validate.rules.base_rule import BaseRule
from db.models import Batch, Field


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
            if val == 'none' or not val:
                results.append(self.err(
                    batch.id,
                    f"Unchecked checkbox — context: '{f.raw_value}' "
                    f"in §{f.section}",
                    section=f.section,
                    field_name='checkbox'
                ))

        return results
