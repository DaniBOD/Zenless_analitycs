"""Disco LIBRE equipado a un PJ (S17) → evento `equipado` para el toast "AHORA EN".

Hermano de `test_monitor_sustitucion`. Ahí el origen es otro PJ y el diálogo S23 arma el
pendiente; acá el origen es LIBRE y lo arma la observación pura: badge ausente + botón que solo
sale en discos libres.

Las DOS señales son obligatorias porque cada una tapa el agujero de la otra. LIBRE es la lectura
más frágil del sistema de badges (falso LIBRE de Jane, 2026-07-19 → "presencia gana a LIBRE") y un
falso LIBRE dispararía un toast fantasma; el botón, en cambio, es texto de posición fija — pero no
dice QUIÉN es el dueño. Para un falso positivo tendrían que fallar las dos a la vez y de forma
coherente.

El botón se stubbea (`_s17_action_btn`); su lectura real vive en `test_parser_boton_s17`.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.core.detector import ScreenState
from app.core.parser_disc import DiscParsed, SubstatParsed
from app.core.stats_vocab import _norm_key

_ST17 = ScreenState("S17", 1.0, "s17")


class _FakeSet:
    def __init__(self, id, nombre):
        self.id, self.nombre = id, nombre


class _SetRepo:
    _SETS = {"Balada de la rama y la espada": 1, "Jazz caótico": 2}

    def resolve_id(self, raw):
        r = (raw or "").lower()
        for n, i in self._SETS.items():
            if n.lower() in r or r in n.lower():
                return i
        return None

    def get_all(self):
        return [_FakeSet(i, n) for n, i in self._SETS.items()]


class _Identifier:
    def __init__(self, names):
        self._roster_norm = {_norm_key(n): n for n in names}

    def _load_roster(self):
        pass


def _disc(set_canon="Balada de la rama y la espada", slot=2, owner=None, visual=None,
          libre=False, detectado=None, subs=("CR", "CD")):
    """DiscParsed de un disco S17.

    `libre`     = el badge junto al pill NO localizó avatar (`equip_libre`).
    `owner`     = dueño CERTERO (ancla/latch); `visual` = dueño OBSERVADO por badge.
    `subs`      = nombres de substats: entran en la identidad, así que distinguen discos
                  del mismo set y slot (ver el test de discos gemelos)."""
    return DiscParsed(
        set_name_raw=set_canon, set_name_canon=set_canon, slot=slot,
        main_stat_raw="ATK", main_stat_canon="ATK", main_valor=79, main_unidad="flat",
        nivel=0, rareza="S", agente_asignado_nombre=owner, equip_pj_visual=visual,
        equip_libre=libre,
        equip_detectado=(not libre) if detectado is None else detectado,
        subs=[SubstatParsed(nombre_raw=s, nombre_canon=s, valor=1.0, unidad="flat",
                            rolls=0, confianza=1.0) for s in subs],
    )


def _monitor(roster=("Yixuan", "Nangong Yu")):
    import app.core.monitor as mon_mod
    diags: list[str] = []
    eventos: list[dict] = []
    m = mon_mod.Monitor(
        ocr=object(), detector=None, on_diagnostic=diags.append,
        on_replacement=eventos.append,
        set_repo=_SetRepo(), agent_identifier=_Identifier(roster),
    )
    m._diags = diags
    m._eventos = eventos
    return m


def _armado(m, disc, latch="Nangong Yu", boton="equipar"):
    """Simula el ciclo que ARMA el pendiente: latch puesto, botón leído, disco libre."""
    m._last_agent_name = latch
    m._s17_action_btn = boton
    m._arm_libre_pending(disc)
    return m


def _checks(m):
    return [d for d in m._diags if d.startswith("[equipado] check")]


# ---- armado ------------------------------------------------------------------

def test_ver_un_disco_libre_arma_el_pendiente():
    m = _armado(_monitor(), _disc(libre=True))
    ps = m._pending_swap
    assert ps is not None
    assert ps["origin_kind"] == "libre"
    assert ps["dest_name"] == "Nangong Yu"
    assert ps["slot"] == 2 and ps["set_id"] == 1


def test_sin_boton_de_disco_libre_no_arma():
    """El botón 'Desequipar' significa que el disco YA lo lleva el PJ → no hay nada pendiente."""
    m = _armado(_monitor(), _disc(libre=True), boton="desequipar")
    assert m._pending_swap is None


def test_un_disco_con_dueno_no_arma():
    m = _armado(_monitor(), _disc(libre=False, owner="Yixuan"))
    assert m._pending_swap is None


def test_sin_latch_no_arma():
    """Sin saber a qué PJ se lo equiparía, no hay nada que afirmar después (RNF-02)."""
    m = _armado(_monitor(), _disc(libre=True), latch=None)
    assert m._pending_swap is None


def test_rearmar_el_mismo_disco_no_duplica_el_log():
    m = _monitor()
    d = _disc(libre=True)
    _armado(m, d)
    seq = m._pending_swap["seq"]
    _armado(m, d)
    assert m._pending_swap["seq"] == seq
    assert len([x for x in m._diags if x.startswith("[equipado]")]) == 1


# ---- check -------------------------------------------------------------------

def test_las_dos_senales_disparan_el_toast():
    m = _armado(_monitor(), _disc(libre=True))
    m._s17_action_btn = "desequipar"
    m._check_swap_owner(_disc(owner="Nangong Yu"), _ST17)
    assert m._eventos == [{
        "kind": "equipado", "set_name": "Balada de la rama y la espada", "slot": 2,
        "from_name": None, "to_name": "Nangong Yu",
    }]
    assert m._pending_swap is None                 # consumido


def test_el_dueno_observado_por_badge_tambien_vale():
    """Igual que en el reemplazo: si el ancla no resolvió pero el badge sí, el badge manda."""
    m = _armado(_monitor(), _disc(libre=True))
    m._s17_action_btn = "desequipar"
    m._check_swap_owner(_disc(owner=None, visual="Nangong Yu"), _ST17)
    assert len(m._eventos) == 1 and m._eventos[0]["to_name"] == "Nangong Yu"


def test_boton_reemplazar_tambien_arma_y_confirma():
    """'Reemplazar' = disco libre a un slot YA ocupado (habrá desplazado). Decisión del usuario:
    mismo toast que el slot vacío, no se menciona al desplazado."""
    m = _armado(_monitor(), _disc(libre=True), boton="reemplazar")
    m._s17_action_btn = "desequipar"
    m._check_swap_owner(_disc(owner="Nangong Yu"), _ST17)
    assert len(m._eventos) == 1 and m._eventos[0]["kind"] == "equipado"


def test_solo_el_badge_no_alcanza():
    """El badge dice que lo tiene el destino pero el botón sigue en 'Equipar' → contradicción.
    Lo más probable es un falso dueño del badge: abstenerse (RNF-02)."""
    m = _armado(_monitor(), _disc(libre=True))
    m._s17_action_btn = "equipar"
    m._check_swap_owner(_disc(owner="Nangong Yu"), _ST17)
    assert m._eventos == [] and m._pending_swap is not None
    assert any("solo badge" in d for d in _checks(m))


def test_solo_el_boton_no_alcanza():
    """Botón en 'Desequipar' pero el disco sigue sin dueño legible → incierto, no se afirma."""
    m = _armado(_monitor(), _disc(libre=True))
    m._s17_action_btn = "desequipar"
    m._check_swap_owner(_disc(owner=None, visual=None), _ST17)
    assert m._eventos == [] and m._pending_swap is not None
    assert any("incierto" in d for d in _checks(m))


def test_otro_dueno_se_abstiene():
    m = _armado(_monitor(), _disc(libre=True))
    m._s17_action_btn = "desequipar"
    m._check_swap_owner(_disc(owner="Yixuan"), _ST17)
    assert m._eventos == [] and m._pending_swap is not None
    assert any("otro" in d for d in _checks(m))


def test_un_disco_gemelo_por_set_y_slot_no_dispara():
    """FALSO POSITIVO que motivó exigir identidad COMPLETA: mirás un disco libre, NO lo equipás,
    y más tarde ves OTRO disco del mismo set y slot que un PJ ya tiene puesto. Sin los substats
    en la identidad, eso se leería como 'antes LIBRE, ahora Nangong Yu' → toast fantasma."""
    m = _armado(_monitor(), _disc(libre=True, subs=("CR", "CD")))
    m._s17_action_btn = "desequipar"
    m._check_swap_owner(_disc(owner="Nangong Yu", subs=("ATK%", "PEN")), _ST17)
    assert m._eventos == [] and m._pending_swap is not None
    assert _checks(m) == []          # ni siquiera es el disco del pendiente → no loguea


def test_cambiar_de_pj_mata_el_pendiente():
    """Diferencia deliberada con el pendiente de S23 (que vive hasta consumirse): ver un disco
    libre no compromete a nada. Se equipa al PJ que estás mirando, en la misma visita."""
    m = _armado(_monitor(), _disc(libre=True))
    m._last_agent_name = "Yixuan"                  # te fuiste a otro PJ sin equipar
    m._check_swap_owner(_disc(owner="Yixuan"), _ST17)
    assert m._pending_swap is None and m._eventos == []


def test_el_log_del_check_sale_una_sola_vez_por_desenlace():
    m = _armado(_monitor(), _disc(libre=True))
    m._s17_action_btn = "desequipar"
    for _ in range(5):
        m._check_swap_owner(_disc(owner=None), _ST17)
    assert len(_checks(m)) == 1


def test_un_s23_reemplaza_al_pendiente_libre(monkeypatch):
    """Un solo slot de pendiente: la última intención manda."""
    import app.core.parser_sustitucion as psu
    from app.core.parser_sustitucion import SustitucionParsed
    m = _armado(_monitor(), _disc(libre=True))
    monkeypatch.setattr(
        psu, "parse_sustitucion",
        lambda frame, ocr: SustitucionParsed("Yixuan", "Jazz caótico", 3, 1.0),
    )
    m._process_s23_sustitucion(np.zeros((1439, 2559, 3), np.uint8),
                               ScreenState("S23", 1.0, "s23"))
    assert m._pending_swap["origin_kind"] == "pj"


# ---- gate de la relectura del botón (RNF-06) ---------------------------------

def test_el_boton_se_relee_solo_cuando_cambia_el_estado(monkeypatch):
    """Es una llamada EXTRA a OCR: no debe correr por ciclo, solo en transiciones reales."""
    import app.core.parser_disc_s17 as p17
    llamadas = []
    monkeypatch.setattr(p17, "read_s17_action_button",
                        lambda frame, ocr: llamadas.append(1) or "equipar")
    m = _monitor()
    frame = np.zeros((1439, 2559, 3), np.uint8)
    libre = _disc(libre=True)
    for _ in range(4):
        m._refresh_action_button(libre, frame)
    assert len(llamadas) == 1                      # mismo disco, mismo badge → 1 sola lectura
    m._refresh_action_button(_disc(libre=False, owner="Nangong Yu"), frame)
    assert len(llamadas) == 2                      # el badge apareció → releer
