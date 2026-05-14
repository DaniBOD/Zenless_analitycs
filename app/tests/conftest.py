"""
Fixtures compartidos para tests.
DB en memoria con schema mínimo para unit tests (sin depender del archivo .db real).
"""
import os
import sqlite3
import json
import pytest
import sys
from pathlib import Path

# D:\paddle_site contiene numpy 1.26.4 + paddlepaddle 2.6.2 + paddleocr 2.8.1.
# Debe estar al frente de sys.path antes de cualquier `import numpy` para que
# paddle no se rompa contra numpy 2.x del user-site (np.sctypes removido).
_PADDLE_SITE = r"D:\paddle_site"
if os.path.isdir(_PADDLE_SITE) and _PADDLE_SITE not in sys.path:
    sys.path.insert(0, _PADDLE_SITE)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@pytest.fixture
def mem_db():
    """DB SQLite en memoria con tablas mínimas para scoring tests."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE disc_archetypes (
            id INTEGER PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            substats_positivos TEXT,
            substats_perjudiciales TEXT,
            threshold_stock REAL DEFAULT 0.50,
            mains_4 TEXT DEFAULT '[]',
            mains_5 TEXT DEFAULT '[]',
            mains_6 TEXT DEFAULT '[]'
        );
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY,
            nombre TEXT UNIQUE NOT NULL,
            rol TEXT DEFAULT 'Ataque'
        );
        CREATE TABLE agent_score_thresholds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agente_id INTEGER NOT NULL,
            threshold_equip REAL DEFAULT 0.75,
            threshold_upgrade REAL DEFAULT 0.50
        );
        CREATE TABLE agent_substat_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agente_id INTEGER NOT NULL,
            substat TEXT NOT NULL,
            peso REAL NOT NULL
        );
        CREATE TABLE disc_sets (id INTEGER PRIMARY KEY, nombre TEXT);
        CREATE TABLE disc_set_archetype (
            set_id INTEGER,
            archetype_id INTEGER,
            prioridad INTEGER DEFAULT 1
        );
        CREATE TABLE inventory_discs (
            id INTEGER PRIMARY KEY,
            set_id INTEGER, slot INTEGER,
            main_stat TEXT, main_valor REAL,
            sub1 TEXT, val1 REAL, rolls1 INTEGER DEFAULT 0,
            sub2 TEXT, val2 REAL, rolls2 INTEGER DEFAULT 0,
            sub3 TEXT, val3 REAL, rolls3 INTEGER DEFAULT 0,
            sub4 TEXT, val4 REAL, rolls4 INTEGER DEFAULT 0,
            nivel INTEGER DEFAULT 0,
            equipado INTEGER DEFAULT 0,
            agente_asignado INTEGER,
            descartado INTEGER DEFAULT 0,
            score_evaluacion REAL,
            agentes_compatibles TEXT,
            notas TEXT
        );
    """)

    # Seed mínimo — arquetipo ATK_DPS
    con.execute("""INSERT INTO disc_archetypes (id, code, substats_positivos, substats_perjudiciales, mains_4, mains_5, mains_6)
        VALUES (1, 'ATK_DPS',
            '{"Prob. Crítica": 1.0, "Daño Crítico": 1.0, "ATK%": 0.8, "ATK": 0.4, "Perforación": 0.5}',
            '{"DEF%": -0.3, "HP%": -0.2}',
            '["Prob. Crítica", "Daño Crítico", "ATK%", "Maestría de Anomalía", "HP%", "DEF%", "Tasa de Perforación"]',
            '["Bono Daño Físico", "Bono Daño Fuego", "Bono Daño Hielo", "Bono Daño Eléctrico", "Bono Daño Éter", "ATK%", "HP%", "DEF%", "Tasa de Perforación"]',
            '["HP%", "ATK%", "DEF%", "Maestría de Anomalía", "Impacto", "Recarga de Energía"]'
        )
    """)
    con.execute("INSERT INTO disc_sets VALUES (1, 'Test Set')")
    con.execute("INSERT INTO disc_set_archetype VALUES (1, 1, 1)")

    # Agente test
    con.execute("INSERT INTO agents (id, nombre, rol) VALUES (1, 'TestAgent', 'Ataque')")
    con.execute("INSERT INTO agent_score_thresholds (agente_id, threshold_equip, threshold_upgrade) VALUES (1, 0.75, 0.50)")

    con.commit()
    yield con
    con.close()
