"""Puente de sustitución de disco entre PJs (S23 → hint en S17) en el monitor.

Rediseño 2026-07-19: ver el diálogo S23 ARMA un swap pendiente {origen, set, slot, destino=latch}.
La confirmación NO es un toast disparado desde acá, sino que cuando el flujo S17 emite ese disco
(set+slot) equipado por el DESTINO, el monitor le ADJUNTA el hint de origen (`swap_origin_hint`)
y lo marca fresco (`swap_fresh`). La persistencia usa el hint para MOVER la fila (sin duplicar) y
el controller dispara el toast. Si el disco no llega dentro del TTL, el pending expira en silencio.

Se stubbea `parse_sustitucion` (la lectura real está en `test_parser_sustitucion`); acá se testea
el armado del pending y el adjuntado del hint / expiración.
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


def _disc(set_canon="Balada de la rama y la espada", slot=2, owner=None):
    """DiscParsed de un disco S17 ya resuelto (owner = agente_asignado_nombre)."""
    return DiscParsed(
        set_name_raw=set_canon, set_name_canon=set_canon, slot=slot,
        main_stat_raw="ATK", main_stat_canon="ATK", main_valor=79, main_unidad="flat",
        nivel=0, rareza="S", agente_asignado_nombre=owner,
    )


def _monitor(monkeypatch, sust, roster=("Yixuan", "Nangong Yu")):
    import app.core.monitor as mon_mod
    import app.core.parser_sustitucion as psu
    diags: list[str] = []
    m = mon_mod.Monitor(
        ocr=object(), detector=None, on_diagnostic=diags.append,
        set_repo=_SetRepo(), agent_identifier=_Identifier(roster),
    )
    m._diags = diags
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


# ---- adjuntado del hint en S17 ---------------------------------------------

def test_adjunta_el_hint_cuando_s17_muestra_el_disco_en_el_destino(monkeypatch):
    m = _monitor(monkeypatch, SustitucionParsed("Yixuan", "Balada de la rama y la espada", 2, 1.0))
    m._last_agent_name = "Nangong Yu"
    m._process_s23_sustitucion(_frame(), _ST23)
    # S17 muestra el mismo disco (set+slot) ahora equipado por el destino → adjunta el hint.
    disc = _disc(slot=2, owner="Nangong Yu")
    m._attach_swap_hint(disc, _ST17)

    assert m._pending_swap is None                 # pending consumido
    assert disc.swap_origin_hint == "Yixuan"       # hint de origen adjuntado
    assert disc.swap_fresh is True                 # fresco → el controller disparará el toast
    assert any("✓" in d for d in _reemplazos(m))


def test_no_adjunta_si_lo_equipa_otro_pj(monkeypatch):
    m = _monitor(monkeypatch, SustitucionParsed("Yixuan", "Balada de la rama y la espada", 2, 1.0))
    m._last_agent_name = "Nangong Yu"
    m._process_s23_sustitucion(_frame(), _ST23)
    disc = _disc(slot=2, owner="Ellen")            # otro dueño, no el destino
    m._attach_swap_hint(disc, _ST17)
    assert m._pending_swap is not None and disc.swap_origin_hint is None


def test_no_adjunta_si_el_disco_no_esta_equipado(monkeypatch):
    """Un candidato (sin agente_asignado) no adjunta: hay que ver el disco EQUIPADO."""
    m = _monitor(monkeypatch, SustitucionParsed("Yixuan", "Jazz caótico", 2, 1.0))
    m._last_agent_name = "Nangong Yu"
    m._process_s23_sustitucion(_frame(), _ST23)
    disc = _disc(set_canon="Jazz caótico", slot=2, owner=None)
    m._attach_swap_hint(disc, _ST17)
    assert m._pending_swap is not None and disc.swap_origin_hint is None


def test_no_adjunta_otro_set_o_slot(monkeypatch):
    m = _monitor(monkeypatch, SustitucionParsed("Yixuan", "Balada de la rama y la espada", 2, 1.0))
    m._last_agent_name = "Nangong Yu"
    m._process_s23_sustitucion(_frame(), _ST23)
    m._attach_swap_hint(_disc(set_canon="Jazz caótico", slot=2, owner="Nangong Yu"), _ST17)
    m._attach_swap_hint(_disc(slot=5, owner="Nangong Yu"), _ST17)
    assert m._pending_swap is not None


def test_el_pending_expira_por_ttl(monkeypatch):
    m = _monitor(monkeypatch, SustitucionParsed("Yixuan", "Jazz caótico", 2, 1.0))
    m._last_agent_name = "Nangong Yu"
    m._process_s23_sustitucion(_frame(), _ST23)
    m._pending_swap["ts"] -= 999.0                 # vencido
    disc = _disc(set_canon="Jazz caótico", slot=2, owner="Nangong Yu")
    m._attach_swap_hint(disc, _ST17)
    assert m._pending_swap is None and disc.swap_origin_hint is None   # expiró sin adjuntar


def test_emit_s17_adjunta_el_hint(monkeypatch):
    """Integración: `_emit_s17_disc` llama a `_attach_swap_hint` (antes del dedup)."""
    m = _monitor(monkeypatch, SustitucionParsed("Yixuan", "Balada de la rama y la espada", 2, 1.0))
    captured: list = []
    m._on_disc = lambda disc, state: captured.append(disc)
    m._last_agent_name = "Nangong Yu"
    m._process_s23_sustitucion(_frame(), _ST23)
    m._emit_s17_disc(_disc(slot=2, owner="Nangong Yu"), _ST17, True)
    assert captured and captured[0].swap_origin_hint == "Yixuan" and captured[0].swap_fresh
    assert m._pending_swap is None
