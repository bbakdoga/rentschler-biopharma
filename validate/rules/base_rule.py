from abc import ABC, abstractmethod
from datetime import datetime
from db.models import ValidationResult, Batch


class BaseRule(ABC):
    rule_id   = "BASE"
    rule_name = "Base Rule"

    @abstractmethod
    def validate(self, batch: Batch, session) -> list[ValidationResult]:
        ...

    def err(self, batch_id, msg, section=None, page_num=None, field_name=None):
        return self._make(batch_id, "error", msg, section, page_num, field_name)

    def warn(self, batch_id, msg, section=None, page_num=None, field_name=None):
        return self._make(batch_id, "warning", msg, section, page_num, field_name)

    def info(self, batch_id, msg, section=None, page_num=None, field_name=None):
        return self._make(batch_id, "info", msg, section, page_num, field_name)

    def _make(self, batch_id, severity, msg, section, page_num, field_name):
        return ValidationResult(
            batch_id=batch_id,
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            severity=severity,
            message=msg,
            section=section,
            page_num=page_num,
            field_name=field_name,
            flagged_at=datetime.utcnow(),
        )
