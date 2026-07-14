"""
Tests de la asignación de PJ en S17 (disco equipado) — Hito captura S17, 2026-06-06.

Cubre las tres piezas del item #5 ("PJ asignado"):
  1. `crop_s17_assigned_avatar`: localiza el avatar circular anclado al Y de la
     barra de nivel (que se desplaza con el largo del nombre del set), y devuelve
     None cuando no hay avatar (disco sin equipar).
  2. `AgentIdentifier` guarda S17 (mismo/distinto vs el latch): same-PJ confirma,
     otro PJ abstiene. Más `identify_face` (descriptor rectangular del row).
  3. Persistencia con salvaguarda: `insert_from_parsed` con asignación,
     `update_assignment`, y `update_from_parsed` que NO pisa lo curado.

Los tests de crop/guarda usan PNG reales (se saltean si no están).
"""
import json
import sqlite3
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.parser_disc_s17 import (
    crop_s17_assigned_avatar,
    _has_avatar_content,
    _detail_level_bbox,
    detect_active_set_tier,
)
from app.core.agent_identifier import AgentIdentifier
from app.core.parser_disc import DiscParsed, SubstatParsed
from app.db.repositories import InventoryDiscRepo

REPO = Path(__file__).resolve().parents[3]
_FIX = REPO / "app" / "tests" / "fixtures" / "s17_ocr"
_PNG = REPO / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers" / "04_Inventario_Disco_Vista_Individual"


def _load_frame_lines(name: str):
    """(frame, lines, W, H) desde el PNG real + el OCR cacheado. Skip si falta."""
    jp = _FIX / f"{name}.json"
    pp = _PNG / f"{name}.png"
    if not jp.exists() or not pp.exists():
        pytest.skip(f"fixture/png no encontrado: {name}")
    d = json.loads(jp.read_text(encoding="utf-8"))
    lines = [(t, c, tuple(bb)) for t, c, bb in d["lines"]]
    frame = cv2.imread(str(pp))
    if frame is None:
        pytest.skip(f"no se pudo leer PNG: {name}")
    return frame, lines, d["W"], d["H"]


# --- 1. Crop del avatar -------------------------------------------------------

@pytest.mark.parametrize("name", ["Ejemplo_1", "Ejemplo_8", "Ejemplo_9", "Ejemplo_10"])
def test_crop_avatar_presente(name):
    """Discos equipados reales: el crop existe y es un cuadrado razonable."""
    frame, lines, W, H = _load_frame_lines(name)
    face = crop_s17_assigned_avatar(frame, lines, W, H)
    assert face is not None, f"{name}: no se localizó el avatar"
    h, w = face.shape[:2]
    assert h == w and 40 <= h <= 140, f"{name}: crop raro {face.shape}"


def test_crop_sigue_el_y_de_la_barra_de_nivel():
    """
    El Y del crop debe SEGUIR la barra de nivel: Ejemplo_1 (nombre 1 línea, nivel
    más arriba) vs Ejemplo_10 (nombre 2 líneas, nivel más abajo) → distinto cy.
    """
    f1, l1, W1, H1 = _load_frame_lines("Ejemplo_1")
    f10, l10, W10, H10 = _load_frame_lines("Ejemplo_10")
    bb1 = _detail_level_bbox(l1, W1)
    bb10 = _detail_level_bbox(l10, W10)
    cy1 = (bb1[1] + bb1[3]) // 2
    cy10 = (bb10[1] + bb10[3]) // 2
    assert cy10 > cy1 + 20, f"el nivel de Ej10 (2 líneas) debe estar más abajo: {cy1} vs {cy10}"


def test_crop_sin_barra_de_nivel_devuelve_none():
    """Sin línea de nivel en el panel de detalle → no se puede anclar → None."""
    frame = np.zeros((1439, 2557, 3), dtype=np.uint8)
    assert crop_s17_assigned_avatar(frame, [("ruido", 0.9, (10, 10, 80, 40))], 2557, 1439) is None


def test_has_avatar_content_distingue_avatar_de_fondo():
    """Crop con avatar real → True; crop gris uniforme (disco sin equipar) → False."""
    frame, lines, W, H = _load_frame_lines("Ejemplo_1")
    face = crop_s17_assigned_avatar(frame, lines, W, H)
    assert face is not None and _has_avatar_content(face)
    gris = np.full((76, 76, 3), 40, dtype=np.uint8)  # fondo oscuro casi sin saturación
    assert not _has_avatar_content(gris)


def test_crop_avatar_ausente_devuelve_none():
    """Frame con barra de nivel pero región del avatar vacía (gris) → None."""
    frame = np.full((1439, 2557, 3), 38, dtype=np.uint8)
    # línea de nivel sintética en el panel de detalle (xn≈0.36)
    lines = [("Nivel 15/15", 0.95, (924, 249, 1103, 286))]
    assert crop_s17_assigned_avatar(frame, lines, 2557, 1439) is None


# --- 1b. Tier de conjunto activo (color del texto) ---------------------------

@pytest.mark.parametrize("name,esperado", [
    ("Ejemplo_1", 2),   # Jazz caótico 2pc (4pistas en gris)
    ("Ejemplo_8", 2),
    ("Ejemplo_2", 4),   # 4pistas en blanco → 4pc activo
    ("Ejemplo_4", 4),
    ("Ejemplo_9", 4),
    ("Ejemplo_10", 4),
])
def test_detect_active_tier(name, esperado):
    frame, lines, W, H = _load_frame_lines(name)
    assert detect_active_set_tier(frame, lines, W, H) == esperado


def test_detect_active_tier_sin_pistas_none():
    frame = np.zeros((1439, 2557, 3), dtype=np.uint8)
    assert detect_active_set_tier(frame, [("ruido", 0.9, (10, 10, 80, 40))], 2557, 1439) is None


# --- 2. Guarda S17 del identificador -----------------------------------------

def test_guarda_s17_confirma_mismo_pj_y_abstiene_otro(tmp_path):
    """
    Fase 5R: aprendido el badge de un PJ, el MISMO badge confirma (sim alto) y el de
    OTRO PJ abstiene (sim bajo). Usa íconos reales del roster (descriptor robusto).
    """
    refs = REPO / "app" / "resources" / "avatar_refs"
    ellen = cv2.imread(str(refs / "Ellen.png"))
    lycaon = cv2.imread(str(refs / "Lycaon.png"))
    assert ellen is not None and lycaon is not None
    ident = AgentIdentifier(library_path=tmp_path / "lib.npz", autoload=False, roster={"PJ_A"})
    ident.learn_s17(ellen, "PJ_A")
    assert ident.s17_similarity(ellen, "PJ_A") >= 0.86          # mismo → confirma
    s_other = ident.s17_similarity(lycaon, "PJ_A")
    assert s_other is not None and s_other < 0.86               # otro → abstiene


def test_s17_similarity_none_si_pj_no_aprendido():
    """Sin descriptor aprendido para el PJ → None (bootstrap, confiar en latch)."""
    ident = AgentIdentifier(autoload=False)
    fr, ln, W, H = _load_frame_lines("Ejemplo_1")
    f = crop_s17_assigned_avatar(fr, ln, W, H)
    assert ident.s17_similarity(f, "Desconocido") is None


def test_identify_face_sin_libreria_devuelve_none():
    """`identify_face` (descriptor row) sin librería cargada → None, no crashea."""
    ident = AgentIdentifier(autoload=False)
    assert ident.identify_face(np.zeros((30, 30, 3), dtype=np.uint8)) is None


# --- 3. Persistencia con salvaguarda -----------------------------------------

def _disc(slot=1, set_name="Jazz caótico"):
    return DiscParsed(
        set_name_raw=set_name, set_name_canon=set_name, slot=slot,
        main_stat_raw="PV", main_stat_canon="HP", main_valor=2200.0, main_unidad="flat",
        nivel=15, rareza="S",
        subs=[SubstatParsed("ATK", "ATK", 38.0, "flat", 1, 0.95)],
        confianza_global=0.95,
    )


def test_disc_identity_distingue_mismo_set_slot_distintos_substats():
    """Bug 2026-06-12 ('Yanagi no logueaba'): (set, slot, main) es demasiado grueso —
    en slot 1 el main es siempre HP → dos discos distintos del MISMO set en slot 1
    colapsaban y el 2º nunca se emitía. La identidad ahora incluye substats."""
    from app.core.monitor import Monitor
    base = dict(set_name_raw="Jazz oscilante", set_name_canon="Jazz oscilante", slot=1,
                main_stat_raw="PV", main_stat_canon="HP", main_valor=2200.0,
                main_unidad="flat", nivel=15, rareza="S", confianza_global=0.95)
    d1 = DiscParsed(**base, subs=[SubstatParsed("ATK", "ATK", 38.0, "flat", 1, 0.95),
                                  SubstatParsed("Daño Crítico", "Daño Crítico", 9.6, "%", 1, 0.95)])
    d2 = DiscParsed(**base, subs=[SubstatParsed("Perforación", "Perforación", 9.0, "flat", 0, 0.95),
                                  SubstatParsed("HP%", "HP%", 3.0, "%", 0, 0.95)])
    # mismo set+slot+main pero substats distintos → identidades DISTINTAS (ambos emiten)
    assert Monitor._disc_identity(d1) != Monitor._disc_identity(d2)
    # el MISMO disco re-parseado (animación) → misma identidad (sigue deduplicando)
    d1b = DiscParsed(**base, subs=[SubstatParsed("Daño Crítico", "Daño Crítico", 9.6, "%", 1, 0.95),
                                   SubstatParsed("ATK", "ATK", 38.0, "flat", 1, 0.95)])  # orden distinto
    assert Monitor._disc_identity(d1) == Monitor._disc_identity(d1b)


def test_equip_map_registra_solo_equipados(monkeypatch, tmp_path):
    """5R.C: el mapa disco→dueño se escribe SOLO con la identidad+dueño del disco
    equipado (verdad de tierra del flujo-ancla), serializado con clave estable."""
    import json
    from app.core.monitor import Monitor
    mappath = tmp_path / "equip_map.json"
    monkeypatch.setenv("DANIBOD_EQUIP_MAP", str(mappath))
    m = _monitor()
    d = _disc(slot=1, set_name="Jazz oscilante")
    ident = Monitor._disc_identity(d)
    m._record_equip_map(ident, "Burnice")
    data = json.loads(mappath.read_text(encoding="utf-8"))
    key = Monitor._identity_to_key(ident)
    assert data == {key: "Burnice"}
    assert key.startswith("jazzoscilante#1#")         # clave determinista (norm sin espacios)
    # idempotente: mismo (ident, dueño) no reescribe distinto
    m._record_equip_map(ident, "Burnice")
    assert json.loads(mappath.read_text(encoding="utf-8")) == {key: "Burnice"}


def test_equip_map_no_clobberea_entradas_previas(monkeypatch, tmp_path):
    """5R.C fix: al detener/reanudar captura se recrea el Monitor (_equip_map={}).
    El primer write de la instancia nueva debe MERGEAR el JSON existente, no pisarlo:
    los PJs de pases previos se conservan. Regresión del bug de pérdida 2026-06-12."""
    import json
    from app.core.monitor import Monitor
    mappath = tmp_path / "equip_map.json"
    monkeypatch.setenv("DANIBOD_EQUIP_MAP", str(mappath))
    # Pase 1 (instancia A): registra a Nangong Yu.
    a = _monitor()
    d1 = _disc(slot=1, set_name="Jazz caótico")
    a._record_equip_map(Monitor._disc_identity(d1), "Nangong Yu")
    k1 = Monitor._identity_to_key(Monitor._disc_identity(d1))
    # Pausa/reanudación → instancia NUEVA con _equip_map vacío.
    b = _monitor()
    assert b._equip_map == {}
    d2 = _disc(slot=2, set_name="Melodía de Faetón")
    b._record_equip_map(Monitor._disc_identity(d2), "Yuzuha")
    k2 = Monitor._identity_to_key(Monitor._disc_identity(d2))
    data = json.loads(mappath.read_text(encoding="utf-8"))
    assert data == {k1: "Nangong Yu", k2: "Yuzuha"}   # ambos, no clobber


def test_equip_map_noop_sin_env(monkeypatch, tmp_path):
    """Sin DANIBOD_EQUIP_MAP, _record_equip_map no escribe nada (no-op)."""
    from app.core.monitor import Monitor
    monkeypatch.delenv("DANIBOD_EQUIP_MAP", raising=False)
    m = _monitor()
    m._record_equip_map(Monitor._disc_identity(_disc()), "Rina")
    assert list(tmp_path.glob("*.json")) == []


@pytest.fixture
def disc_db():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE inventory_discs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            set_id INTEGER, slot INTEGER NOT NULL,
            main_stat TEXT, main_valor REAL, unidad_main TEXT,
            sub1 TEXT, val1 REAL, rolls1 INTEGER DEFAULT 0, unidad1 TEXT,
            sub2 TEXT, val2 REAL, rolls2 INTEGER DEFAULT 0, unidad2 TEXT,
            sub3 TEXT, val3 REAL, rolls3 INTEGER DEFAULT 0, unidad3 TEXT,
            sub4 TEXT, val4 REAL, rolls4 INTEGER DEFAULT 0, unidad4 TEXT,
            nivel INTEGER DEFAULT 0,
            equipado INTEGER DEFAULT 0,
            agente_asignado INTEGER,
            descartado INTEGER DEFAULT 0,
            score_evaluacion REAL, agentes_compatibles TEXT, notas TEXT
        );
    """)
    con.commit()
    yield con
    con.close()


def test_insert_con_asignacion_setea_pj_y_equipado(disc_db):
    repo = InventoryDiscRepo(disc_db)
    did = repo.insert_from_parsed(_disc(), set_id=1, agente_asignado=7, equipado=1)
    r = disc_db.execute("SELECT agente_asignado, equipado FROM inventory_discs WHERE id=?", (did,)).fetchone()
    assert r["agente_asignado"] == 7 and r["equipado"] == 1


def test_insert_sin_asignacion_queda_null_y_no_equipado(disc_db):
    repo = InventoryDiscRepo(disc_db)
    did = repo.insert_from_parsed(_disc(), set_id=1)
    r = disc_db.execute("SELECT agente_asignado, equipado FROM inventory_discs WHERE id=?", (did,)).fetchone()
    assert r["agente_asignado"] is None and r["equipado"] == 0


def test_update_from_parsed_preserva_asignacion_curada(disc_db):
    """
    Re-captura de stats SIN asignación confiable: update_from_parsed NO debe pisar
    agente_asignado/equipado existentes (lo curado se preserva, RNF-02).
    """
    repo = InventoryDiscRepo(disc_db)
    did = repo.insert_from_parsed(_disc(), set_id=1, agente_asignado=3, equipado=1)
    # Re-captura con nivel/subs nuevos pero sin tocar la asignación
    nuevo = _disc()
    nuevo.nivel = 12
    repo.update_from_parsed(did, nuevo)
    r = disc_db.execute("SELECT agente_asignado, equipado, nivel FROM inventory_discs WHERE id=?", (did,)).fetchone()
    assert r["agente_asignado"] == 3 and r["equipado"] == 1, "no debe pisar lo curado"
    assert r["nivel"] == 12, "sí debe actualizar el nivel"


def test_update_assignment_reasigna_a_otro_pj(disc_db):
    """Asignación confiable nueva (latch+avatar) → mueve el disco de PJ."""
    repo = InventoryDiscRepo(disc_db)
    did = repo.insert_from_parsed(_disc(), set_id=1, agente_asignado=3, equipado=1)
    repo.update_assignment(did, 9)
    r = disc_db.execute("SELECT agente_asignado, equipado FROM inventory_discs WHERE id=?", (did,)).fetchone()
    assert r["agente_asignado"] == 9 and r["equipado"] == 1


# --- 4. Orquestación en el monitor (_assign_s17_pj) --------------------------

class _DummyOcr:
    def text(self, img, psm=6, lang="spa"):
        return ("", 0.0)
    def text_with_bboxes(self, frame):
        return []


def _monitor():
    from app.core.detector import ScreenDetector
    from app.core.monitor import Monitor
    return Monitor(ocr=_DummyOcr(), detector=ScreenDetector())


def test_maybe_harvest_etiqueta_y_capea(tmp_path, monkeypatch):
    """5R.3: con DANIBOD_HARVEST guarda frames etiquetados por latch, cap por (PJ,estado)."""
    import numpy as _np
    from app.core.detector import ScreenState
    from app.core import monitor as _mon
    monkeypatch.setenv("DANIBOD_HARVEST", str(tmp_path))
    m = _monitor()
    m._last_agent_name = "Zhu Yuan"
    frame = _np.zeros((64, 64, 3), _np.uint8)
    st = ScreenState("S8", 0.9, "")
    for _ in range(_mon._HARVEST_CAP + 3):
        m._maybe_harvest(frame, st)
    files = list(tmp_path.glob("*.png"))
    assert len(files) == _mon._HARVEST_CAP            # cap respetado
    assert all("__S8__" in f.name for f in files)     # etiquetado por estado


def test_maybe_harvest_gates(tmp_path, monkeypatch):
    """Sin env o sin latch o estado no-cosechable → no escribe."""
    import numpy as _np
    from app.core.detector import ScreenState
    frame = _np.zeros((64, 64, 3), _np.uint8)
    st = ScreenState("S8", 0.9, "")
    monkeypatch.delenv("DANIBOD_HARVEST", raising=False)
    m = _monitor(); m._last_agent_name = "X"
    m._maybe_harvest(frame, st)                        # sin env
    assert list(tmp_path.glob("*.png")) == []
    monkeypatch.setenv("DANIBOD_HARVEST", str(tmp_path))
    m2 = _monitor(); m2._last_agent_name = None
    m2._maybe_harvest(frame, st)                       # sin latch
    assert list(tmp_path.glob("*.png")) == []
    m3 = _monitor(); m3._last_agent_name = "X"
    m3._maybe_harvest(frame, ScreenState("S12", 0.0, ""))  # estado no-cosechable
    assert list(tmp_path.glob("*.png")) == []


class _StubIdent:
    """Identificador controlado para testear la lógica de `_assign_s17_pj` (5R.5)
    sin depender de fixtures: define la similitud al latch y el dueño identificado."""
    def __init__(self, sim=None, owner=None, free=False, det_owner=None,
                 det_conf=0.66, det_margin=0.5):
        self._sim = sim; self._owner = owner; self.learned = []
        self._roster_norm = {}; self._free = free
        self._det_owner = det_owner; self.learned_detail = []
        # Para el gate de presencia del detalle (5R.L.7.3): conf+margen del crop cuando NO
        # hay dueño identificado. Default = avatar real presente (margen claro); un crop
        # espurio tipo texto '(N)' se modela con det_margin chico (~0.02).
        self._det_conf = det_conf; self._det_margin = det_margin

    def s17_similarity(self, badge, name):
        return self._sim

    def identify_s17(self, badge, min_sim=0.80):
        return self._owner

    def s17_match(self, badge, min_sim=0.80):
        if self._owner:
            return self._owner[0], self._owner[1], False
        # sin dueño: 'free' simula badge en reject-set/conf baja; si no, conf media.
        return (None, 0.40, True) if self._free else (None, 0.70, False)

    def s17_match_detail(self, badge, min_sim=0.80):
        if self._det_owner:
            return self._det_owner[0], self._det_owner[1], 0.5, False
        return None, self._det_conf, self._det_margin, False

    def learn_s17(self, badge, name):
        self.learned.append(name); return True

    def learn_s17_detail(self, badge, name):
        self.learned_detail.append(name); return True


def _monitor_badge(monkeypatch, sim=None, owner=None):
    """Monitor con badge presente (stub de `crop_grid_selected_badge`) + identificador
    controlado, latch=Zhu Yuan."""
    import numpy as np
    import app.core.monitor as mon
    monkeypatch.setattr(mon, "crop_grid_selected_badge",
                        lambda f: np.zeros((40, 40, 3), np.uint8))
    m = _monitor()
    m._identifier = _StubIdent(sim, owner)
    m._last_agent_name = "Zhu Yuan"
    return m


def _frame():
    import numpy as np
    return np.zeros((720, 1280, 3), np.uint8)


def test_monitor_equipado_por_flujo_asigna_y_cosecha(monkeypatch):
    """Anchor de flujo (5R.5b): disco en un slot NUEVO = equipado por el latch
    (certero) → asigna conf 1.0 + cosecha el badge, sin depender del sim."""
    from app.core.monitor import _S17_OWNER_MIN_SAMPLES
    m = _monitor_badge(monkeypatch, sim=None, owner=None)
    m._s17_last_slot = 0                       # slot 1 será "nuevo" → equipado
    m._s17_owner_passes = _S17_OWNER_MIN_SAMPLES  # warmup ya corrió, sin voto del badge → trust anchor
    disc = _disc(slot=1)
    m._assign_s17_pj(disc, _frame())
    assert disc.agente_asignado_nombre == "Zhu Yuan"
    assert disc.agente_asignado_conf == 1.0
    assert "Zhu Yuan" in m._identifier.learned  # cosecha con label certero


def test_monitor_equipado_sin_badge_igual_asigna(monkeypatch):
    """El equipado (slot nuevo) se asigna al latch AUNQUE el badge no se localice —
    la estructura del juego lo garantiza (a prueba del crop)."""
    import app.core.monitor as mon
    monkeypatch.setattr(mon, "crop_grid_selected_badge", lambda f: None)
    m = _monitor()
    m._identifier = _StubIdent()
    m._last_agent_name = "Zhu Yuan"
    m._s17_last_slot = 0
    m._s17_owner_passes = mon._S17_OWNER_MIN_SAMPLES  # warmup ya corrió → trust anchor
    disc = _disc(slot=2)
    m._assign_s17_pj(disc, _frame())
    assert disc.agente_asignado_nombre == "Zhu Yuan"
    assert disc.agente_asignado_conf == 1.0


def test_monitor_candidato_del_latch_reconfirma(monkeypatch):
    """Mismo slot + badge que matchea el latch (volviste al equipado) → re-confirma."""
    m = _monitor_badge(monkeypatch, sim=0.95, owner=("Zhu Yuan", 0.95))
    m._s17_last_slot = 1                       # mismo slot → candidato
    disc = _disc(slot=1)
    m._assign_s17_pj(disc, _frame())
    assert disc.agente_asignado_nombre == "Zhu Yuan"
    assert disc.agente_asignado_conf == 0.95


def test_monitor_candidato_de_otro_pj_reporta_no_asigna(monkeypatch):
    """Mismo slot + badge de OTRO PJ (sim<guarda) → reporta el dueño VOTADO pero NO lo
    asigna al latch (no corrompe la build con un disco ajeno — RNF-02)."""
    m = _monitor_badge(monkeypatch, sim=0.40, owner=("Ellen", 0.93))
    m._s17_last_slot = 1
    disc = _disc(slot=1)
    m._sample_s17_owner(_frame())                    # loop rápido acumula el voto
    m._assign_s17_pj(disc, _frame())
    assert disc.agente_asignado_nombre is None       # NO asignado al latch
    assert disc.equip_pj_visual == "Ellen"           # dueño votado reportado


def test_monitor_candidato_incierto_abstiene(monkeypatch):
    """Mismo slot + avatar VISIBLE (el detalle lo ve) pero bajo guard → 'dueño incierto',
    NO libre, sin asignar. 5R.L.7.3: 'avatar visible' = detalle presente (la superficie
    confiable); con un avatar real que no se identifica → incierto, nunca falso-libre."""
    import numpy as np
    import app.core.monitor as mon
    monkeypatch.setattr(mon, "crop_grid_selected_badge",
                        lambda f: np.zeros((40, 40, 3), np.uint8))   # grid ve algo, no matchea
    monkeypatch.setattr(mon, "crop_detail_badge",
                        lambda f: np.zeros((40, 40, 3), np.uint8))   # el DETALLE ve un avatar
    m = _monitor()
    m._identifier = _StubIdent(sim=0.40, owner=None, det_owner=None)  # ninguno identifica al PJ
    m._last_agent_name = "Zhu Yuan"
    m._s17_last_slot = 1
    disc = _disc(slot=1)
    for _ in range(3):
        m._sample_s17_owner(_frame())                # avatar presente, sin ID
    m._assign_s17_pj(disc, _frame())
    assert disc.agente_asignado_nombre is None
    assert disc.equip_pj_visual is None
    assert disc.equip_libre is False                 # detalle vio avatar → no libre, incierto


def test_monitor_disco_libre_consistente(monkeypatch):
    """5R.L.7.3: ÁRBITRO DE PRESENCIA. Disco libre = ninguna superficie ve avatar
    (grid gateado a None por L.7.2 + detalle None) en ≥2 frames → LIBRE. Desacoplado
    de la identidad (no depende de que el matcher rechace)."""
    import numpy as np
    import app.core.monitor as mon
    monkeypatch.setattr(mon, "crop_grid_selected_badge", lambda f: None)   # gate: sin avatar
    monkeypatch.setattr(mon, "crop_detail_badge", lambda f: None)          # detalle: sin avatar
    m = _monitor()
    m._identifier = _StubIdent(sim=0.40, owner=None, free=True)
    m._last_agent_name = "Zhu Yuan"
    m._s17_last_slot = 1
    disc = _disc(slot=1)
    for _ in range(4):
        m._sample_s17_owner(_frame())
    m._assign_s17_pj(disc, _frame())
    assert disc.equip_libre is True
    assert disc.equip_pj_visual is None
    assert disc.agente_asignado_nombre is None


def test_monitor_un_frame_sin_avatar_ya_es_libre(monkeypatch):
    """LIBRE gana a 'incierto' (decisión usuario 2026-06-21): un frame sin avatar y SIN voto
    YA es LIBRE — los matchers son robustos, 'nadie votó' ⇒ sin dueño. (Antes exigía ≥2
    frames → parpadeo LIBRE↔incierto navegando rápido.)"""
    import app.core.monitor as mon
    monkeypatch.setattr(mon, "crop_grid_selected_badge", lambda f: None)
    monkeypatch.setattr(mon, "crop_detail_badge", lambda f: None)
    m = _monitor()
    m._identifier = _StubIdent(sim=0.40, owner=None, free=True)
    m._last_agent_name = "Zhu Yuan"
    m._s17_last_slot = 1
    disc = _disc(slot=1)
    m._sample_s17_owner(_frame())                    # 1 frame sin avatar, sin voto
    m._assign_s17_pj(disc, _frame())
    assert disc.equip_libre is True                  # sin voto → LIBRE (no 'incierto')


def test_monitor_detalle_ve_avatar_no_declara_libre(monkeypatch):
    """5R.L.7.3 (guard Lycaon/RNF-02): si el DETALLE ve un avatar (aunque el matcher no
    lo identifique) con el grid en NOLOC → NO es libre. La presencia manda: hubo un dueño
    visible → 'incierto', nunca falso-libre."""
    import numpy as np
    import app.core.monitor as mon
    monkeypatch.setattr(mon, "crop_grid_selected_badge", lambda f: None)            # grid NOLOC
    monkeypatch.setattr(mon, "crop_detail_badge",
                        lambda f: np.zeros((40, 40, 3), np.uint8))                  # detalle CON avatar
    m = _monitor()
    m._identifier = _StubIdent(sim=0.40, owner=None, det_owner=None)   # detalle no resuelve PJ
    m._last_agent_name = "Zhu Yuan"
    m._s17_last_slot = 1
    disc = _disc(slot=1)
    for _ in range(4):
        m._sample_s17_owner(_frame())
    m._assign_s17_pj(disc, _frame())
    assert disc.equip_libre is False                 # detalle vio avatar → no libre
    assert disc.equip_pj_visual is None              # pero el matcher no lo identificó → incierto


def test_monitor_grid_presente_leaky_sin_voto_igual_libre(monkeypatch):
    """5R.L.7.3 (QA 2026-06-20): la esquina del tile LIBRE pasa el gate del grid (barra
    'Nivel' amarilla + arte → hough+blob) aunque NO sea una cara y el matcher se abstenga
    (sin voto). El ÁRBITRO POR EL DETALLE manda: detalle ausente ≥2 + sin votos → LIBRE,
    PESE a la presencia espuria del grid. (Antes grid_present>0 bloqueaba → 'no detectado'.)"""
    import numpy as np
    import app.core.monitor as mon
    monkeypatch.setattr(mon, "crop_grid_selected_badge",
                        lambda f: np.zeros((40, 40, 3), np.uint8))   # grid leaky: crop presente
    monkeypatch.setattr(mon, "crop_detail_badge", lambda f: None)    # detalle: sin avatar (libre)
    m = _monitor()
    m._identifier = _StubIdent(sim=0.40, owner=None, free=False)      # s17_match → (None, 0.70, no-reject): SIN voto
    m._last_agent_name = "Zhu Yuan"
    m._s17_last_slot = 1                              # mismo slot → candidato (grid presente)
    disc = _disc(slot=1)
    for _ in range(4):
        m._sample_s17_owner(_frame())
    assert m._s17_grid_present > 0 and not m._s17_grid_votes   # grid presente pero sin voto
    m._assign_s17_pj(disc, _frame())
    assert disc.equip_libre is True                  # el detalle arbitra → LIBRE
    assert disc.equip_pj_visual is None
    assert disc.agente_asignado_nombre is None


def test_monitor_detalle_espurio_texto_no_bloquea_libre(monkeypatch):
    """5R.L.7.3 (QA 2026-06-20, Metal colmilludo): el localizador del detalle a veces recorta
    el texto '(N)' del nº de slot en discos LIBRES (det_loc>0 pero conf 0.66 + margen 0.02 =
    equidistante = no es cara). Ese crop espurio NO debe contar como avatar presente → no
    bloquea LIBRE. (Antes: det_loc>0 → 'badge no localizado'/incierto.)"""
    import app.core.monitor as mon
    monkeypatch.setattr(mon, "crop_grid_selected_badge", lambda f: None)             # grid NOLOC
    monkeypatch.setattr(mon, "crop_detail_badge", lambda f: np.zeros((40, 40, 3), np.uint8))  # detalle recorta algo
    m = _monitor()
    m._identifier = _StubIdent(sim=0.40, owner=None, det_owner=None,
                               det_conf=0.66, det_margin=0.02)   # crop espurio: ambos bajos
    m._last_agent_name = "Zhu Yuan"
    m._s17_last_slot = 1
    disc = _disc(slot=1)
    for _ in range(4):
        m._sample_s17_owner(_frame())
    assert m._s17_detail_present == 0 and m._s17_detail_absent >= 2   # texto → ausente
    m._assign_s17_pj(disc, _frame())
    assert disc.equip_libre is True                  # crop espurio no bloquea → LIBRE
    assert disc.equip_pj_visual is None


def test_s17_is_libre_libre_gana_salvo_presencia_dominante(monkeypatch):
    """LIBRE gana a 'incierto' (usuario 2026-06-21): sin voto → LIBRE salvo que el detalle
    vea un avatar REAL de forma DOMINANTE (present ≥ 2× absent). Tolera spikes espurios del
    texto '(N)' (no dominantes) y no exige acumular frames."""
    import numpy as np
    import app.core.monitor as mon
    monkeypatch.setattr(mon, "_s17_disc_signature", lambda self, f: (1, 2, 3), raising=False)
    m = _monitor()
    sig = (np.zeros((48, 24), np.float32), np.zeros((48, 48), np.float32), np.zeros((24, 24), np.float32))
    monkeypatch.setattr(m, "_s17_disc_signature", lambda frame: sig)
    m._s17_owner_sig = sig
    # Sin evidencia (0/0) → LIBRE (no exige 2 frames).
    m._s17_detail_present, m._s17_detail_absent = 0, 0
    assert m._s17_is_libre(_frame()) is True
    # 1 spike presente vs 1 ausente → no dominante → LIBRE.
    m._s17_detail_present, m._s17_detail_absent = 1, 1
    assert m._s17_is_libre(_frame()) is True
    # presencia DOMINANTE (4 presentes vs 1 ausente = avatar real sin nombrar) → no libre.
    m._s17_detail_present, m._s17_detail_absent = 4, 1
    assert m._s17_is_libre(_frame()) is False


_FREE_DIR = (REPO / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers"
             / "17_Inventario_Disco_Vista_Individual_libres")


@pytest.mark.skipif(not _FREE_DIR.is_dir() or not any(_FREE_DIR.glob("*.png")),
                    reason="capturas de discos libres no presentes")
def test_s17_discos_libres_reales_son_libre():
    """Regresión sobre los discos LIBRES reales (carpeta 17, ampliada en QA 2026-06-21):
    con 1 sample (peor caso, navegación rápida) cada uno debe dar is_libre=True — sin
    parpadeo LIBRE↔incierto. Requiere la librería runtime; se saltea si no carga."""
    import glob
    import app.core.monitor as mon
    from app.core.agent_identifier import AgentIdentifier
    ident = AgentIdentifier()
    for fp in sorted(glob.glob(str(_FREE_DIR / "*.png"))):
        frame = cv2.imdecode(np.fromfile(fp, dtype=np.uint8), cv2.IMREAD_COLOR)
        m = mon.Monitor(ocr=None, detector=None)
        m._identifier = ident
        m._last_agent_name = "Nicole"
        m._sample_s17_owner(frame)
        assert m._s17_is_libre(frame) is True, f"{Path(fp).name}: deberia ser LIBRE con 1 sample"


def test_monitor_voto_dueno_gana_pese_a_frames_inciertos(monkeypatch):
    """Anti-parpadeo (5R.5c): el loop rápido samplea ~varios frames del MISMO disco;
    aunque algunos den 'incierto' (recorte movido), el dueño con más confianza
    acumulada gana → lectura estable, no el frame azaroso que tocó la cadencia."""
    import numpy as np
    import app.core.monitor as mon
    monkeypatch.setattr(mon, "crop_grid_selected_badge",
                        lambda f: np.zeros((40, 40, 3), np.uint8))

    class _Flicker:
        """Alterna incierto/Yuzuha frame a frame (como el recorte real)."""
        def __init__(self): self._i = 0; self.learned = []
        def s17_similarity(self, badge, name): return 0.40   # no es el latch
        def s17_match(self, badge, min_sim=0.80):
            self._i += 1
            # frames pares: Yuzuha nítido; impares: cara presente pero bajo guard (no libre)
            return ("Yuzuha", 0.90, False) if self._i % 2 == 0 else (None, 0.70, False)
        def s17_match_detail(self, badge, min_sim=0.80): return None, 0.0, 0.0, False
        def learn_s17(self, badge, name): self.learned.append(name); return True
        def learn_s17_detail(self, badge, name): return True

    m = _monitor()
    m._identifier = _Flicker()
    m._last_agent_name = "Nangong Yu"
    m._s17_last_slot = 1                              # mismo slot → candidato
    for _ in range(8):                               # 8 frames: 4 Yuzuha, 4 incierto
        m._sample_s17_owner(_frame())
    disc = _disc(slot=1)
    m._assign_s17_pj(disc, _frame())
    assert disc.equip_pj_visual == "Yuzuha"          # gana el voto, no el parpadeo
    assert disc.agente_asignado_nombre is None        # candidato: no asigna al latch


def test_monitor_voto_se_resetea_al_cambiar_disco(monkeypatch):
    """Al cambiar de disco (firma distinta) la votación arranca limpia: el dueño del
    disco anterior NO se arrastra al nuevo."""
    import numpy as np
    import app.core.monitor as mon
    monkeypatch.setattr(mon, "crop_grid_selected_badge",
                        lambda f: np.zeros((40, 40, 3), np.uint8))
    m = _monitor_badge(monkeypatch, sim=0.40, owner=("Ellen", 0.93))
    m._sample_s17_owner(_frame())
    assert m._s17_voted_owner(_frame()) == "Ellen"
    # Firma distinta = disco nuevo → reset de votos
    other = np.full((720, 1280, 3), 200, np.uint8)
    assert m._s17_voted_owner(other) is None


def test_monitor_sin_badge_mismo_slot_no_asigna(monkeypatch):
    """Mismo slot (candidato) sin badge → sin asignar (no es el equipado)."""
    import app.core.monitor as mon
    monkeypatch.setattr(mon, "crop_grid_selected_badge", lambda f: None)
    m = _monitor()
    m._identifier = _StubIdent()
    m._last_agent_name = "Zhu Yuan"
    m._s17_last_slot = 1
    disc = _disc(slot=1)
    m._assign_s17_pj(disc, _frame())
    assert disc.agente_asignado_nombre is None
    assert disc.equip_detectado is False


def test_identifier_learn_valida_y_canonicaliza_por_roster(tmp_path):
    """Fase 4: learn_s17 rechaza nombres fuera del roster ('Permiso') y canonicaliza
    el OCR sin tilde ('Lucia'→'Lucía')."""
    import numpy as np
    from app.core.agent_identifier import AgentIdentifier
    ident = AgentIdentifier(library_path=tmp_path / "lib.npz", autoload=False,
                            roster={"Nangong Yu", "Lucía"})
    face = np.full((48, 48, 3), 127, np.uint8)
    assert ident.learn_s17(face, "Permiso") is False        # fuera del roster
    assert "Permiso" not in ident.names_s17
    assert ident.learn_s17(face, "Lucia") is True            # OCR sin tilde
    assert "Lucía" in ident.names_s17                        # canonicalizado


def test_learn_s17_readonly_gateado_por_badge_harvest(tmp_path, monkeypatch):
    """En readonly, learn_s17 NO persiste — salvo en modo cosecha de badges
    (DANIBOD_BADGE_HARVEST), que escribe la librería de badges sin tocar la DB."""
    import numpy as np
    import app.core.agent_identifier as ai
    monkeypatch.setattr(ai, "is_readonly", lambda: True)
    face = np.full((48, 48, 3), 127, np.uint8)
    ident = ai.AgentIdentifier(library_path=tmp_path / "lib.npz", autoload=False,
                               roster={"Nangong Yu"})
    monkeypatch.delenv("DANIBOD_BADGE_HARVEST", raising=False)
    assert ident.learn_s17(face, "Nangong Yu") is False       # readonly puro → inerte
    monkeypatch.setenv("DANIBOD_BADGE_HARVEST", "1")
    assert ident.learn_s17(face, "Nangong Yu") is True        # modo cosecha → persiste
    assert "Nangong Yu" in ident.names_s17


def test_identifier_prune_to_roster(tmp_path):
    """Fase 5R: prune_to_roster quita refs espurias de ambos matchers (protege -ico)."""
    import numpy as np
    from app.core.agent_identifier import AgentIdentifier
    from app.core.avatar_descriptor import AvatarDescriptor
    ident = AgentIdentifier(library_path=tmp_path / "lib.npz", autoload=False,
                            roster={"Nangong Yu"})
    def d():
        return [AvatarDescriptor(np.zeros(192, np.float32), np.zeros(10, np.float32),
                                 np.zeros(9, np.float32), np.zeros(10, np.float32), False)]
    ident._row._refs = {"Nangong Yu": d(), "Permiso": d()}
    ident._badge._refs = {"Nangong Yu": d(), "Sporos_bogus": d()}
    assert ident.prune_to_roster() == 2
    assert ident.names == ["Nangong Yu"] and ident.names_s17 == ["Nangong Yu"]


def test_crop_detail_badge_localiza_y_none():
    """5R.C.4: crop_detail_badge encuentra el blob saturado en la franja del detalle
    (robusto a resolución por regiones fraccionales) y devuelve None si no hay avatar."""
    import numpy as np
    import cv2
    from app.core.detector import crop_detail_badge
    H, W = 720, 1280
    frame = np.zeros((H, W, 3), np.uint8)              # fondo oscuro (header)
    # avatar saturado en la franja del detalle: centro ~ (0.495 W, 0.19 H)
    cv2.circle(frame, (int(0.495 * W), int(0.19 * H)), 16, (40, 60, 220), -1)  # rojo saturado
    crop = crop_detail_badge(frame)
    assert crop is not None and crop.size > 0
    # sin avatar (todo oscuro) → None
    assert crop_detail_badge(np.zeros((H, W, 3), np.uint8)) is None


def test_learn_s17_detail_readonly_gateado_por_badge_harvest(tmp_path, monkeypatch):
    """En readonly, learn_s17_detail NO persiste salvo en cosecha de badges
    (DANIBOD_BADGE_HARVEST) — mismo gating que learn_s17, librería propia de detalle."""
    import numpy as np
    import app.core.agent_identifier as ai
    monkeypatch.setattr(ai, "is_readonly", lambda: True)
    face = np.full((48, 48, 3), 127, np.uint8)
    ident = ai.AgentIdentifier(library_path=tmp_path / "lib.npz", autoload=False,
                               roster={"Nangong Yu"})
    monkeypatch.delenv("DANIBOD_BADGE_HARVEST", raising=False)
    assert ident.learn_s17_detail(face, "Nangong Yu") is False      # readonly puro → inerte
    monkeypatch.setenv("DANIBOD_BADGE_HARVEST", "1")
    assert ident.learn_s17_detail(face, "Nangong Yu") is True       # cosecha → persiste
    assert "Nangong Yu" in ident._detbadge._refs


def test_monitor_voto_detalle_suma_dueno_aunque_grid_falle(monkeypatch):
    """5R.C.4: el detalle-badge vota al MISMO acumulador. Si el grid da NOLOC pero el
    detalle localiza e identifica, el dueño se acumula igual (sube el yield del voto)."""
    import numpy as np
    import app.core.monitor as mon
    monkeypatch.setattr(mon, "crop_grid_selected_badge", lambda f: None)        # grid NOLOC
    monkeypatch.setattr(mon, "crop_detail_badge", lambda f: np.zeros((40, 40, 3), np.uint8))
    m = _monitor()
    m._identifier = _StubIdent(det_owner=("Yuzuha", 0.90))
    for _ in range(3):
        m._sample_s17_owner(_frame())
    assert m._s17_voted_owner(_frame()) == "Yuzuha"


def test_retroceso_s17_a_s8_hereda_pj(monkeypatch):
    """Fase 4: al volver de S17 (detalle disco) a S8 (hexágono) se HEREDA el PJ —
    se re-ancla el latch y NO se re-identifica por avatar (sería el mismo PJ)."""
    import numpy as np
    from app.core.detector import ScreenState
    m = _monitor()
    m._last_agent_name = "Burnice"
    m._agent_anchor_x = None
    m._detail_source = "avatar"
    m._prev_state_code = "S17"  # venimos del detalle del disco
    monkeypatch.setattr("app.core.monitor.selected_avatar_x", lambda f: 0.123)
    # si NO se heredara, el matcher cambiaría el latch a 'OtroPJ'
    monkeypatch.setattr(m._identifier, "identify", lambda f: ("OtroPJ", 0.99))
    monkeypatch.setattr(m, "_process_agent_detail_continuous", lambda f, s: None)
    monkeypatch.setattr(m, "_handle_upgrade", lambda f, s, p=None: None)
    m._last_detail_sig = ("S8", "Burnice", True, "avatar")  # firma previa (no cambiaría)
    m._dispatch_state(np.zeros((1440, 2560, 3), np.uint8), ScreenState("S8", 0.9, "tmpl"))
    assert m._agent_anchor_x == 0.123      # re-anclado a la posición actual
    assert m._last_agent_name == "Burnice"  # latch preservado (no 'OtroPJ')
    assert m._last_detail_sig is None       # re-emite (feedback al retroceder)


def test_monitor_sin_latch_no_asigna():
    fr, ln, W, H = _load_frame_lines("Ejemplo_1")
    m = _monitor()
    m._last_agent_name = None
    disc = _disc()
    m._assign_s17_pj(disc, crop_s17_assigned_avatar(fr, ln, W, H))
    assert disc.agente_asignado_nombre is None


def test_monitor_candidato_sin_badge_no_asigna(monkeypatch):
    """Candidato (mismo slot) sin badge localizado → no asigna (no es el equipado)."""
    import app.core.monitor as mon
    monkeypatch.setattr(mon, "crop_grid_selected_badge", lambda f: None)
    m = _monitor()
    m._last_agent_name = "Zhu Yuan"
    m._s17_last_slot = 1                       # mismo slot → candidato, no equipado
    disc = _disc(slot=1)
    m._assign_s17_pj(disc, _frame())
    assert disc.agente_asignado_nombre is None


# --- 5. Persistencia enfocada S17 (DiscSyncer.persist_s17_disc) --------------

@pytest.fixture
def syncer_db(tmp_path):
    """DB de archivo con el esquema mínimo que toca persist_s17_disc."""
    path = tmp_path / "s17.db"
    con = sqlite3.connect(str(path))
    con.executescript("""
        CREATE TABLE disc_archetypes (id INTEGER PRIMARY KEY, code TEXT UNIQUE);
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY, nombre TEXT UNIQUE, rol TEXT DEFAULT 'Ataque',
            set_4p_id INTEGER, set_2p_id INTEGER, protected_build INTEGER DEFAULT 0
        );
        CREATE TABLE agent_score_thresholds (
            id INTEGER PRIMARY KEY AUTOINCREMENT, agente_id INTEGER,
            threshold_equip REAL DEFAULT 0.75, threshold_upgrade REAL DEFAULT 0.50
        );
        CREATE TABLE agent_substat_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT, agente_id INTEGER, substat TEXT, peso REAL
        );
        CREATE TABLE disc_sets (
            id INTEGER PRIMARY KEY, nombre TEXT UNIQUE, nombre_en TEXT,
            bonus_2p_stat TEXT, bonus_2p_valor TEXT, bonus_4p_desc TEXT
        );
        CREATE TABLE disc_set_archetype (set_id INTEGER, archetype_id INTEGER, prioridad INTEGER DEFAULT 1);
        CREATE TABLE inventory_discs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            set_id INTEGER, slot INTEGER NOT NULL,
            main_stat TEXT, main_valor REAL, unidad_main TEXT,
            sub1 TEXT, val1 REAL, rolls1 INTEGER DEFAULT 0, unidad1 TEXT,
            sub2 TEXT, val2 REAL, rolls2 INTEGER DEFAULT 0, unidad2 TEXT,
            sub3 TEXT, val3 REAL, rolls3 INTEGER DEFAULT 0, unidad3 TEXT,
            sub4 TEXT, val4 REAL, rolls4 INTEGER DEFAULT 0, unidad4 TEXT,
            nivel INTEGER DEFAULT 0, equipado INTEGER DEFAULT 0,
            agente_asignado INTEGER, descartado INTEGER DEFAULT 0,
            score_evaluacion REAL, agentes_compatibles TEXT, notas TEXT
        );
        INSERT INTO disc_archetypes VALUES (1, 'ATK_DPS');
        INSERT INTO disc_sets VALUES (1, 'Jazz caótico', 'Chaotic Jazz', 'Maestría de Anomalía', '+30', 'Al golpear...');
        INSERT INTO agents (id, nombre, rol) VALUES (7, 'Zhu Yuan', 'Ataque');
        INSERT INTO agent_score_thresholds (agente_id) VALUES (7);
    """)
    con.commit()
    con.close()
    return path


def _make_syncer(path):
    from app.core.sync_equip import DiscSyncer
    return DiscSyncer(db_path=path)


def test_persist_s17_inserta_con_asignacion(syncer_db):
    sync = _make_syncer(syncer_db)
    try:
        disc = _disc()
        disc.agente_asignado_nombre = "Zhu Yuan"
        disc.agente_asignado_conf = 0.95
        res = sync.persist_s17_disc(disc)
        assert res is not None and res.agente_asignado_nombre == "Zhu Yuan"
        assert res.set_bonus_2p == "Maestría de Anomalía +30"  # item #3 desde DB
        con = sqlite3.connect(str(syncer_db)); con.row_factory = sqlite3.Row
        r = con.execute("SELECT agente_asignado, equipado FROM inventory_discs WHERE id=?", (res.disc_id,)).fetchone()
        assert r["agente_asignado"] == 7 and r["equipado"] == 1
        con.close()
    finally:
        sync.close()


def test_persist_s17_sin_pj_confiable_no_persiste(syncer_db):
    """
    Sin PJ confiable NO se persiste: el disco S17 está equipado en algún PJ y sin
    saber cuál, cualquier match por firma colisiona con discos de otros PJs.
    """
    sync = _make_syncer(syncer_db)
    try:
        res = sync.persist_s17_disc(_disc())  # sin agente_asignado_nombre
        assert res is None
        con = sqlite3.connect(str(syncer_db)); con.row_factory = sqlite3.Row
        n = con.execute("SELECT COUNT(*) c FROM inventory_discs").fetchone()["c"]
        assert n == 0, "no debe insertar nada sin PJ confiable"
        con.close()
    finally:
        sync.close()


def test_persist_s17_no_colisiona_entre_pjs(syncer_db):
    """
    Regresión del bug de corrupción (2026-06-06): dos PJs con la MISMA firma
    (set+slot+main+mainval) — capturar el disco del PJ B no debe tocar el del PJ A.
    Antes find_by_hash devolvía el disco de A (id más bajo) y le pisaba los stats.
    """
    sync = _make_syncer(syncer_db)
    try:
        con = sqlite3.connect(str(syncer_db)); con.row_factory = sqlite3.Row
        con.execute("INSERT INTO agents (id, nombre, rol) VALUES (8, 'Otro PJ', 'Ataque')")
        # Disco de A (Zhu Yuan, id agente 7): Jazz slot1, HP 2200, substat propio.
        con.execute(
            "INSERT INTO inventory_discs (id, set_id, slot, main_stat, main_valor, "
            "sub1, val1, rolls1, nivel, equipado, agente_asignado, descartado) "
            "VALUES (100, 1, 1, 'HP', 2200.0, 'Daño Crítico', 9.6, 1, 15, 1, 7, 0)"
        )
        con.commit(); con.close()

        # Capturo el disco de B (Otro PJ): MISMA firma, substat distinto.
        d = _disc(slot=1)  # Jazz, HP 2200
        d.subs = [SubstatParsed("ATK", "ATK", 38.0, "flat", 1, 0.95)]
        d.agente_asignado_nombre = "Otro PJ"; d.agente_asignado_conf = 0.95
        res = sync.persist_s17_disc(d)
        assert res is not None and res.disc_id != 100, "no debe matchear el disco de A"

        con = sqlite3.connect(str(syncer_db)); con.row_factory = sqlite3.Row
        a = con.execute("SELECT sub1, val1, agente_asignado FROM inventory_discs WHERE id=100").fetchone()
        assert a["sub1"] == "Daño Crítico" and a["val1"] == 9.6, "el disco de A fue pisado"
        assert a["agente_asignado"] == 7, "el disco de A fue robado"
        b = con.execute("SELECT agente_asignado, equipado FROM inventory_discs WHERE id=?", (res.disc_id,)).fetchone()
        assert b["agente_asignado"] == 8 and b["equipado"] == 1
        con.close()
    finally:
        sync.close()


def test_persist_s17_update_mismo_pj_slot(syncer_db):
    """Re-captura del mismo PJ+slot actualiza ESE disco (no crea duplicado)."""
    sync = _make_syncer(syncer_db)
    try:
        d1 = _disc(slot=1); d1.agente_asignado_nombre = "Zhu Yuan"; d1.agente_asignado_conf = 0.95
        res1 = sync.persist_s17_disc(d1)
        d2 = _disc(slot=1); d2.nivel = 15
        d2.subs = [SubstatParsed("Daño Crítico", "Daño Crítico", 12.0, "%", 2, 0.95)]
        d2.agente_asignado_nombre = "Zhu Yuan"; d2.agente_asignado_conf = 0.95
        res2 = sync.persist_s17_disc(d2)
        assert res2.disc_id == res1.disc_id, "debe actualizar el mismo disco, no duplicar"
        con = sqlite3.connect(str(syncer_db)); con.row_factory = sqlite3.Row
        n = con.execute("SELECT COUNT(*) c FROM inventory_discs WHERE agente_asignado=7 AND slot=1 AND equipado=1").fetchone()["c"]
        assert n == 1, "un PJ tiene un solo disco equipado por slot"
        con.close()
    finally:
        sync.close()


def test_persist_s17_cross_thread(syncer_db):
    """
    Regresión: el DiscSyncer se crea en un thread (UI) y persist_s17_disc corre en
    otro (monitor). check_same_thread=False debe permitirlo sin lanzar
    'SQLite objects created in a thread can only be used in that same thread'.
    """
    import threading
    sync = _make_syncer(syncer_db)  # creado en este thread
    out = {}
    def work():
        try:
            d = _disc()
            d.agente_asignado_nombre = "Zhu Yuan"; d.agente_asignado_conf = 0.95
            out["res"] = sync.persist_s17_disc(d)
        except Exception as exc:  # noqa: BLE001
            out["err"] = exc
    t = threading.Thread(target=work)
    t.start(); t.join()
    sync.close()
    assert "err" not in out, f"persist falló cross-thread: {out.get('err')}"
    assert out["res"] is not None and out["res"].agente_asignado_nombre == "Zhu Yuan"


def _band_frame(val):
    """Frame BGR con la banda de detalle S17 (x[0.30,0.52], y[0.10,0.55]) en `val`."""
    import numpy as np
    f = np.zeros((1440, 2560, 3), dtype=np.uint8)
    f[int(0.10 * 1440):int(0.55 * 1440), int(0.30 * 2560):int(0.52 * 2560)] = val
    return f


def test_s17_firma_detecta_cambio_de_disco():
    """
    La firma híbrida gobierna el RESET del aggregator (Fase 1): mismo disco → no es
    nuevo; otra firma (otro disco/slot) → es nuevo. Cubre el modo visualización.
    """
    m = _monitor()
    fA, fB = _band_frame(50), _band_frame(200)
    sigA, sigB = m._s17_disc_signature(fA), m._s17_disc_signature(fB)
    assert m._is_new_s17_disc(sigA)        # sin ancla → todo es nuevo
    m._disc_agg_sig = sigA
    assert not m._is_new_s17_disc(sigA)    # mismo disco
    assert m._is_new_s17_disc(sigB)        # otro disco


def test_s17_firma_distingue_set_por_nombre():
    """QA 2026-06-20: dos discos del MISMO slot (candidatos) con detail+hex IDÉNTICOS pero
    SET distinto se separan por el TÍTULO. Antes colisionaban (Monarca↔Nana, ambos main
    HP 2200, mismo hex) → el 2º no se re-detectaba. El título no estaba en la firma."""
    m = _monitor()
    base = np.full((1440, 2560, 3), 30, np.uint8)
    fa = base.copy()
    fb = base.copy()
    # Solo difiere la región del TÍTULO del set (y∈[0.05,0.19], x∈[0.31,0.58]).
    fb[int(0.05 * 1440):int(0.19 * 1440), int(0.31 * 2560):int(0.58 * 2560)] = 220
    sa, sb = m._s17_disc_signature(fa), m._s17_disc_signature(fb)
    assert m._sig_close(sa, sa)
    assert not m._sig_close(sa, sb), "distinto set (título) debe verse como disco distinto"


_SLOTS_DIR = REPO / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers" / "14_Slots_equipamiento"


def test_crop_grid_selected_badge_localiza_en_s17():
    """5R.4: el localizador de badge del tile seleccionado devuelve un crop en una
    pantalla de grilla S17, y None sin grilla."""
    from app.core.detector import crop_grid_selected_badge
    f = cv2.imread(str(_SLOTS_DIR / "Ejemplo_Slot1_1.png"))
    if f is None:
        pytest.skip("captura Slot1_1 no encontrada")
    badge = crop_grid_selected_badge(f)
    assert badge is not None and badge.size > 0
    h, w = badge.shape[:2]
    assert 0.7 < h / w < 1.4              # aprox cuadrado (círculo inscripto)
    assert crop_grid_selected_badge(np.zeros((720, 1280, 3), np.uint8)) is None


@pytest.mark.parametrize("a,b", [
    ("Ejemplo_Slot4_1", "Ejemplo_Slot5_1"),   # adyacentes, MISMO set (Melodía) — el caso que fallaba
    ("Ejemplo_Slot5_1", "Ejemplo_Slot6_1"),
    ("Ejemplo_Slot2_1", "Ejemplo_Slot3_1"),
])
def test_s17_firma_distingue_slots_mismo_set_adyacentes(a, b):
    """
    Regresión QA 2026-06-07: dos slots ADYACENTES del MISMO set se ven como discos
    DISTINTOS (firma híbrida) → el aggregator se resetea al navegar. La firma 12×12
    vieja no los distinguía. Usa capturas reales.
    """
    fa = cv2.imread(str(_SLOTS_DIR / f"{a}.png"))
    fb = cv2.imread(str(_SLOTS_DIR / f"{b}.png"))
    if fa is None or fb is None:
        pytest.skip(f"captura no encontrada: {a}/{b}")
    m = _monitor()
    sa, sb = m._s17_disc_signature(fa), m._s17_disc_signature(fb)
    assert m._sig_close(sa, sa), "el mismo frame debe verse como el mismo disco"
    assert not m._sig_close(sa, sb), f"{a}→{b} (mismo set) deben verse como discos distintos"


def test_maybe_process_disc_s17_va_al_handler_continuo(monkeypatch):
    """S17 enruta al handler CONTINUO (Fase 1), no al one-shot _process_disc."""
    from app.core.detector import ScreenState
    m = _monitor()
    calls = []
    monkeypatch.setattr(m, "_process_disc_s17_continuous", lambda frame, st: calls.append(st.code))
    m._maybe_process_disc(None, ScreenState("S17", 1.0, "tmpl"))
    assert calls == ["S17"]


# --- 5d. DiscAggregator + S17 continuo (Fase 1) ------------------------------

def _sub(nombre, valor, rolls=0, unidad="flat"):
    return SubstatParsed(nombre, nombre, valor, unidad, rolls, 0.95)


def _disc_full(slot=1, set_name="Jazz caótico"):
    """Disco maduro: set+slot+main+4 substats con valor."""
    d = _disc(slot=slot, set_name=set_name)
    d.subs = [_sub("ATK", 38.0, 1), _sub("Daño Crítico", 9.6, 1, "%"),
              _sub("Prob. Crítica", 4.8, 0, "%"), _sub("Maestría de Anomalía", 27.0, 2)]
    return d


def test_disc_is_mature():
    from app.core.parser_disc_s17 import disc_is_mature
    assert disc_is_mature(_disc_full())
    # main sin valor → no maduro
    d = _disc_full(); d.main_valor = None
    assert not disc_is_mature(d)
    # solo 3 substats → no maduro
    d = _disc_full(); d.subs = d.subs[:3]
    assert not disc_is_mature(d)
    # slot inválido (0) → no maduro
    d = _disc_full(); d.slot = 0
    assert not disc_is_mature(d)


def test_disc_aggregator_converge_parciales():
    """Fusiona parciales del mismo disco: un valor leído en un frame se conserva
    aunque el siguiente lo lea None; converge a completo."""
    from app.core.parser_disc_s17 import DiscAggregator, disc_is_mature
    agg = DiscAggregator()
    # Frame 1: main OK pero 2 substats sin valor.
    d1 = _disc_full()
    d1.subs[1].valor = None
    d1.subs[3].valor = None
    m1 = agg.merge(d1)
    assert not disc_is_mature(m1)
    # Frame 2: main None (se dropea) pero los 2 substats faltantes ahora con valor.
    d2 = _disc_full()
    d2.main_valor = None
    m2 = agg.merge(d2)
    # main se conserva del frame 1; substats completados del frame 2 → maduro.
    assert m2.main_valor is not None
    assert disc_is_mature(m2)


def test_s17_continuo_emite_una_vez_al_madurar(monkeypatch):
    """
    _process_disc_s17_continuous fusiona cada ciclo y emite (_on_disc) UNA sola vez
    al madurar; no re-emite mientras siga el mismo disco; resetea al cambiar de disco.
    """
    from app.core.detector import ScreenState
    import numpy as np
    emitted = []
    m = _monitor()
    m._on_disc = lambda disc, st: emitted.append(disc)
    # Firma estable (mismo disco) y sin avatar.
    sig = (np.zeros((48, 24), np.float32), np.zeros((48, 48), np.float32), np.zeros((24, 24), np.float32))
    monkeypatch.setattr(m, "_s17_disc_signature", lambda frame: sig)
    # 5R.L.6: el real SIEMPRE resuelve el dueño (owner/libre/incierto); acá lo marcamos
    # 'libre' (resuelto) para que emita al madurar sin entrar al warmup del dueño incierto.
    monkeypatch.setattr(m, "_assign_s17_pj", lambda disc, face: setattr(disc, "equip_libre", True))

    seq = iter([_partial := _disc_full(), _disc_full(), _disc_full()])
    _partial.subs[2].valor = None  # frame 1 incompleto
    monkeypatch.setattr("app.core.monitor.parse_disc_s17_full",
                        lambda frame, ocr: (next(seq), None))
    st = ScreenState("S17", 1.0, "tmpl")
    m._process_disc_s17_continuous(None, st)   # frame 1: parcial → no emite
    assert emitted == []
    m._process_disc_s17_continuous(None, st)   # frame 2: completo → emite 1 vez
    assert len(emitted) == 1
    m._process_disc_s17_continuous(None, st)   # frame 3: mismo disco → no re-emite
    assert len(emitted) == 1


def test_s17_warmup_difiere_emision_si_dueno_incierto(monkeypatch):
    """
    5R.L.6: si el disco MADURA pero el dueño quedó INCIERTO (no resuelto), la emisión se
    DIFIERE hasta juntar _S17_OWNER_MIN_SAMPLES pasadas del loop rápido (que vota el badge
    a 10fps, sin re-OCR). Evita cerrar el disco como 'incierto' sobre un único frame ruidoso
    (la grilla localiza ~81%/frame; el detalle se abstiene seguido). Al calentar, emite.
    """
    from app.core.detector import ScreenState
    import numpy as np
    import app.core.monitor as mon
    emitted = []
    m = _monitor()
    m._on_disc = lambda disc, st: emitted.append(disc)
    sig = (np.zeros((48, 24), np.float32), np.zeros((48, 48), np.float32), np.zeros((24, 24), np.float32))
    monkeypatch.setattr(m, "_s17_disc_signature", lambda frame: sig)
    # Dueño SIEMPRE incierto: el stub NO setea equip_* → _s17_owner_resolved False.
    monkeypatch.setattr(m, "_assign_s17_pj", lambda disc, face: None)
    monkeypatch.setattr("app.core.monitor.parse_disc_s17_full",
                        lambda frame, ocr: (_disc_full(), None))
    st = ScreenState("S17", 1.0, "tmpl")
    # Sin pasadas del loop rápido (owner_passes=0): madura pero DIFIERE (no emite, queda warming).
    m._process_disc_s17_continuous(None, st)
    assert emitted == [] and m._s17_warming is True
    # Aún frío: re-chequeo sin re-OCR sigue difiriendo.
    m._s17_owner_passes = mon._S17_OWNER_MIN_SAMPLES - 1
    m._process_disc_s17_continuous(None, st)
    assert emitted == [] and m._s17_warming is True
    # Simular que el loop rápido (10fps) llegó al umbral → emite (incierto, RNF-02 abstención).
    m._s17_owner_passes = mon._S17_OWNER_MIN_SAMPLES
    m._process_disc_s17_continuous(None, st)
    assert len(emitted) == 1 and m._s17_warming is False


def test_s17_confirma_upgrade_aunque_dueno_incierto(monkeypatch):
    """REGRESIÓN (QA 2026-07-14): al volver del popup S20 (vuelto de materiales), el disco maxeado
    viene SIN latch y con badge INCIERTO → la EMISIÓN queda en warming del dueño. La confirmación
    del UPGRADE (resumen PRE→POST) NO debe depender de eso: compara stats, no dueño. Debe disparar
    al MADURAR el disco, aunque `_on_disc` (emisión) se difiera. Antes NO salía nunca el resumen."""
    from app.core.detector import ScreenState
    import numpy as np

    class _SpySyncer:
        def __init__(self):
            self.confirmed = []
        def on_post_upgrade_disc(self, disc):
            self.confirmed.append(disc)

    emitted = []
    m = _monitor()
    m._on_disc = lambda disc, st: emitted.append(disc)
    spy = _SpySyncer()
    m._upgrade_syncer = spy
    sig = (np.zeros((48, 24), np.float32), np.zeros((48, 48), np.float32), np.zeros((24, 24), np.float32))
    monkeypatch.setattr(m, "_s17_disc_signature", lambda frame: sig)
    monkeypatch.setattr(m, "_assign_s17_pj", lambda disc, face: None)   # dueño INCIERTO (no resuelve)
    monkeypatch.setattr("app.core.monitor.parse_disc_s17_full",
                        lambda frame, ocr: (_disc_full(), None))
    st = ScreenState("S17", 1.0, "tmpl")
    m._process_disc_s17_continuous(None, st)
    # La EMISIÓN se difiere (warming por dueño incierto)…
    assert emitted == [] and m._s17_warming is True
    # …pero la CONFIRMACIÓN del upgrade ya disparó al madurar (desacoplada del dueño).
    assert len(spy.confirmed) == 1
    assert (spy.confirmed[0].set_name_canon or spy.confirmed[0].set_name_raw) == "Jazz caótico"


def test_s17_warmup_no_difiere_equipado(monkeypatch):
    """5R.L.6 (no-regresión de latencia): un disco con dueño RESUELTO (equipado/latch o
    votado) emite al madurar SIN esperar warmup — el costo se paga solo en los inciertos."""
    from app.core.detector import ScreenState
    import numpy as np
    emitted = []
    m = _monitor()
    m._on_disc = lambda disc, st: emitted.append(disc)
    sig = (np.zeros((48, 24), np.float32), np.zeros((48, 48), np.float32), np.zeros((24, 24), np.float32))
    monkeypatch.setattr(m, "_s17_disc_signature", lambda frame: sig)
    # Dueño resuelto por latch (equipado): _s17_owner_resolved True → sin warmup.
    monkeypatch.setattr(m, "_assign_s17_pj",
                        lambda disc, face: setattr(disc, "agente_asignado_nombre", "Koleda"))
    monkeypatch.setattr("app.core.monitor.parse_disc_s17_full",
                        lambda frame, ocr: (_disc_full(), None))
    st = ScreenState("S17", 1.0, "tmpl")
    m._process_disc_s17_continuous(None, st)   # owner_passes=0 pero RESUELTO → emite ya
    assert len(emitted) == 1 and m._s17_warming is False


def test_s17_libre_emite_sin_warmup_completo(monkeypatch):
    """5R.L.7.4: un disco LIBRE resuelto por el ÁRBITRO DE PRESENCIA (detalle ausente ≥2,
    grid gateado sin avatar) queda 'resuelto' (equip_libre) y emite al madurar SIN esperar
    las _S17_OWNER_MIN_SAMPLES pasadas de warmup — la latencia se paga solo en los inciertos."""
    from app.core.detector import ScreenState
    import numpy as np
    import app.core.monitor as mon
    monkeypatch.setattr(mon, "crop_grid_selected_badge", lambda f: None)   # gate: sin avatar
    monkeypatch.setattr(mon, "crop_detail_badge", lambda f: None)          # detalle: sin avatar
    emitted = []
    m = _monitor()
    m._on_disc = lambda disc, st: emitted.append(disc)
    m._identifier = _StubIdent(sim=0.40, owner=None)
    m._last_agent_name = "Zhu Yuan"
    m._s17_last_slot = 1                        # mismo slot que el disco → NO anchor (candidato/NOLOC)
    sig = (np.zeros((48, 24), np.float32), np.zeros((48, 48), np.float32), np.zeros((24, 24), np.float32))
    monkeypatch.setattr(m, "_s17_disc_signature", lambda frame: sig)
    monkeypatch.setattr("app.core.monitor.parse_disc_s17_full",
                        lambda frame, ocr: (_disc_full(slot=1), None))
    # El loop rápido (10fps) ya juntó la evidencia de presencia: 2 frames sin avatar.
    m._s17_owner_sig = sig
    m._s17_detail_absent = mon._S17_FREE_MIN_FRAMES
    m._s17_owner_passes = 1                     # < _S17_OWNER_MIN_SAMPLES (no calentó)
    st = ScreenState("S17", 1.0, "tmpl")
    m._process_disc_s17_continuous(None, st)
    assert len(emitted) == 1
    assert emitted[0].equip_libre is True
    assert m._s17_owner_passes < mon._S17_OWNER_MIN_SAMPLES   # emitió sin warmup completo
    assert m._s17_warming is False


def test_s17_continuo_no_re_emite_por_parpadeo_de_firma(monkeypatch):
    """
    Regresión QA 2026-06-07: el modelo 3D del disco tiene animación idle → la firma
    híbrida cruza el umbral en pantalla ESTÁTICA y resetea el aggregator. Sin dedup
    por identidad el MISMO disco quieto se re-emitía ~7×. Con dedup: aunque la firma
    parpadee (fuerza reset cada ciclo), un disco ya emitido NO se re-emite.
    """
    from app.core.detector import ScreenState
    import numpy as np
    emitted = []
    m = _monitor()
    m._on_disc = lambda disc, st: emitted.append(disc)
    # Firma que PARPADEA cruzando el umbral cada ciclo (diff 100 > _S17_SIG_DETAIL_MAX)
    # → _is_new_s17_disc True cada ciclo (peor caso: modelo 3D animado).
    import itertools
    seqsig = itertools.cycle([0.0, 100.0])
    monkeypatch.setattr(
        m, "_s17_disc_signature",
        lambda frame: (np.zeros((48, 24), np.float32),
                       np.full((48, 48), next(seqsig), np.float32), np.zeros((24, 24), np.float32)),
    )
    # 5R.L.6: dueño 'resuelto' (libre) → emite al madurar sin warmup.
    monkeypatch.setattr(m, "_assign_s17_pj", lambda disc, face: setattr(disc, "equip_libre", True))
    monkeypatch.setattr("app.core.monitor.parse_disc_s17_full",
                        lambda frame, ocr: (_disc_full(), None))
    st = ScreenState("S17", 1.0, "tmpl")
    for _ in range(7):
        m._process_disc_s17_continuous(None, st)
    assert len(emitted) == 1, "el mismo disco no debe re-emitirse aunque la firma parpadee"
    # Cambiar de disco (otra identidad) SÍ emite de nuevo.
    monkeypatch.setattr("app.core.monitor.parse_disc_s17_full",
                        lambda frame, ocr: (_disc_full(slot=2), None))
    m._process_disc_s17_continuous(None, st)
    assert len(emitted) == 2
    # Salir de S17 limpia el dedup → re-entrar re-emite.
    m._reset_s17_disc_tracking()
    monkeypatch.setattr("app.core.monitor.parse_disc_s17_full",
                        lambda frame, ocr: (_disc_full(), None))
    m._process_disc_s17_continuous(None, st)
    assert len(emitted) == 3


def test_s17_dedup_identidad_insensible_a_mojibake_de_tilde(monkeypatch):
    """
    Regresión QA Fase 2 (2026-06-08): el OCR del crop lee la tilde del set de forma
    inestable entre ciclos ('Faetón'→'Faeton'). El dedup por identidad normaliza con
    `_norm_key` ⇒ el MISMO disco NO se re-emite aunque varíe el mojibake del nombre.
    """
    from app.core.detector import ScreenState
    import numpy as np
    emitted = []
    m = _monitor()
    m._on_disc = lambda disc, st: emitted.append(disc)
    # firma fija (mismo disco), pero el set cambia de mojibake cada ciclo
    sig = (np.zeros((48, 24), np.float32), np.zeros((48, 48), np.float32), np.zeros((24, 24), np.float32))
    monkeypatch.setattr(m, "_s17_disc_signature", lambda frame: sig)
    # 5R.L.6: dueño 'resuelto' (libre) → emite al madurar sin warmup.
    monkeypatch.setattr(m, "_assign_s17_pj", lambda disc, face: setattr(disc, "equip_libre", True))
    variants = iter(["Melodia de Faetón", "Melodia de Faeton", "Melodia de Faetön"])

    def _parse(frame, ocr):
        d = _disc_full(slot=3, set_name=next(variants))
        return d, None
    monkeypatch.setattr("app.core.monitor.parse_disc_s17_full", _parse)
    st = ScreenState("S17", 1.0, "tmpl")
    for _ in range(3):
        m._disc_agg_sig = None  # firma "parpadea" → reset del aggregator (NO de ids)
        m._process_disc_s17_continuous(None, st)
    assert len(emitted) == 1, "mojibake de la tilde no debe re-emitir el mismo disco"


def test_log_s17_assign_edge_triggered():
    """El log de asignación S17 emite 1× por firma; re-loguea al cambiar de decisión."""
    m = _monitor()
    logs = []
    import app.core.monitor as mon
    orig = mon.log.info
    mon.log.info = lambda msg, *a: logs.append(msg % a if a else msg)
    try:
        m._log_s17_assign(("confirm", "Lucía"), "asig %s", "Lucía")
        m._log_s17_assign(("confirm", "Lucía"), "asig %s", "Lucía")  # misma firma → no
        m._log_s17_assign(("mismatch", "Lucía", "Yixuan"), "mismatch")  # cambia → sí
    finally:
        mon.log.info = orig
    assert logs == ["asig Lucía", "mismatch"]


def test_s17_continuo_baja_confianza_no_contamina(monkeypatch):
    """Un frame con confianza < 0.7 (transición) no se fusiona ni emite."""
    from app.core.detector import ScreenState
    import numpy as np
    emitted = []
    m = _monitor()
    m._on_disc = lambda disc, st: emitted.append(disc)
    sig = (np.zeros((48, 24), np.float32), np.zeros((48, 48), np.float32), np.zeros((24, 24), np.float32))
    monkeypatch.setattr(m, "_s17_disc_signature", lambda frame: sig)
    monkeypatch.setattr(m, "_assign_s17_pj", lambda disc, face: None)
    bad = _disc_full(); bad.confianza_global = 0.5
    monkeypatch.setattr("app.core.monitor.parse_disc_s17_full", lambda frame, ocr: (bad, None))
    m._process_disc_s17_continuous(None, ScreenState("S17", 1.0, "tmpl"))
    assert emitted == []
    assert m._disc_aggregator.current is None  # no se fusionó nada


def test_assign_s17_visualizacion_no_equipado(monkeypatch):
    """Candidato (mismo slot) sin badge → equip_detectado False, sin dueño."""
    import app.core.monitor as mon
    monkeypatch.setattr(mon, "crop_grid_selected_badge", lambda f: None)
    m = _monitor()
    m._identifier = _StubIdent()
    m._last_agent_name = "Zhu Yuan"
    m._s17_last_slot = 1                       # mismo slot → no es el equipado
    disc = _disc(slot=1)
    m._assign_s17_pj(disc, _frame())
    assert disc.equip_detectado is False
    assert disc.equip_pj_visual is None


def test_assign_s17_visualizacion_equipado_por_latch(monkeypatch):
    """Con badge del PJ latcheado (equipado por flujo) → equip_detectado True +
    equip_pj_visual = latch."""
    from app.core.monitor import _S17_OWNER_MIN_SAMPLES
    m = _monitor_badge(monkeypatch, sim=0.95, owner=("Zhu Yuan", 0.95))
    m._s17_last_slot = 0                       # slot nuevo → equipado
    m._s17_owner_passes = _S17_OWNER_MIN_SAMPLES   # warmup ya corrió → trust anchor
    disc = _disc(slot=1)
    m._assign_s17_pj(disc, _frame())
    assert disc.equip_detectado is True
    assert disc.equip_pj_visual == "Zhu Yuan"


def test_assign_s17_anchor_difiere_hasta_voto_y_badge_gana(monkeypatch):
    """QA 2026-06-20 (Nana de Seth marcado 'Nicole'): el ancla NO debe asignar el latch
    antes de que el badge vote. (a) sin voto y sin warmup → DIFIERE (no asigna). (b) con un
    voto que CONTRADICE al latch → gana el badge, no se cosecha bajo el latch."""
    from app.core.monitor import _S17_OWNER_MIN_SAMPLES
    from app.core.stats_vocab import _norm_key
    import app.core.monitor as mon
    # (a) Primer frame: sin voto acumulado, warmup en 0 → diferir (no fijar nada).
    m = _monitor_badge(monkeypatch, sim=None, owner=None)
    m._last_agent_name = "Nicole"
    m._s17_last_slot = 0
    m._s17_owner_passes = 0
    monkeypatch.setattr(m, "_s17_voted_owner", lambda f: None)   # voto aún no listo
    disc = _disc(slot=1)
    m._assign_s17_pj(disc, _frame())
    assert disc.agente_asignado_nombre is None, "sin voto + sin warmup → no asignar (diferir)"
    assert m._s17_last_slot == 0, "no debe fijar el slot al diferir"
    # (b) Ya hay voto y CONTRADICE al latch (badge dice Seth, latch Nicole) → gana el badge.
    monkeypatch.setattr(m, "_s17_voted_owner", lambda f: "Seth")
    disc2 = _disc(slot=1)
    m._assign_s17_pj(disc2, _frame())
    assert disc2.equip_pj_visual == "Seth", "el badge debe ganar al ancla"
    assert disc2.agente_asignado_nombre is None, "no se asigna el latch (no cosecha bajo Nicole)"
    assert "Nicole" not in m._identifier.learned


def test_persist_s17_sin_pj_no_pisa_lo_curado(syncer_db):
    """Re-captura SIN asignación confiable no persiste → preserva el PJ curado."""
    sync = _make_syncer(syncer_db)
    try:
        d1 = _disc(); d1.agente_asignado_nombre = "Zhu Yuan"; d1.agente_asignado_conf = 0.95
        res1 = sync.persist_s17_disc(d1)
        # Segunda pasada SIN asignación confiable → None, no toca nada.
        res2 = sync.persist_s17_disc(_disc())
        assert res2 is None
        con = sqlite3.connect(str(syncer_db)); con.row_factory = sqlite3.Row
        r = con.execute("SELECT agente_asignado, equipado FROM inventory_discs WHERE id=?", (res1.disc_id,)).fetchone()
        assert r["agente_asignado"] == 7 and r["equipado"] == 1, "no debe pisar lo curado"
        con.close()
    finally:
        sync.close()


# --- 5b. Resolución de set INSENSIBLE A ACENTOS (OCR pierde tildes) -----------

def test_resolve_set_id_sin_tilde(syncer_db):
    """
    El OCR pierde tildes inconsistentemente ('Melodía'→'Melodia'). _resolve_set_id
    debe matchear igual (regresión del slot 2 que no persistía en el QA 2026-06-07).
    """
    con = sqlite3.connect(str(syncer_db))
    con.execute("INSERT INTO disc_sets (id, nombre, nombre_en, bonus_2p_stat, bonus_2p_valor, bonus_4p_desc) "
                "VALUES (2, 'Melodía de Faetón', \"Phaethon's Melody\", 'Tasa de Anomalía', '+8%', 'Cuando...')")
    con.commit(); con.close()
    sync = _make_syncer(syncer_db)
    try:
        d = _disc(slot=2, set_name="Melodia de Faetón")  # OCR sin la í
        assert sync._resolve_set_id(d) == 2
        # Persiste de punta a punta con el PJ asignado.
        d.agente_asignado_nombre = "Zhu Yuan"; d.agente_asignado_conf = 0.95
        res = sync.persist_s17_disc(d)
        assert res is not None
        con = sqlite3.connect(str(syncer_db)); con.row_factory = sqlite3.Row
        r = con.execute("SELECT set_id FROM inventory_discs WHERE id=?", (res.disc_id,)).fetchone()
        assert r["set_id"] == 2
        con.close()
    finally:
        sync.close()


def test_resolve_set_id_no_inventa_set(syncer_db):
    """Un nombre que no se parece a ningún set → None (no falso positivo)."""
    sync = _make_syncer(syncer_db)
    try:
        d = _disc(set_name="Texto OCR basura xyz")
        assert sync._resolve_set_id(d) is None
    finally:
        sync.close()


def test_resolve_set_id_distingue_sets_parecidos(syncer_db):
    """Sets distintos no colisionan al normalizar (Jazz caótico ≠ Melodía)."""
    con = sqlite3.connect(str(syncer_db))
    con.execute("INSERT INTO disc_sets (id, nombre) VALUES (2, 'Melodía de Faetón')")
    con.commit(); con.close()
    sync = _make_syncer(syncer_db)
    try:
        assert sync._resolve_set_id(_disc(set_name="Jazz caotico")) == 1   # sin tilde en ó
        assert sync._resolve_set_id(_disc(set_name="melodia de faeton")) == 2
    finally:
        sync.close()


def test_resolve_set_id_fuzzy_drop_de_letra(syncer_db):
    """
    Regresión QA Yixuan 2026-06-08: el OCR dropea una letra del nombre del set
    ('Fábula Yunkui'→'Fäbua Yunkui'), que el substring no captura. El fuzzy difflib
    (cutoff 0.86 + guarda de ambigüedad) lo resuelve, pero NO inventa ante un nombre
    genuinamente lejano/ambiguo (dos sets 'Balada …' + alias corto del catálogo).
    """
    con = sqlite3.connect(str(syncer_db))
    con.execute("INSERT INTO disc_sets (id, nombre) VALUES (49, 'Fábula Yunkui')")
    con.execute("INSERT INTO disc_sets (id, nombre) VALUES (25, 'Balada rama/espada')")
    con.execute("INSERT INTO disc_sets (id, nombre) VALUES (51, 'Balada de aguas blancas')")
    con.commit(); con.close()
    sync = _make_syncer(syncer_db)
    try:
        assert sync._resolve_set_id(_disc(set_name="Fäbua Yunkui")) == 49  # drop de 'l'
        # forma larga real vs alias corto + 2º 'Balada' → ambiguo/lejano → None
        assert sync._resolve_set_id(_disc(set_name="Balada de la rama y la espada")) is None
    finally:
        sync.close()


# --- 5c. Modo READONLY (DANIBOD_READONLY) — no escribe -----------------------

def test_persist_s17_readonly_no_escribe(syncer_db, monkeypatch):
    """
    Con DANIBOD_READONLY, persist_s17_disc NO toca la DB (modo offline para testear
    hipótesis), pero devuelve un SyncResult informativo (trigger='readonly').
    """
    monkeypatch.setenv("DANIBOD_READONLY", "1")
    sync = _make_syncer(syncer_db)
    try:
        d = _disc(slot=1)
        d.agente_asignado_nombre = "Zhu Yuan"; d.agente_asignado_conf = 0.95
        res = sync.persist_s17_disc(d)
        assert res is not None and res.trigger == "readonly"
        con = sqlite3.connect(str(syncer_db)); con.row_factory = sqlite3.Row
        n = con.execute("SELECT COUNT(*) c FROM inventory_discs").fetchone()["c"]
        assert n == 0, "readonly no debe escribir en la DB"
        con.close()
    finally:
        sync.close()


def test_persist_s17_escribe_si_no_readonly(syncer_db, monkeypatch):
    """Sin la var (o '0'), persiste normal — confirma que el guard no rompe el flujo."""
    monkeypatch.setenv("DANIBOD_READONLY", "0")
    sync = _make_syncer(syncer_db)
    try:
        d = _disc(slot=1)
        d.agente_asignado_nombre = "Zhu Yuan"; d.agente_asignado_conf = 0.95
        res = sync.persist_s17_disc(d)
        assert res is not None and res.trigger != "readonly"
        con = sqlite3.connect(str(syncer_db)); con.row_factory = sqlite3.Row
        n = con.execute("SELECT COUNT(*) c FROM inventory_discs WHERE equipado=1").fetchone()["c"]
        assert n == 1
        con.close()
    finally:
        sync.close()


# --- 6. Composición de set derivada de inventory_discs -----------------------

def _comp_db():
    """DB en memoria con inventory_discs + disc_sets para tests de composición."""
    con = sqlite3.connect(":memory:"); con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE disc_sets (id INTEGER PRIMARY KEY, nombre TEXT);
        CREATE TABLE inventory_discs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, set_id INTEGER, slot INTEGER,
            equipado INTEGER DEFAULT 0, agente_asignado INTEGER, descartado INTEGER DEFAULT 0
        );
        INSERT INTO disc_sets VALUES (1,'Jazz Caótico'),(2,'Melodía de Faetón'),(3,'Set C');
    """)
    return con


def _seed(con, agente, pares):
    """pares: lista de (slot, set_id)."""
    for slot, sid in pares:
        con.execute("INSERT INTO inventory_discs (set_id, slot, equipado, agente_asignado) VALUES (?,?,1,?)",
                    (sid, slot, agente))
    con.commit()


def test_composicion_estandar_4_2():
    from app.core.sync_equip import compute_set_composition, format_composition
    con = _comp_db()
    _seed(con, 26, [(1, 1), (6, 1), (2, 2), (3, 2), (4, 2), (5, 2)])  # 2x Jazz + 4x Melodía
    comp = compute_set_composition(con, 26)
    assert comp["clasificacion"] == "estándar 4+2"
    assert comp["faltantes"] == []
    # 4pc primero
    assert comp["sets"][0]["nombre"] == "Melodía de Faetón" and comp["sets"][0]["tier"] == "4pc"
    assert comp["sets"][1]["nombre"] == "Jazz Caótico" and comp["sets"][1]["tier"] == "2pc"
    s = format_composition(comp)
    assert s == "4pc Melodía de Faetón + 2pc Jazz Caótico · 6/6 · estándar 4+2", s


def test_composicion_exotica_2_2_2():
    from app.core.sync_equip import compute_set_composition
    con = _comp_db()
    _seed(con, 1, [(1, 1), (2, 1), (3, 2), (4, 2), (5, 3), (6, 3)])
    comp = compute_set_composition(con, 1)
    assert comp["clasificacion"] == "exótica"
    assert all(s["tier"] == "2pc" for s in comp["sets"]) and len(comp["sets"]) == 3


def test_composicion_incompleta_con_faltantes():
    from app.core.sync_equip import compute_set_composition, format_composition
    con = _comp_db()
    _seed(con, 1, [(1, 1), (2, 2), (3, 2), (4, 2), (5, 2)])  # slot 6 faltante
    comp = compute_set_composition(con, 1)
    assert comp["clasificacion"] == "incompleta"
    assert comp["faltantes"] == [6]
    assert "slots 6 faltantes (nulo/no capturado)" in format_composition(comp)
    # set con 1 pieza → "suelto"
    jazz = next(s for s in comp["sets"] if s["nombre"] == "Jazz Caótico")
    assert jazz["tier"] == "suelto"


def test_composicion_sin_discos():
    from app.core.sync_equip import compute_set_composition, format_composition
    con = _comp_db()
    comp = compute_set_composition(con, 99)
    assert comp["sets"] == [] and comp["faltantes"] == [1, 2, 3, 4, 5, 6]
    assert format_composition(comp) == "sin discos equipados capturados"


def test_persist_s17_devuelve_composicion(syncer_db):
    """persist_s17_disc adjunta la composición del PJ asignado al SyncResult."""
    sync = _make_syncer(syncer_db)
    try:
        d = _disc(slot=1); d.agente_asignado_nombre = "Zhu Yuan"; d.agente_asignado_conf = 0.95
        res = sync.persist_s17_disc(d)
        assert res is not None and res.set_composition is not None
        # 1 disco (slot 1) → incompleta con 5 faltantes
        assert "incompleta" in res.set_composition
    finally:
        sync.close()


# --- 5. Fixes de la fuga RNF-06 (gates de OCR + watchdog) --------------------

def test_s18_stats_signature_gate():
    """Gate OCR S18 (RNF-06): firma de DOS componentes (nombre+banner / stats) de la mitad
    DERECHA. Cambio en la mitad IZQUIERDA (modelo 3D) NO mueve ninguna → skip OCR; cambio
    en el bloque de stats O en el NOMBRE → re-OCR."""
    from app.core.monitor import Monitor, _S18_SIG_MAX, _S18_SIG_NAME_MAX
    H, W = 1439, 2557

    def _reocr(s1, s2):
        """Replica la condición del gate: re-OCR si CUALQUIERA de las 2 componentes cambió."""
        return (Monitor._sig_component_diff(s1[0], s2[0]) > _S18_SIG_NAME_MAX
                or Monitor._sig_component_diff(s1[1], s2[1]) > _S18_SIG_MAX)

    a = np.zeros((H, W, 3), np.uint8)
    a[int(0.18 * H):int(0.39 * H), int(0.54 * W):int(0.96 * W)] = 40   # nombre + banner
    a[int(0.39 * H):int(0.74 * H), int(0.54 * W):int(0.96 * W)] = 30   # bloque de stats
    sig_a = Monitor._s18_stats_signature(a)
    assert sig_a is not None and isinstance(sig_a, tuple) and len(sig_a) == 2
    # "Animación" en la mitad izquierda (modelo del PJ) → ninguna componente cambia → skip.
    b = a.copy(); b[:, :int(0.50 * W)] = 220
    assert not _reocr(sig_a, Monitor._s18_stats_signature(b))
    # Cambio en el bloque de STATS (level-up) → re-OCR.
    c = a.copy(); c[int(0.40 * H):int(0.73 * H), int(0.55 * W):int(0.95 * W)] = 220
    assert _reocr(sig_a, Monitor._s18_stats_signature(c))
    # Cambio SOLO en el NOMBRE (otro agente del MISMO rol, stats parecidos) → re-OCR. Fix
    # QA 2026-06-20 (N.º 11 -> Sporos, ambos Ataque): antes el gate quedaba pegado porque la
    # firma solo miraba el bloque de stats y a 32×32 la diferencia de dígitos se diluía.
    e = a.copy(); e[int(0.19 * H):int(0.31 * H), int(0.55 * W):int(0.95 * W)] = 220
    assert _reocr(sig_a, Monitor._s18_stats_signature(e))


def test_s17_post_emit_skip_no_ocr(monkeypatch):
    """Gate RNF-06: un disco YA emitido con firma sin cambios NO vuelve a llamar OCR
    (parse_disc_s17_full) cada ciclo — era el desperdicio que alimentaba el leak."""
    from app.core import monitor as _mon
    from app.core.detector import ScreenState
    calls = {"n": 0}
    monkeypatch.setattr(_mon, "parse_disc_s17_full",
                        lambda frame, ocr: (calls.__setitem__("n", calls["n"] + 1), (None, None))[1])
    m = _monitor()
    frame = np.full((1439, 2557, 3), 50, np.uint8)
    m._disc_agg_sig = m._s17_disc_signature(frame)   # ancla = este disco (firma estable)
    m._disc_emitted = True                            # ya procesado/emitido
    m._process_disc_s17_continuous(frame, ScreenState("S17", 0.9, ""))
    assert calls["n"] == 0                            # OCR salteado por el gate


def test_ram_watchdog_dispara_restart_una_vez(monkeypatch):
    """Watchdog RNF-06: cruzar el umbral de private dispara el callback 1×; respeta el
    guard de 'ya disparado', el kill-switch env y el umbral."""
    from app.core import monitor as _mon
    fired = {"n": 0}
    bump = lambda: fired.__setitem__("n", fired["n"] + 1)

    # Cruza umbral → dispara una vez; segundo llamado no re-dispara (guard).
    m = _monitor(); m._on_ram_critical = bump
    monkeypatch.setattr(_mon.mem_diag, "mem_counters",
                        lambda: (0.0, float(_mon._RAM_RESTART_MB + 100)))
    m._ram_watchdog(1000.0)
    assert fired["n"] == 1
    m._ram_watchdog(2000.0)
    assert fired["n"] == 1

    # Bajo umbral → no dispara.
    m2 = _monitor(); m2._on_ram_critical = bump
    monkeypatch.setattr(_mon.mem_diag, "mem_counters",
                        lambda: (0.0, float(_mon._RAM_RESTART_MB - 500)))
    m2._ram_watchdog(1000.0)
    assert fired["n"] == 1

    # Kill-switch env → no dispara aunque cruce.
    m3 = _monitor(); m3._on_ram_critical = bump
    monkeypatch.setenv("DANIBOD_NO_RAM_GUARD", "1")
    monkeypatch.setattr(_mon.mem_diag, "mem_counters",
                        lambda: (0.0, float(_mon._RAM_RESTART_MB + 100)))
    m3._ram_watchdog(1000.0)
    assert fired["n"] == 1


def test_mem_counters_lee_memoria():
    """mem_counters() debe devolver WS y commit > 0. Regresión: la reescritura a ctypes-only
    devolvía (0,0) → el heartbeat y el watchdog leían 0 y el watchdog NUNCA disparaba (la app
    llegó a 29 GB en la medición post-gates antes de detectar esto)."""
    from app.core import mem_diag
    ws, commit = mem_diag.mem_counters()
    assert ws > 0, f"WorkingSet leyó {ws}"
    assert commit > 0, f"commit/private leyó {commit}"
