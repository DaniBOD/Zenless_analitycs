"""Puente de sustitución de disco entre PJs (S23 → hint en S17) en el monitor.

Rediseño 2026-07-19: ver el diálogo S23 ARMA un swap pendiente {origen, set, slot, destino=latch}.
La confirmación NO es un toast disparado desde acá, sino que cuando el flujo S17 emite ese disco
(set+slot) equipado por el DESTINO, el monitor le ADJUNTA el hint de origen (`swap_origin_hint`)
y lo marca fresco (`swap_fresh`). La persistencia usa el hint para MOVER la fila (sin duplicar) y
el controller dispara el toast.

FRESCURA (2026-07-20): el pending NO expira por reloj. Vive hasta consumirse, hasta que otro S23
lo reemplace, o hasta cerrar la app — porque en QA la emisión S17 tardó ~10 min y el TTL de 120s
mataba el toast de un swap real. Es seguro porque el hint solo se adjunta si el disco aparece
equipado por el DESTINO (si cancelaste, eso nunca pasa).

Se stubbea `parse_sustitucion` (la lectura real está en `test_parser_sustitucion`); acá se testea
el armado del pending y el adjuntado del hint.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.core.detector import ScreenState
from app.core.parser_disc import DiscParsed
from app.core.parser_sustitucion import SustitucionParsed
from app.core.stats_vocab import _norm_key

_ST23 = ScreenState("S23", 1.0, "s23_sustitucion.png")
_ST17 = ScreenState("S17", 1.0, "s17")


def _frame(fill: int = 0):
    return np.full((1439, 2559, 3), fill, dtype=np.uint8)


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
    """Roster mínimo para `_resolve_agent_name` (fuzzy del PJ origen)."""
    def __init__(self, names):
        self._roster_norm = {_norm_key(n): n for n in names}

    def _load_roster(self):
        pass


def _disc(set_canon="Balada de la rama y la espada", slot=2, owner=None, visual=None):
    """DiscParsed de un disco S17 ya resuelto.

    `owner` = dueño CERTERO (`agente_asignado_nombre`, rama del ancla/latch).
    `visual` = dueño OBSERVADO por badge (`equip_pj_visual`), que puede venir SIN el certero."""
    return DiscParsed(
        set_name_raw=set_canon, set_name_canon=set_canon, slot=slot,
        main_stat_raw="ATK", main_stat_canon="ATK", main_valor=79, main_unidad="flat",
        nivel=0, rareza="S", agente_asignado_nombre=owner, equip_pj_visual=visual,
    )


def _monitor(monkeypatch, sust, roster=("Yixuan", "Nangong Yu")):
    import app.core.monitor as mon_mod
    import app.core.parser_sustitucion as psu
    diags: list[str] = []
    reemplazos: list[dict] = []
    m = mon_mod.Monitor(
        ocr=object(), detector=None, on_diagnostic=diags.append,
        on_replacement=reemplazos.append,
        set_repo=_SetRepo(), agent_identifier=_Identifier(roster),
    )
    m._diags = diags
    m._toasts = reemplazos      # eventos de reemplazo OBSERVADO → toast
    monkeypatch.setattr(psu, "parse_sustitucion", lambda frame, ocr: sust)
    return m


def _reemplazos(m):
    return [d for d in m._diags if d.startswith("[reemplazo]")]


# ---- armado del pending -----------------------------------------------------

def test_s23_arma_el_pending_y_loguea_tentativo(monkeypatch):
    m = _monitor(monkeypatch, SustitucionParsed("7ixuan", "Balada de la rama y la espada", 2, 1.0))
    m._last_agent_name = "Nangong Yu"     # destino (latch)
    m._process_s23_sustitucion(_frame(), _ST23)

    assert m._pending_swap is not None
    ps = m._pending_swap
    assert ps["origin_name"] == "Yixuan"          # '7ixuan' → fuzzy → Yixuan
    assert ps["set_id"] == 1 and ps["slot"] == 2 and ps["dest_name"] == "Nangong Yu"
    linea = _reemplazos(m)
    assert linea and "pendiente" in linea[-1]
    assert "Yixuan" in linea[-1] and "Nangong Yu" in linea[-1]


def test_s23_dedup_mientras_el_dialogo_sigue_en_pantalla(monkeypatch):
    m = _monitor(monkeypatch, SustitucionParsed("Yixuan", "Jazz caótico", 2, 1.0))
    m._last_agent_name = "Nangong Yu"
    for _ in range(3):
        m._process_s23_sustitucion(_frame(), _ST23)
    assert len(_reemplazos(m)) == 1


def test_dispatch_s23_no_resetea_el_latch(monkeypatch):
    """Regresión: S23 (conf alta) caería en el `else` de `_dispatch_state` y resetearía el latch
    del destino. La rama explícita de S23 debe preservarlo."""
    m = _monitor(monkeypatch, SustitucionParsed("Yixuan", "Jazz caótico", 2, 1.0))
    m._last_agent_name = "Nangong Yu"
    m._dispatch_state(_frame(), _ST23)
    assert m._last_agent_name == "Nangong Yu"      # NO reseteado
    assert m._pending_swap is not None


# ---- check del dueño en S17 (los 4 desenlaces) -----------------------------

def _checks(m):
    return [d for d in m._diags if "check dueño" in d]


def test_cambio_de_dueno_dispara_el_toast(monkeypatch):
    """CAMBIÓ: el disco aparece en manos del destino → afirma el reemplazo."""
    m = _monitor(monkeypatch, SustitucionParsed("Yixuan", "Balada de la rama y la espada", 2, 1.0))
    m._last_agent_name = "Nangong Yu"
    m._process_s23_sustitucion(_frame(), _ST23)
    disc = _disc(slot=2, owner="Nangong Yu")
    m._check_swap_owner(disc, _ST17)

    assert m._toasts == [{"set_name": "Balada de la rama y la espada", "slot": 2,
                          "from_name": "Yixuan", "to_name": "Nangong Yu"}]
    assert m._pending_swap is None                 # consumido
    assert disc.swap_origin_hint == "Yixuan"       # hint para que la persistencia mueva la fila
    assert disc.swap_fresh is True
    assert any("CAMBIÓ" in c for c in _checks(m))


def test_dueno_observado_por_badge_tambien_vale(monkeypatch):
    """El ancla puede equivocarse y el badge tener razón (caso real: '[badge] ancla decía X pero
    el badge dice Y'). Exigir solo el dueño CERTERO perdía esos swaps."""
    m = _monitor(monkeypatch, SustitucionParsed("Yixuan", "Balada de la rama y la espada", 2, 1.0))
    m._last_agent_name = "Nangong Yu"
    m._process_s23_sustitucion(_frame(), _ST23)
    disc = _disc(slot=2, owner=None, visual="Nangong Yu")   # sin certero, solo observado
    m._check_swap_owner(disc, _ST17)
    assert m._toasts and m._toasts[0]["to_name"] == "Nangong Yu"
    assert disc.swap_fresh is True


def test_sin_cambio_no_dispara_ni_consume(monkeypatch):
    """SIN CAMBIO: el disco sigue con el origen → se canceló. Nada de toast, pending intacto."""
    m = _monitor(monkeypatch, SustitucionParsed("Yixuan", "Balada de la rama y la espada", 2, 1.0))
    m._last_agent_name = "Nangong Yu"
    m._process_s23_sustitucion(_frame(), _ST23)
    disc = _disc(slot=2, owner="Yixuan")           # sigue siendo del origen
    m._check_swap_owner(disc, _ST17)
    assert m._toasts == [] and disc.swap_fresh is False
    assert m._pending_swap is not None             # NO se consume: el swap puede llegar después
    assert any("sin cambio" in c for c in _checks(m))


def test_dueno_incierto_se_abstiene(monkeypatch):
    """INCIERTO: equipado pero sin nombre → abstenerse (RNF-02), y decirlo en el log."""
    m = _monitor(monkeypatch, SustitucionParsed("Yixuan", "Jazz caótico", 2, 1.0))
    m._last_agent_name = "Nangong Yu"
    m._process_s23_sustitucion(_frame(), _ST23)
    disc = _disc(set_canon="Jazz caótico", slot=2, owner=None)
    m._check_swap_owner(disc, _ST17)
    assert m._toasts == [] and m._pending_swap is not None
    assert any("incierto" in c for c in _checks(m))


def test_tercer_pj_se_abstiene(monkeypatch):
    """OTRO: ni el origen ni el destino → algo no cierra, no afirmar nada."""
    m = _monitor(monkeypatch, SustitucionParsed("Yixuan", "Balada de la rama y la espada", 2, 1.0))
    m._last_agent_name = "Nangong Yu"
    m._process_s23_sustitucion(_frame(), _ST23)
    disc = _disc(slot=2, owner="Ellen")
    m._check_swap_owner(disc, _ST17)
    assert m._toasts == [] and m._pending_swap is not None
    assert any("otro" in c for c in _checks(m))


def test_otro_set_o_slot_no_es_el_disco_del_swap(monkeypatch):
    """Otro disco → ni siquiera se chequea (no es el del swap): sin log y sin consumir."""
    m = _monitor(monkeypatch, SustitucionParsed("Yixuan", "Balada de la rama y la espada", 2, 1.0))
    m._last_agent_name = "Nangong Yu"
    m._process_s23_sustitucion(_frame(), _ST23)
    m._check_swap_owner(_disc(set_canon="Jazz caótico", slot=2, owner="Nangong Yu"), _ST17)
    m._check_swap_owner(_disc(slot=5, owner="Nangong Yu"), _ST17)
    assert m._pending_swap is not None and m._toasts == [] and _checks(m) == []


def test_el_log_del_check_sale_una_sola_vez_por_desenlace(monkeypatch):
    """El check corre en el ciclo continuo (muchas veces por segundo) → log por FLANCO (RNF-06)."""
    m = _monitor(monkeypatch, SustitucionParsed("Yixuan", "Jazz caótico", 2, 1.0))
    m._last_agent_name = "Nangong Yu"
    m._process_s23_sustitucion(_frame(), _ST23)
    for _ in range(8):
        m._check_swap_owner(_disc(set_canon="Jazz caótico", slot=2, owner=None), _ST17)
    assert len(_checks(m)) == 1


def test_el_pending_no_expira_por_reloj(monkeypatch):
    """FRESCURA = 'no superado todavía', NO 'dentro de N segundos' (2026-07-20).

    Regresión del QA en vivo: la emisión S17 tardó ~10 min (el handler estaba trabado) y el
    TTL de 120s mataba el toast de un swap que SÍ había ocurrido."""
    m = _monitor(monkeypatch, SustitucionParsed("Yixuan", "Jazz caótico", 2, 1.0))
    m._last_agent_name = "Nangong Yu"
    m._process_s23_sustitucion(_frame(), _ST23)
    m._pending_swap["ts"] -= 99999.0               # horas después: ya NO importa
    disc = _disc(set_canon="Jazz caótico", slot=2, owner="Nangong Yu")
    m._check_swap_owner(disc, _ST17)
    assert disc.swap_origin_hint == "Yixuan" and disc.swap_fresh is True
    assert m._pending_swap is None                 # consumido, no expirado


def test_un_s23_nuevo_reemplaza_al_pending_anterior(monkeypatch):
    """El pending ya no muere por reloj → el que lo acota es el swap SIGUIENTE."""
    import app.core.parser_sustitucion as psu
    m = _monitor(monkeypatch, SustitucionParsed("Yixuan", "Jazz caótico", 2, 1.0),
                 roster=("Yixuan", "Jane", "Nangong Yu"))
    m._last_agent_name = "Nangong Yu"
    m._process_s23_sustitucion(_frame(), _ST23)
    assert m._pending_swap["origin_name"] == "Yixuan"

    monkeypatch.setattr(psu, "parse_sustitucion",
                        lambda frame, ocr: SustitucionParsed("Jane", "Jazz caótico", 4, 1.0))
    m._process_s23_sustitucion(_frame(), _ST23)
    assert m._pending_swap["origin_name"] == "Jane"   # el viejo quedó superado
    assert m._pending_swap["slot"] == 4


def test_el_check_no_depende_de_que_el_disco_se_emita(monkeypatch):
    """El check vive en el ciclo continuo, NO en `_emit_s17_disc`.

    Regresión del QA 2026-07-20: el handler S17 estuvo 8m42s sin emitir (returns tempranos por
    OCR de baja confianza) y el reemplazo se perdió. El toast no puede colgar de que el disco
    madure — solo necesita (set, slot, dueño)."""
    m = _monitor(monkeypatch, SustitucionParsed("Yixuan", "Balada de la rama y la espada", 2, 1.0))
    emitidos: list = []
    m._on_disc = lambda disc, state: emitidos.append(disc)
    m._last_agent_name = "Nangong Yu"
    m._process_s23_sustitucion(_frame(), _ST23)

    m._check_swap_owner(_disc(slot=2, owner="Nangong Yu"), _ST17)
    assert m._toasts, "el toast debe salir sin pasar por la emisión"
    assert emitidos == [], "no hubo emisión del disco y aun así el toast salió"
