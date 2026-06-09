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
    ident = AgentIdentifier(autoload=False, roster={"PJ_A"})  # roster explícito (no DB)
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


def test_monitor_confia_en_latch_para_disco_equipado():
    """
    Fase 4 (revisado tras QA 2026-06-09): el avatar circular S17 es poco
    discriminativo (best-match inservible) → para el disco EQUIPADO se CONFÍA en el
    latch (identidad fiable de S8/S18), sin rechazar por el avatar. La discriminación
    de discos de OTRO PJ (grilla) se difiere a su fase. Aquí: latch presente → asigna
    al latch aunque el frame sea de otro PJ.
    """
    m = _monitor()
    m._identifier._roster_norm = {}  # no validar roster en el test
    f2, l2, W2, H2 = _load_frame_lines("Ejemplo_2")
    m._last_agent_name = "Zhu Yuan"
    disc = _disc()
    m._assign_s17_pj(disc, crop_s17_assigned_avatar(f2, l2, W2, H2))
    assert disc.agente_asignado_nombre == "Zhu Yuan"  # confía en el latch
    assert disc.equip_pj_visual == "Zhu Yuan"


def test_monitor_self_heal_descriptor_viejo_no_falso_rechaza():
    """
    Fase 4: un descriptor S17 VIEJO del latch (sim baja, p.ej. Nangong 0.734) NO debe
    causar falso-rechazo si nadie le gana: se asigna al latch y se RE-APRENDE.
    """
    m = _monitor()
    m._identifier._roster_norm = {}
    f1, l1, W1, H1 = _load_frame_lines("Ejemplo_1")
    f9, l9, W9, H9 = _load_frame_lines("Ejemplo_9")  # mismo PJ, otro disco
    # Sembrar un descriptor "viejo" del latch desde un frame de OTRO PJ (sim baja).
    m._identifier.learn_s17(crop_s17_assigned_avatar(f1, l1, W1, H1), "Zhu Yuan")
    import numpy as np
    m._identifier._lib_s17["Zhu Yuan"] = m._identifier._lib_s17["Zhu Yuan"] * 0  # descriptor degradado
    m._last_agent_name = "Zhu Yuan"
    disc = _disc()
    m._assign_s17_pj(disc, crop_s17_assigned_avatar(f9, l9, W9, H9))
    assert disc.agente_asignado_nombre == "Zhu Yuan"  # no falso-rechazo


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


def test_identifier_prune_to_roster(tmp_path):
    """Fase 4: prune_to_roster quita entradas espurias de ambas librerías."""
    import numpy as np
    from app.core.agent_identifier import AgentIdentifier
    ident = AgentIdentifier(library_path=tmp_path / "lib.npz", autoload=False,
                            roster={"Nangong Yu"})
    z = np.zeros(10, np.float32)
    ident._lib = {"Nangong Yu": z, "Permiso": z}
    ident._lib_s17 = {"Nangong Yu": z, "Sporos_bogus": z}
    assert ident.prune_to_roster() == 2
    assert ident.names == ["Nangong Yu"] and ident.names_s17 == ["Nangong Yu"]


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
    monkeypatch.setattr(m, "_handle_upgrade", lambda f, s: None)
    m._dispatch_state(np.zeros((1440, 2560, 3), np.uint8), ScreenState("S8", 0.9, "tmpl"))
    assert m._agent_anchor_x == 0.123      # re-anclado a la posición actual
    assert m._last_agent_name == "Burnice"  # latch preservado (no 'OtroPJ')


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


_SLOTS_DIR = REPO / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers" / "14_Slots_equipamiento"


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
    sig = (np.zeros((48, 48), np.float32), np.zeros((24, 24), np.float32))
    monkeypatch.setattr(m, "_s17_disc_signature", lambda frame: sig)
    monkeypatch.setattr(m, "_assign_s17_pj", lambda disc, face: None)

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
        lambda frame: (np.full((48, 48), next(seqsig), np.float32), np.zeros((24, 24), np.float32)),
    )
    monkeypatch.setattr(m, "_assign_s17_pj", lambda disc, face: None)
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
    sig = (np.zeros((48, 48), np.float32), np.zeros((24, 24), np.float32))
    monkeypatch.setattr(m, "_s17_disc_signature", lambda frame: sig)
    monkeypatch.setattr(m, "_assign_s17_pj", lambda disc, face: None)
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
    sig = (np.zeros((48, 48), np.float32), np.zeros((24, 24), np.float32))
    monkeypatch.setattr(m, "_s17_disc_signature", lambda frame: sig)
    monkeypatch.setattr(m, "_assign_s17_pj", lambda disc, face: None)
    bad = _disc_full(); bad.confianza_global = 0.5
    monkeypatch.setattr("app.core.monitor.parse_disc_s17_full", lambda frame, ocr: (bad, None))
    m._process_disc_s17_continuous(None, ScreenState("S17", 1.0, "tmpl"))
    assert emitted == []
    assert m._disc_aggregator.current is None  # no se fusionó nada


def test_assign_s17_visualizacion_no_equipado():
    """Sin avatar → equip_detectado False (disco disponible, no equipado)."""
    m = _monitor()
    m._last_agent_name = "Zhu Yuan"
    disc = _disc()
    m._assign_s17_pj(disc, None)
    assert disc.equip_detectado is False
    assert disc.equip_pj_visual is None


def test_assign_s17_visualizacion_equipado_por_latch():
    """Con avatar del PJ latcheado → equip_detectado True + equip_pj_visual = latch."""
    fr, ln, W, H = _load_frame_lines("Ejemplo_1")
    m = _monitor()
    m._last_agent_name = "Zhu Yuan"
    disc = _disc()
    m._assign_s17_pj(disc, crop_s17_assigned_avatar(fr, ln, W, H))
    assert disc.equip_detectado is True
    assert disc.equip_pj_visual == "Zhu Yuan"


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
