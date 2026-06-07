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

def test_guarda_s17_confirma_mismo_pj_y_abstiene_otro():
    """
    Aprendido el descriptor S17 de un PJ (desde Ejemplo_1), otros discos del MISMO
    PJ (Ej_8/9/10) confirman (sim alto) y discos de OTRO PJ (Ej_2/4/5) abstienen.
    """
    ident = AgentIdentifier(autoload=False)
    def face(name):
        fr, ln, W, H = _load_frame_lines(name)
        f = crop_s17_assigned_avatar(fr, ln, W, H)
        assert f is not None, name
        return f

    ident.learn_s17(face("Ejemplo_1"), "PJ_A")
    # Mismo PJ → sim alto
    for same in ["Ejemplo_8", "Ejemplo_9", "Ejemplo_10"]:
        sim = ident.s17_similarity(face(same), "PJ_A")
        assert sim is not None and sim >= 0.86, f"{same}: sim={sim} (debería confirmar)"
    # Otro PJ → sim bajo (abstiene)
    for other in ["Ejemplo_2", "Ejemplo_4", "Ejemplo_5"]:
        sim = ident.s17_similarity(face(other), "PJ_A")
        assert sim is not None and sim < 0.86, f"{other}: sim={sim} (debería abstener)"


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


def test_monitor_bootstrap_asigna_y_aprende_con_latch():
    """Latch presente + PJ no visto aún en S17 → confía latch, aprende, asigna."""
    fr, ln, W, H = _load_frame_lines("Ejemplo_1")
    face = crop_s17_assigned_avatar(fr, ln, W, H)
    m = _monitor()
    m._last_agent_name = "Zhu Yuan"
    disc = _disc()
    m._assign_s17_pj(disc, face)
    assert disc.agente_asignado_nombre == "Zhu Yuan"
    assert disc.agente_asignado_conf == 1.0
    assert "Zhu Yuan" in m._identifier.names_s17  # aprendió el descriptor S17


def test_monitor_confirma_mismo_pj_tras_bootstrap():
    """Tras bootstrap con Ej_1, otro disco del MISMO PJ (Ej_9) confirma por avatar."""
    m = _monitor()
    m._last_agent_name = "Zhu Yuan"
    f1, l1, W1, H1 = _load_frame_lines("Ejemplo_1")
    m._assign_s17_pj(_disc(), crop_s17_assigned_avatar(f1, l1, W1, H1))  # bootstrap
    f9, l9, W9, H9 = _load_frame_lines("Ejemplo_9")
    disc = _disc()
    m._assign_s17_pj(disc, crop_s17_assigned_avatar(f9, l9, W9, H9))
    assert disc.agente_asignado_nombre == "Zhu Yuan"
    assert 0.86 <= disc.agente_asignado_conf < 1.0  # confirmado por sim, no bootstrap


def test_monitor_abstiene_si_avatar_es_de_otro_pj():
    """Tras aprender PJ_A (Ej_1), un disco de OTRO PJ (Ej_2) → no asigna (preserva)."""
    m = _monitor()
    m._last_agent_name = "Zhu Yuan"
    f1, l1, W1, H1 = _load_frame_lines("Ejemplo_1")
    m._assign_s17_pj(_disc(), crop_s17_assigned_avatar(f1, l1, W1, H1))  # aprende Zhu Yuan
    f2, l2, W2, H2 = _load_frame_lines("Ejemplo_2")
    disc = _disc()
    m._assign_s17_pj(disc, crop_s17_assigned_avatar(f2, l2, W2, H2))
    assert disc.agente_asignado_nombre is None
    assert disc.agente_asignado_conf == 0.0


def test_monitor_sin_latch_no_asigna():
    fr, ln, W, H = _load_frame_lines("Ejemplo_1")
    m = _monitor()
    m._last_agent_name = None
    disc = _disc()
    m._assign_s17_pj(disc, crop_s17_assigned_avatar(fr, ln, W, H))
    assert disc.agente_asignado_nombre is None


def test_monitor_sin_avatar_no_asigna():
    m = _monitor()
    m._last_agent_name = "Zhu Yuan"
    disc = _disc()
    m._assign_s17_pj(disc, None)  # disco sin equipar / avatar no localizado
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


def test_persist_s17_sin_asignacion_no_equipa(syncer_db):
    sync = _make_syncer(syncer_db)
    try:
        res = sync.persist_s17_disc(_disc())  # sin agente_asignado_nombre
        assert res is not None and res.agente_asignado_nombre is None
        con = sqlite3.connect(str(syncer_db)); con.row_factory = sqlite3.Row
        r = con.execute("SELECT agente_asignado, equipado FROM inventory_discs WHERE id=?", (res.disc_id,)).fetchone()
        assert r["agente_asignado"] is None and r["equipado"] == 0
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


def test_maybe_process_disc_recaptura_al_cambiar_slot(monkeypatch):
    """S17: la dedup es por (code, slot) → cambiar de slot re-captura."""
    from app.core.detector import ScreenState
    m = _monitor()
    calls = []
    monkeypatch.setattr(m, "_process_disc", lambda frame, st: calls.append(st.slot))
    s1 = ScreenState("S17", 1.0, "tmpl"); s1.slot = 1
    s1b = ScreenState("S17", 1.0, "tmpl"); s1b.slot = 1
    s2 = ScreenState("S17", 1.0, "tmpl"); s2.slot = 2
    m._maybe_process_disc(None, s1)   # captura slot 1
    m._maybe_process_disc(None, s1b)  # mismo slot → dedup
    m._maybe_process_disc(None, s2)   # slot 2 → re-captura
    assert calls == [1, 2], f"esperaba capturas en slot 1 y 2, hubo {calls}"


def test_persist_s17_update_preserva_asignacion_si_sin_match(syncer_db):
    """Re-captura del mismo disco SIN asignación confiable no pisa el PJ curado."""
    sync = _make_syncer(syncer_db)
    try:
        d1 = _disc(); d1.agente_asignado_nombre = "Zhu Yuan"; d1.agente_asignado_conf = 0.95
        res1 = sync.persist_s17_disc(d1)
        # Segunda pasada del MISMO disco (mismo hash) sin asignación → preserva
        res2 = sync.persist_s17_disc(_disc())
        assert res2 is not None and res2.disc_id == res1.disc_id
        con = sqlite3.connect(str(syncer_db)); con.row_factory = sqlite3.Row
        r = con.execute("SELECT agente_asignado, equipado FROM inventory_discs WHERE id=?", (res1.disc_id,)).fetchone()
        assert r["agente_asignado"] == 7 and r["equipado"] == 1, "no debe pisar lo curado"
        con.close()
    finally:
        sync.close()
