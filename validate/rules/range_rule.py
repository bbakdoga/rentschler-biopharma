"""
Rule 4 – Soll range checks.
Reads fields that carry a soll_min / soll_max pair and confirms
the recorded value falls within [min, max].

Known ranges hard-coded from the BPR template:
  Wippgeschwindigkeit:  20–30 Hübe/min
  Beladung:             7–19 g_Cake/L_Milk
  pH Equi:              8.56–9.30
  LF Equi:              7.32–11.16 mS/cm
  Baker Five:           75–165 mS/cm
  Baker Four:           8.56–23.30
  Oven BAK B20:         1.30–2.86 L
  Baker Five (cm):      2.99–4.30 cm
"""
from validate.rules.base_rule import BaseRule
from db.models import Batch, Field

# (field_name, soll_min, soll_max, unit, section_hint)
RANGE_SPECS = [
    ('wippgeschwindigkeit', 20.0, 30.0,  'Hübe/min', '5.6'),
    ('beladung',             7.0, 19.0,  'g/L',      '5.9'),
    ('ph_equi',              8.56, 9.30, '',          '5.12'),
    ('lf_equi',              7.32, 11.16,'mS/cm',    '5.12'),
    ('baker_five_ms',       75.0, 165.0, 'mS/cm',    '5.12'),
    ('baker_four',           8.56, 23.30,'',          '5.12'),
    ('v_ofen_bak_b20',       1.30, 2.86, 'L',        '5.8'),
    ('baker_five_cm',        2.99, 4.30, 'cm',        '5.8'),
    ('hygienezone',          0.0,  3.0,  'HZ',        '5.2'),
]


class RangeRule(BaseRule):
    rule_id   = "RNG-001"
    rule_name = "Soll range (in-spec) check"

    def validate(self, batch: Batch, session):
        results = []

        for field_name, lo, hi, unit, section_hint in RANGE_SPECS:
            fields = (
                session.query(Field)
                .filter(Field.batch_id == batch.id,
                        Field.field_name == field_name)
                .all()
            )
            for f in fields:
                try:
                    val = float((f.parsed_value or '').replace(',', '.'))
                except (ValueError, AttributeError):
                    continue
                if not (lo <= val <= hi):
                    results.append(self.err(
                        batch.id,
                        f"Out-of-range: {field_name} = {val} {unit} "
                        f"(Soll: {lo}–{hi}) in §{f.section}",
                        section=f.section,
                        field_name=field_name
                    ))

        return results
