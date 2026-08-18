"""El upsert de `on_disc_detected` deduplica por IDENTIDAD, no por la firma gruesa.

`find_by_hash` compara `(set, slot, main_stat, main_valor)`. Suena razonable hasta que se mira qué
son los slots 1, 2 y 3: **su main es fijo** (PV / ATK / DEF planos), así que a un mismo nivel todos
los discos de un set comparten los cuatro campos. La firma no distingue discos: distingue
*casilleros*.

Medido contra el inventario real de 367 discos (snapshot `pre_censo_20260817`):

| clave | filas que sobreviven |
|---|---|
| `(set, slot, main, main_valor)` | **177** — se pierde el 51,8 % |
| identidad completa (`+ nivel + {substat, rolls}`) | **345** |

El grupo peor: 10 discos de Monarca del Pináculo, slot 3, DEF 184 — un solo registro para el
sistema. Un disco farmeado nuevo no se insertaba: **pisaba** a uno viejo que no tenía nada que ver.

La identidad correcta ya estaba escrita en este repo (`row_matches_parsed_identity`), y el mismo
bug ya se había arreglado una vez **en la capa de emisión** (`_disc_identity`, junio 2026: *"en
slot 1 el main es siempre HP → dos discos distintos del MISMO set colapsaban"*). Se arregló donde
se veía —el log— y no donde se escribe.

Los 22 pares que ni la identidad completa separa son ambigüedad irreducible: dos discos realmente
idénticos. Ahí no se adivina (RNF-02), se avisa.
"""
from __future__ import annotations

import sqlite3

import pytest

from app.core.parser_disc import DiscParsed, SubstatParsed

_SCHEMA = """
CREATE TABLE disc_archetypes (
    id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, nombre TEXT,
    mains_4 TEXT, mains_5 TEXT, mains_6 TEXT,
    substats_positivos TEXT, substats_perjudiciales TEXT,
    threshold_stock REAL NOT NULL DEFAULT 0.7
);
CREATE TABLE agents (
    id INTEGER PRIMARY KEY, nombre TEXT UNIQUE, rol TEXT DEFAULT 'Ataque',
    set_4p_id INTEGER, set_2p_id INTEGER, protected_build INTEGER DEFAULT 0,
    arquetipo_primario_id INTEGER DEFAULT 1
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
CREATE TABLE inventory_disc_evaluations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    inventory_disc_id INTEGER NOT NULL REFERENCES inventory_discs(id),
    fecha             DATETIME DEFAULT CURRENT_TIMESTAMP,
    trigger_evento    TEXT NOT NULL,   -- 'captura_inicial' | 're_eval_threshold' | 're_eval_upgrade' | 're_eval_manual'
    recomendacion     TEXT,            -- 'equipar_pj_X' | 'mejorar_pj_Y' | 'reserva_arq_Z' | 'descartar'
    score             REAL,
    detalle_json      TEXT             -- desglose: set_match, main_match, subs_positivos, subs_perjudiciales, arquetipo, pj_top
);
INSERT INTO disc_archetypes (id, code, nombre, mains_4, mains_5, mains_6, substats_positivos, substats_perjudiciales) VALUES
  (1, 'ATK_DPS', 'ATK DPS', '["Prob. Crítica"]', '["ATK%"]', '["ATK%"]',
   '{"ATK": 1.0, "Daño Crítico": 1.0}', '{"DEF": -0.5}');
INSERT INTO disc_sets VALUES (1, 'Monarca del Pináculo', 'Peak Monarch', 'PV', '+10%', 'Al golpear...');
INSERT INTO agents (id, nombre, rol) VALUES (5, 'Ellen', 'Ataque');
INSERT INTO agent_score_thresholds (agente_id) VALUES (5);
"""


@pytest.fixture
def db(tmp_path, monkeypatch):
    import app.core.sync_equip as se
    monkeypatch.setattr(se, "is_readonly", lambda: False)
    path = tmp_path / "dedup.db"
    con = sqlite3.connect(str(path))
    con.executescript(_SCHEMA)
    con.commit(); con.close()
    return path


def _syncer(path):
    from app.core.sync_equip import DiscSyncer
    return DiscSyncer(db_path=path)


def _sub(name, val, rolls, unidad="flat"):
    return SubstatParsed(name, name, val, unidad, rolls, 0.95)


def _slot3(subs, nivel=15):
    """Disco slot 3 de Monarca: main DEF plano, idéntico en TODOS los discos del set a ese nivel.
    Lo único que los distingue son los substats — que es justo lo que la firma gruesa ignoraba."""
    return DiscParsed(
        set_name_raw="Monarca del Pináculo", set_name_canon="Monarca del Pináculo", slot=3,
        main_stat_raw="DEF", main_stat_canon="DEF", main_valor=184.0, main_unidad="flat",
        nivel=nivel, rareza="S", subs=subs, confianza_global=0.95,
    )


_SUBS_A = [_sub("ATK", 38.0, 1), _sub("Daño Crítico", 9.6, 1, "%"),
           _sub("Perforación", 27.0, 2), _sub("Maestría de Anomalía", 9.0, 0)]
_SUBS_B = [_sub("PV", 320.0, 2), _sub("Prob. Crítica", 4.8, 1, "%"),
           _sub("DEF%", 12.0, 0, "%"), _sub("Impacto", 3.0, 1)]


def _count(path):
    con = sqlite3.connect(str(path))
    n = con.execute("SELECT COUNT(*) FROM inventory_discs").fetchone()[0]
    con.close()
    return n


def _subs_de(path, disc_id):
    con = sqlite3.connect(str(path)); con.row_factory = sqlite3.Row
    r = con.execute("SELECT sub1, sub2, sub3, sub4 FROM inventory_discs WHERE id=?",
                    (disc_id,)).fetchone()
    con.close()
    return [r[f"sub{i}"] for i in (1, 2, 3, 4)]


# --- el bug de los 190 discos -----------------------------------------------------------------

def test_dos_discos_del_MISMO_set_y_slot_no_colapsan_en_uno(db):
    """El caso exacto que perdía el 51,8 % del inventario: mismo set, mismo slot, mismo main y
    mismo valor de main — y aun así son dos discos distintos, porque los substats difieren."""
    s = _syncer(db)
    r1 = s.on_disc_detected(_slot3(_SUBS_A))
    r2 = s.on_disc_detected(_slot3(_SUBS_B))
    assert r1 is not None and r2 is not None
    assert r1.disc_id != r2.disc_id, "el segundo disco pisó al primero"
    assert _count(db) == 2
    assert "ATK" in _subs_de(db, r1.disc_id)
    assert "PV" in _subs_de(db, r2.disc_id), "el disco viejo quedó con los substats del nuevo"


def test_el_mismo_disco_visto_dos_veces_sigue_siendo_UNO(db):
    """La otra mitad del contrato: precisión no puede costar duplicados. Ver el mismo disco en dos
    frames (o dos sesiones) tiene que actualizar, no insertar."""
    s = _syncer(db)
    r1 = s.on_disc_detected(_slot3(_SUBS_A))
    r2 = s.on_disc_detected(_slot3(_SUBS_A))
    assert r1.disc_id == r2.disc_id
    assert _count(db) == 1
    assert r2.trigger == "re_eval_threshold", "el segundo avistamiento es re-evaluación"


def test_los_MISMOS_substats_con_distintos_rolls_son_discos_distintos(db):
    """Los rolls son enteros limpios y distinguen builds; por eso entran a la identidad y los
    valores (ruidosos por OCR) no."""
    otros_rolls = [_sub("ATK", 38.0, 3), _sub("Daño Crítico", 9.6, 1, "%"),
                   _sub("Perforación", 27.0, 0), _sub("Maestría de Anomalía", 9.0, 0)]
    s = _syncer(db)
    r1 = s.on_disc_detected(_slot3(_SUBS_A))
    r2 = s.on_disc_detected(_slot3(otros_rolls))
    assert r1.disc_id != r2.disc_id
    assert _count(db) == 2


def test_los_valores_ruidosos_del_OCR_no_parten_un_disco_en_dos(db):
    """Contrapeso del test anterior. Los VALORES quedan fuera de la identidad a propósito: el OCR
    lee 38.0 y 38.4 del mismo substat entre ciclos. Si contaran, cada relectura sería un disco
    nuevo y el censo contaría de más."""
    ruidoso = [_sub("ATK", 38.4, 1), _sub("Daño Crítico", 9.5, 1, "%"),
               _sub("Perforación", 27.1, 2), _sub("Maestría de Anomalía", 9.0, 0)]
    s = _syncer(db)
    r1 = s.on_disc_detected(_slot3(_SUBS_A))
    r2 = s.on_disc_detected(_slot3(ruidoso))
    assert r1.disc_id == r2.disc_id
    assert _count(db) == 1


def test_un_disco_MEJORADO_no_se_duplica_por_haber_subido_de_nivel(db):
    """El nivel participa de la identidad. El fixture mantiene `main_valor` fijo a propósito —en
    el juego subiría con el nivel— para que lo único que separe a los dos discos sea el nivel y el
    test no pueda pasar por el motivo equivocado.

    La equivalencia entre un disco y su versión mejorada la resuelve `sync_upgrade`, que SABE que
    hubo una mejora. Acá insertar es lo honesto: adivinar la equivalencia, no."""
    s = _syncer(db)
    r1 = s.on_disc_detected(_slot3(_SUBS_A, nivel=9))
    r2 = s.on_disc_detected(_slot3(_SUBS_A, nivel=15))
    assert r1.disc_id != r2.disc_id
    assert _count(db) == 2


def test_los_gemelos_IRREDUCIBLES_no_se_adivinan_pero_se_avisan(db, caplog):
    """22 pares del inventario real son indistinguibles hasta por identidad completa. El sistema
    no puede saber si el segundo avistamiento es el gemelo o una relectura del primero.

    RNF-02: no se resuelve a la fuerza. Se actualiza uno solo —lo conservador— y se deja constancia
    de que el conteo puede quedar corto, porque un censo que no sabe qué no vio es peor que no
    tener censo."""
    import logging
    con = sqlite3.connect(str(db))
    for _ in range(2):   # dos filas gemelas, ya en la DB
        con.execute(
            "INSERT INTO inventory_discs (set_id, slot, main_stat, main_valor, "
            "sub1, val1, rolls1, sub2, val2, rolls2, sub3, val3, rolls3, sub4, val4, rolls4, nivel) "
            "VALUES (1,3,'DEF',184.0, 'ATK',38.0,1, 'Daño Crítico',9.6,1, "
            "'Perforación',27.0,2, 'Maestría de Anomalía',9.0,0, 15)")
    con.commit(); con.close()
    s = _syncer(db)
    with caplog.at_level(logging.WARNING):
        r = s.on_disc_detected(_slot3(_SUBS_A))
    assert r is not None
    assert _count(db) == 2, "no inventa una tercera fila"
    assert any("ambig" in m.lower() or "gemelo" in m.lower() for m in caplog.messages), \
        "la ambigüedad tiene que quedar registrada, no resolverse en silencio"
