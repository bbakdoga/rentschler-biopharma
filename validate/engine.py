from datetime import datetime
from db.models import Batch, ValidationResult
from validate.rules.date_rule import DateOrderRule
from validate.rules.signature_rule import SignatureRule
from validate.rules.checkbox_rule import CheckboxRule
from validate.rules.range_rule import RangeRule
from validate.rules.code_consistency_rule import CodeConsistencyRule
from validate.rules.line_count_rule import LineCountRule
from validate.rules.calculation_rule import CalculationRule
from validate.rules.timestamp_rule import TimestampRule


class ValidationEngine:
    def __init__(self):
        self._rules = [
            DateOrderRule(),
            SignatureRule(),
            CheckboxRule(),
            RangeRule(),
            CodeConsistencyRule(),
            LineCountRule(),
            CalculationRule(),
            TimestampRule(),
        ]

    def run(self, batch: Batch, session) -> list[ValidationResult]:
        all_results: list[ValidationResult] = []

        for rule in self._rules:
            try:
                found = rule.validate(batch, session)
                all_results.extend(found)
            except Exception as exc:
                all_results.append(ValidationResult(
                    batch_id=batch.id,
                    rule_id="SYS-ERR",
                    rule_name=f"Rule execution error ({rule.__class__.__name__})",
                    severity="error",
                    message=str(exc),
                    flagged_at=datetime.utcnow(),
                ))

        for r in all_results:
            r.batch_id = batch.id
            session.add(r)

        batch.status = "validated"
        batch.processed_at = datetime.utcnow()
        session.commit()

        return all_results
