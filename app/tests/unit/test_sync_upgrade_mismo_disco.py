"""La confirmación de una mejora exige que sea EL MISMO disco (SPEC 2026-10-02, punto 4).

QA en vivo 2026-10-02 00:01: Daniel mejoró un Rosa espinosa slot 1 libre (#408) y fue al
equipamiento de Claret, que lleva OTRO Rosa espinosa slot 1 (#396). Ese disco confirmó la mejora y a
#408 se le escribieron los stats de #396. Set + slot no alcanzan.
"""
from __future__ import annotations

from app.core.parser_disc import DiscParsed, SubstatParsed
from app.core.sync_upgrade import UpgradeSyncer, _Snap


def _sub(canon, valor, rolls):
    return SubstatParsed(canon, canon, valor, "%" if canon.endswith("%") else "flat", rolls, 1.0)


def _disc(nivel, subs):
    return DiscParsed(set_name_raw="Rosa espinosa", set_name_canon=None, slot=1,
                      main_stat_raw="PV", main_stat_canon="HP", main_valor=550.0,
                      main_unidad="flat", nivel=nivel, rareza="S", subs=subs)


class _SyncerEspia:
    def __init__(self):
        self.llamadas = []

    def actualizar_por_mejora(self, pre, post):
        self.llamadas.append((pre, post))
        return 1


PRE_408 = [_sub("Daño Crítico", 4.8, 0), _sub("Maestría de Anomalía", 9, 0), _sub("DEF", 15, 0)]
EQUIPADO_396 = [_sub("DEF%", 9.6, 1), _sub("ATK", 19, 0), _sub("DEF", 45, 2),
                _sub("Prob. Crítica", 4.8, 1)]
POST_408 = [_sub("Daño Crítico", 9.6, 1), _sub("Maestría de Anomalía", 9, 0), _sub("DEF", 30, 1),
            _sub("Perforación", 27, 2)]


def _syncer():
    espia, diags = _SyncerEspia(), []
    s = UpgradeSyncer(ocr=None, on_diagnostic=diags.append, disc_syncer=espia)
    pre = _disc(0, PRE_408)
    s._pending = (_Snap(0, pre), _Snap(7, pre), 15, 0.0)
    return s, espia, diags, pre


def test_otro_disco_del_mismo_set_y_slot_no_confirma():
    s, espia, diags, _pre = _syncer()
    s.on_post_upgrade_disc(_disc(15, EQUIPADO_396), now=1.0)
    assert espia.llamadas == [], "el disco del PJ no puede confirmar la mejora de otro"
    assert not any("resumen" in d for d in diags)
    assert s._pending is not None, "el pendiente sigue esperando a su disco"


def test_despues_confirma_con_el_disco_bueno():
    s, espia, diags, pre = _syncer()
    s.on_post_upgrade_disc(_disc(15, EQUIPADO_396), now=1.0)
    bueno = _disc(15, POST_408)
    s.on_post_upgrade_disc(bueno, now=2.0)
    assert espia.llamadas == [(pre, bueno)]
    assert any("resumen" in d for d in diags)
