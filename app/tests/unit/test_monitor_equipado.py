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


# ---- el botón VETA al ancla ---------------------------------------------------

def _monitor_con_ancla(boton, monkeypatch, badge=None):
    """Monitor listo para que el ANCLA quiera disparar: hay latch y el slot es nuevo."""
    import app.core.monitor as mon_mod
    m = _monitor()
    m._last_agent_name = "Velina"
    m._s17_last_slot = 0                       # slot nuevo → el ancla aplica
    monkeypatch.setattr(mon_mod, "crop_grid_selected_badge", lambda f: badge)
    monkeypatch.setattr(m, "_refresh_action_button",
                        lambda d, f, badge_present=False: None)
    m._s17_action_btn = boton
    return m


def test_boton_equipar_veta_el_ancla(monkeypatch):
    """EL FP que encontró Daniel (QA 2026-07-23): Velina con el slot 1 VACÍO. Sin disco
    equipado, el "primer disco del slot" es un candidato libre — pero el ancla se lo atribuía
    igual, y el badge no podía desmentirla porque su AUSENCIA no cuenta como evidencia."""
    m = _monitor_con_ancla("equipar", monkeypatch)
    disc = _disc(libre=True, slot=1)
    m._assign_s17_pj(disc, np.zeros((1439, 2559, 3), np.uint8))
    assert disc.agente_asignado_nombre is None, "el ancla le adjudicó un disco libre al PJ"
    assert m._s17_last_slot == 0, "el ancla vetada no debe fijar el slot"


def test_boton_reemplazar_tambien_veta(monkeypatch):
    """'Reemplazar' = el slot tiene OTRO disco → el que se ve es un candidato, no el equipado."""
    m = _monitor_con_ancla("reemplazar", monkeypatch)
    disc = _disc(libre=True, slot=1)
    m._assign_s17_pj(disc, np.zeros((1439, 2559, 3), np.uint8))
    assert disc.agente_asignado_nombre is None


def test_boton_desequipar_deja_pasar_el_ancla(monkeypatch):
    """La contraparte: 'Desequipar' CONFIRMA que el disco lo lleva puesto este PJ."""
    m = _monitor_con_ancla("desequipar", monkeypatch)
    monkeypatch.setattr(m, "_s17_voted_owner", lambda f: "Velina")
    disc = _disc(slot=1)
    m._assign_s17_pj(disc, np.zeros((1439, 2559, 3), np.uint8))
    assert disc.agente_asignado_nombre == "Velina"


def test_sin_lectura_del_boton_el_ancla_se_comporta_como_siempre(monkeypatch):
    """RNF-02 al revés: el guard solo actúa ante evidencia POSITIVA en contra. Si el OCR no
    leyó el botón (None), no se cambia nada — no se rompe lo que ya andaba."""
    m = _monitor_con_ancla(None, monkeypatch)
    monkeypatch.setattr(m, "_s17_voted_owner", lambda f: "Velina")
    disc = _disc(slot=1)
    m._assign_s17_pj(disc, np.zeros((1439, 2559, 3), np.uint8))
    assert disc.agente_asignado_nombre == "Velina"


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
        m._refresh_action_button(libre, frame, badge_present=False)
    assert len(llamadas) == 1                      # mismo disco, mismo badge → 1 sola lectura
    # El badge APARECIÓ (lo equiparon) → el botón pudo cambiar a 'Desequipar' → releer.
    m._refresh_action_button(libre, frame, badge_present=True)
    assert len(llamadas) == 2
    # Otro disco distinto (substats distintos) también fuerza la relectura.
    m._refresh_action_button(_disc(subs=("ATK%", "PEN")), frame, badge_present=True)
    assert len(llamadas) == 3


def _lector_de_boton(monkeypatch, valores: list):
    """Stub de `read_s17_action_button` que devuelve `valores` uno por lectura (el último se
    repite). Devuelve la lista de lecturas hechas, para contarlas."""
    import app.core.parser_disc_s17 as p17
    hechas: list[str] = []

    def _leer(frame, ocr):
        v = valores[min(len(hechas), len(valores) - 1)]
        hechas.append(v)
        return v

    monkeypatch.setattr(p17, "read_s17_action_button", _leer)
    return hechas


def test_con_pendiente_abierto_el_boton_se_relee_en_cada_ciclo(monkeypatch):
    """EL BUG del caso A (QA 2026-07-23): equipar un disco libre en un slot VACÍO no cambia la
    identidad (mismo disco) ni `badge_present` (ya estaba en True) → con el gate viejo el botón
    quedaba cacheado en 'equipar' PARA SIEMPRE y el check se abstenía con "solo badge" sin fin."""
    hechas = _lector_de_boton(monkeypatch, ["equipar"])
    m = _monitor()
    frame = np.zeros((1439, 2559, 3), np.uint8)
    libre = _disc(libre=True)
    m._refresh_action_button(libre, frame, badge_present=True)
    _armado(m, libre)                                  # ← pendiente abierto sobre ESTE disco
    for _ in range(3):
        m._refresh_action_button(libre, frame, badge_present=True)
    assert len(hechas) == 4, "con un pendiente abierto el botón debe releerse en cada ciclo"


def test_el_bypass_esta_acotado_al_disco_del_pendiente(monkeypatch):
    """RNF-06: el bypass no es "pendiente abierto ⇒ OCR libre". Si mirás OTRO disco mientras el
    pendiente sigue vivo, vuelve a regir el gate normal."""
    hechas = _lector_de_boton(monkeypatch, ["equipar"])
    m = _monitor()
    frame = np.zeros((1439, 2559, 3), np.uint8)
    _armado(m, _disc(libre=True))
    otro = _disc(libre=True, subs=("ATK%", "PEN"))
    for _ in range(4):
        m._refresh_action_button(otro, frame, badge_present=False)
    assert len(hechas) == 1


def test_caso_A_el_disco_libre_en_slot_vacio_termina_disparando(monkeypatch):
    """De punta a punta con la lectura REAL del gate (sin stubbear `_s17_action_btn`): el botón
    voltea a 'desequipar' en el 2º ciclo y el toast sale. Es el caso que quedó ABIERTO en el QA."""
    hechas = _lector_de_boton(monkeypatch, ["equipar", "desequipar"])
    m = _monitor()
    frame = np.zeros((1439, 2559, 3), np.uint8)
    libre = _disc(libre=True)
    m._last_agent_name = "Nangong Yu"
    m._refresh_action_button(libre, frame, badge_present=True)
    m._arm_libre_pending(libre)
    assert m._pending_swap is not None
    # Ciclo siguiente: Daniel equipó. Mismo disco, mismo badge, pero el botón cambió.
    puesto = _disc(visual="Nangong Yu")
    m._refresh_action_button(puesto, frame, badge_present=True)
    assert m._s17_action_btn == "desequipar"
    m._check_swap_owner(puesto, _ST17)
    assert [e.get("kind") for e in m._eventos] == ["equipado"]
    assert m._pending_swap is None


# ---- identidad difusa: el disco B (gemelo, OCR sucio) del QA 2026-07-23 -------

def _ident(m, **kw):
    return m._disc_identity(_disc(**kw))


def test_fuzzy_tolera_un_substat_mal_leido():
    """Un solo substat cambia de nombre entre armar y chequear (OCR sucio a conf 0.89) → sigue
    siendo el mismo disco. Es EXACTAMENTE lo que rompía el disco B en el QA."""
    m = _monitor()
    a = _ident(m, subs=("CR", "CD", "ATK%", "PEN"))
    b = _ident(m, subs=("CR", "CD", "ATK%", "HP%"))   # PEN→HP% (1 mal leído)
    assert m._same_disc_fuzzy(a, b)


def test_fuzzy_no_confunde_discos_genuinamente_distintos():
    """Dos substats distintos ya es otro disco: la guarda del falso positivo sigue en pie."""
    m = _monitor()
    a = _ident(m, subs=("CR", "CD", "ATK%", "PEN"))
    b = _ident(m, subs=("CR", "CD", "DEF%", "HP%"))   # 2 distintos
    assert not m._same_disc_fuzzy(a, b)


def test_fuzzy_exige_nucleo_exacto():
    """Set, slot y main NO se aflojan: solo los substats toleran ruido. Las identidades se
    arman a mano (mismo formato que `_disc_identity`: set, slot, main, {(substat, rolls)})."""
    m = _monitor()
    subs = (("cr", 0), ("cd", 0), ("atk%", 0), ("pen", 0))
    base = ("balada de la rama y la espada", 2, "atk", subs)
    assert m._same_disc_fuzzy(base, base)
    assert not m._same_disc_fuzzy(base, ("balada de la rama y la espada", 5, "atk", subs))
    assert not m._same_disc_fuzzy(base, ("balada de la rama y la espada", 2, "cr", subs))
    assert not m._same_disc_fuzzy(base, ("otro set", 2, "atk", subs))


def test_disco_B_con_substat_sucio_igual_dispara():
    """Regresión del QA 2026-07-23: armás con 4 substats y al confirmar uno se leyó distinto.
    Con la identidad exacta el check salía mudo; con fuzzy dispara igual."""
    m = _monitor()
    libre = _disc(libre=True, subs=("CR", "CD", "ATK%", "PEN"))
    _armado(m, libre, boton="reemplazar")
    m._s17_action_btn = "desequipar"
    sucio = _disc(owner="Nangong Yu", subs=("CR", "CD", "ATK%", "HP%"))   # PEN→HP%
    m._check_swap_owner(sucio, _ST17)
    assert [e.get("kind") for e in m._eventos] == ["equipado"]


def test_reamar_no_se_dispara_por_parpadeo_de_substats():
    """El re-log/re-arm espurio del QA (14:08:16 y 14:09:07 la misma línea): un substat parpadea
    y el pendiente se re-armaba con seq nueva. Con fuzzy, el mismo disco no re-arma."""
    m = _monitor()
    _armado(m, _disc(libre=True, subs=("CR", "CD", "ATK%", "PEN")))
    seq = m._pending_swap["seq"]
    _armado(m, _disc(libre=True, subs=("CR", "CD", "ATK%", "HP%")))   # 1 substat parpadeó
    assert m._pending_swap["seq"] == seq                              # no re-armó
    assert len([x for x in m._diags if x.startswith("[equipado]")]) == 1


# ---- dedup con dueño: el detalle vuelve a salir al equipar --------------------

def test_dedup_reemite_el_detalle_al_equipar():
    """Lo que pidió Daniel (QA 2026-07-23): tras equipar un disco visto libre, su detalle debe
    volver a loguearse. El dedup era ciego al dueño → misma identidad → nunca re-emitía."""
    emitidos: list = []
    m = _monitor()
    m._on_disc = lambda d, s: emitidos.append(d.agente_asignado_nombre)
    libre = _disc(libre=True)
    m._emit_s17_disc(libre, _ST17, mature=True)
    m._emit_s17_disc(libre, _ST17, mature=True)                 # parpadeo del 3D → NO re-emite
    assert emitidos == [None]
    puesto = _disc(owner="Nangong Yu")                          # ahora equipado
    m._emit_s17_disc(puesto, _ST17, mature=True)
    assert emitidos == [None, "Nangong Yu"]                     # re-emite con el dueño nuevo
    m._emit_s17_disc(puesto, _ST17, mature=True)                # y ya no vuelve a repetir
    assert emitidos == [None, "Nangong Yu"]


# ---- confirmar aunque el disco ya haya emitido (gate de _disc_emitted) --------

def test_equipar_un_disco_ya_emitido_igual_confirma(monkeypatch):
    """EL bug de fondo del QA 2026-07-23 ("sigo cambiando discos y no lo detecta"): equipar por
    REEMPLAZAR cambia la firma tan poco que NO hay reset, y el gate `if self._disc_emitted:
    return` cortaba antes del check → 74s de log mudo. Con un pendiente LIBRE abierto, el check
    debe correr igual sobre el merge ya logrado, sin re-OCR del disco entero."""
    import types
    m = _monitor()
    _armado(m, _disc(libre=True), boton="reemplazar")            # pendiente libre, dest Nangong Yu
    sig = (np.zeros((48, 24), np.float32), np.zeros((48, 48), np.float32),
           np.zeros((24, 24), np.float32))
    monkeypatch.setattr(m, "_s17_disc_signature", lambda frame: sig)
    m._disc_agg_sig = sig                                        # firma estable → sin reset
    m._disc_emitted = True                                       # el disco YA emitió (libre)
    m._disc_aggregator = types.SimpleNamespace(current=_disc(owner="Nangong Yu"))
    # Al entrar al gate se refresca el dueño por badge (ahora Nangong Yu) y el botón ya viró.
    monkeypatch.setattr(m, "_assign_s17_pj",
                        lambda disc, frame: setattr(disc, "agente_asignado_nombre", "Nangong Yu"))
    m._s17_action_btn = "desequipar"
    m._process_disc_s17_continuous(None, _ST17)
    assert [e.get("kind") for e in m._eventos] == ["equipado"]


def test_disco_ya_emitido_sin_pendiente_no_corre_el_check(monkeypatch):
    """RNF-06: el gate solo se afloja con un pendiente LIBRE vivo. Sin pendiente, sigue cortando
    (no gastar OCR ni badge por ciclo sobre un disco ya cerrado)."""
    import types
    llamado = []
    m = _monitor()
    sig = (np.zeros((48, 24), np.float32), np.zeros((48, 48), np.float32),
           np.zeros((24, 24), np.float32))
    monkeypatch.setattr(m, "_s17_disc_signature", lambda frame: sig)
    m._disc_agg_sig = sig
    m._disc_emitted = True
    m._pending_swap = None
    m._disc_aggregator = types.SimpleNamespace(current=_disc(owner="Nangong Yu"))
    monkeypatch.setattr(m, "_check_swap_owner", lambda *a, **k: llamado.append(1))
    m._process_disc_s17_continuous(None, _ST17)
    assert llamado == []
