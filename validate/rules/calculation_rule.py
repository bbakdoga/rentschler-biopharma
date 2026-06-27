"""
Rule 7 – Mathematical calculation verification.
Re-derives every formula visible in the document and compares to the
recorded result within CALC_TOLERANCE.

Formulas verified:
  m_Netto  = m_Brutto − m_Tara                      (each intermediat section)
  V_Netto  = m_Netto [kg] / ρ [kg/L]  → [L]        (each intermediat section)
  m_B20-ST = m_B10-PP_Z1 + m_B10-PP_Z2              (§5.9)
  Beladung = m_B20-ST [g] / V_Ofen [L]              (§5.9 / §5.12.4)
  LoadVol  = (FlussVorOfen × DauerAuftrag)
             − (FlussA × DauerAuftrag)               (§5.12.3)
  C_Cake   = m_B20-ST [g] / V_Netto_nPZ [L]         (§5.12.4)
  Actual_Beladung = LoadVol × C_Cake / V_Ofen        (§5.12.4)
"""
from collections import defaultdict

from validate.rules.base_rule import BaseRule
from db.models import Batch, Field, Page
from config import CALC_TOLERANCE


def _get(session, batch_id, name, section=None):
    q = session.query(Field).filter(
        Field.batch_id == batch_id,
        Field.field_name == name,
    )
    if section:
        q = q.filter(Field.section == section)
    f = q.first()
    if f and f.parsed_value:
        try:
            return float(f.parsed_value.replace(',', '.'))
        except ValueError:
            pass
    return None


def _page_operands(session, batch_id, names):
    """Group the given fields by the page they were read from:

        page_id → {field_name: (section, page_num, value)}

    A calculation's operands then come from the SAME page, so each
    intermediate's mass balance — typically repeated under the same section on
    separate pages — is checked against its own brutto/tara/density instead of
    the first one found anywhere in the section."""
    pages: dict = defaultdict(dict)
    rows = (
        session.query(Field, Page)
        .join(Page, Field.page_id == Page.id)
        .filter(Field.batch_id == batch_id, Field.field_name.in_(names))
        .all()
    )
    for f, p in rows:
        if not f.parsed_value:
            continue
        try:
            val = float(f.parsed_value.replace(',', '.'))
        except ValueError:
            continue
        pages[p.id][f.field_name] = (f.section, p.page_num, val)
    return pages


class CalculationRule(BaseRule):
    rule_id   = "CALC-001"
    rule_name = "Mathematical calculation verification"
    T = CALC_TOLERANCE

    def validate(self, batch: Batch, session):
        results = []
        bid = batch.id

        # ── m_Netto = m_Brutto − m_Tara, V_Netto = m_Netto / ρ ─────────────
        #   Operands are paired within the page they were read from, so each
        #   intermediate's mass balance is checked against its own brutto/tara/
        #   density — not the first one found in the section (which produced
        #   false errors when a section held several intermediates).
        operand_pages = _page_operands(
            session, bid,
            ('m_tara', 'm_brutto', 'm_netto', 'density', 'v_netto'))
        for fld in operand_pages.values():
            if not ('m_tara' in fld and 'm_brutto' in fld and 'm_netto' in fld):
                continue
            sec, pnum, m_tara = fld['m_tara']
            m_brutto = fld['m_brutto'][2]
            m_netto  = fld['m_netto'][2]
            expected = m_brutto - m_tara
            if abs(expected - m_netto) > self.T:
                results.append(self.err(
                    bid,
                    f"§{sec}: m_Netto should be "
                    f"{expected:.2f} (={m_brutto}−{m_tara}) "
                    f"but recorded {m_netto}",
                    section=sec, page_num=pnum, field_name='m_netto'
                ))

            # ── V_Netto = m_Netto / ρ ──────────────────────────────────────
            if 'density' in fld and 'v_netto' in fld:
                density = fld['density'][2]
                v_netto = fld['v_netto'][2]
                if density > 0:
                    expected_v = m_netto / density
                    if abs(expected_v - v_netto) > self.T:
                        results.append(self.err(
                            bid,
                            f"§{sec}: V_Netto should be "
                            f"{expected_v:.2f} L (={m_netto}/{density}) "
                            f"but recorded {v_netto}",
                            section=sec, page_num=pnum, field_name='v_netto'
                        ))

        # ── m_B20-ST = Z1 + Z2 (§5.9) ──────────────────────────────────────
        m_z1   = _get(session, bid, 'm_b10pp_z1')
        m_z2   = _get(session, bid, 'm_b10pp_z2')
        m_b20  = _get(session, bid, 'm_b20st')
        if m_z1 is not None and m_b20 is not None:
            expected_b20 = m_z1 + (m_z2 or 0.0)
            if abs(expected_b20 - m_b20) > self.T:
                results.append(self.err(
                    bid,
                    f"§5.9: m_B20-ST should be {expected_b20:.2f} g "
                    f"(Z1={m_z1} + Z2={m_z2 or 0}) but recorded {m_b20}",
                    section='5.9', field_name='m_b20st'
                ))

        # ── Beladung = m_B20-ST [g] / V_Ofen [L] (§5.9) ───────────────────
        v_ofen   = _get(session, bid, 'v_ofen_bak_b20')
        beladung = _get(session, bid, 'beladung')
        if m_b20 and v_ofen and v_ofen > 0 and beladung is not None:
            expected_bel = m_b20 / v_ofen
            if abs(expected_bel - beladung) > self.T:
                results.append(self.err(
                    bid,
                    f"§5.9: Beladung should be {expected_bel:.2f} g/L "
                    f"(={m_b20}/{v_ofen}) but recorded {beladung}",
                    section='5.9', field_name='beladung'
                ))

        # ── Load Volume (§5.12.3) ───────────────────────────────────────────
        fluss_vor   = _get(session, bid, 'mittlerer_fluss_vor_ofen')
        fluss_pumpe = _get(session, bid, 'mittlerer_fluss_pumpe_a')
        dauer_h     = _get(session, bid, 'dauer_auftrag_stunden')
        load_vol    = _get(session, bid, 'load_vol')
        if all(v is not None for v in [fluss_vor, fluss_pumpe, dauer_h, load_vol]):
            expected_lv = (fluss_vor - fluss_pumpe) * dauer_h
            if abs(expected_lv - load_vol) > self.T:
                results.append(self.err(
                    bid,
                    f"§5.12.3: Load Volume should be {expected_lv:.2f} L "
                    f"(=({fluss_vor}−{fluss_pumpe})×{dauer_h}) "
                    f"but recorded {load_vol}",
                    section='5.12.3', field_name='load_vol'
                ))

        # ── Actual Beladung §5.12.4: C_Cake = m_B20-ST / V_Netto_nPZ ──────
        v_netto_npz  = _get(session, bid, 'v_netto_npz')
        c_cake       = _get(session, bid, 'c_b20st_cake')
        act_beladung = _get(session, bid, 'actual_beladung')
        if m_b20 and v_netto_npz and v_netto_npz > 0:
            expected_cc = m_b20 / v_netto_npz
            if c_cake is not None and abs(expected_cc - c_cake) > self.T:
                results.append(self.err(
                    bid,
                    f"§5.12.4: C_Cake should be {expected_cc:.2f} g/L "
                    f"but recorded {c_cake}",
                    section='5.12.4', field_name='c_b20st_cake'
                ))
            if load_vol and v_ofen and v_ofen > 0 and act_beladung is not None:
                expected_ab = load_vol * expected_cc / v_ofen
                if abs(expected_ab - act_beladung) > self.T:
                    results.append(self.err(
                        bid,
                        f"§5.12.4: Actual Beladung should be {expected_ab:.2f} g/L "
                        f"but recorded {act_beladung}",
                        section='5.12.4', field_name='actual_beladung'
                    ))

        return results
