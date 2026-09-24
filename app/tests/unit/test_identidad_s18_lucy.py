"""QA en vivo del 2026-09-24: Lucy no se identificaba y su ficha se llegó a guardar en la fila de Grace.

1. La ficha de Lucy dice "Luciana de Montefio". La identificaba la capa POR STATS, que desde el
   rebuild de la DB (stats a 0) no tiene con qué comparar → nombre None → no se guardaba nunca.
2. A las 00:21:22 una ficha con banner Soporte/Fuego (la de Lucy) se guardó en Grace, que es
   Anomalía/Eléctrico. Se sobrescribió con lo correcto 2 s después solo porque Daniel pasó por
   Grace. La última defensa está en el guardado: si el elemento de la ficha contradice al del PJ,
   no se escribe.
"""
from __future__ import annotations

import sqlite3

import numpy as np
import pytest

from app.core import parser_agent_stats as p
from app.core.parser_agent_stats import AgentStatsParsed
from app.core.sync_agent_stats import AgentStatsSyncer
from app.tests.unit.test_optimizer_build_actual import REAL_DB_PATH

#: OCR full-frame de Paddle sobre el S18 de Lucy en vivo (2026-09-24), tal cual.
OCR_LUCY = (
    "Ciudad 4} Hijos de Calidón Luciana de Montefio HOLLOWS ARE AN AI GUIDE THE INTERNAL SPA u c y "
    "Nivel 60 MAX igneo MAuxiliar PV 12 392 Ataque 1774 Defensa 1003 Impacto 86 Probabilidad de "
    "24.2 % Dano Critico 83.6 % Critico Tasa de Anomalia 94 Maestria de Anomalia 120 0 % "
    "Recuperación de Tasa de Perforacion 1.56 Energia Atributos secundarios Preparaciön activos "
    "para el combate CINENA 6/6 Atributos base Habilidades Eqguipamiento"
)


class _Ocr:
    def text(self, img, psm=None):
        return ("", 0.0) if psm == 7 else (OCR_LUCY, 0.97)


@pytest.fixture
def roster_fresco(monkeypatch):
    """El roster se cachea por proceso: se recarga para que entre el alias."""
    if not REAL_DB_PATH.exists():
        pytest.skip("sin DB de dominio")
    monkeypatch.setattr(p, "_ROSTER_CACHE", None)
    monkeypatch.setattr(p, "_NO_POSEIDOS_CACHE", None)
    yield
    p._ROSTER_CACHE = None
    p._NO_POSEIDOS_CACHE = None


def test_el_nombre_en_pantalla_de_lucy_resuelve_a_lucy(roster_fresco):
    assert p._match_agent(p._name_region(OCR_LUCY), "Soporte", "Fuego")[0] == "Lucy"


def test_la_ficha_de_lucy_sale_identificada(roster_fresco):
    r = p.parse_agent_stats(np.zeros((1440, 2560, 3), np.uint8), _Ocr())
    assert r.agente_nombre == "Lucy" and r.elemento == "Fuego"
    assert p.stats_completos(r), p.missing_stat_labels(r)


#: OCR full-frame de Paddle sobre el S18 de Nekomata en vivo (2026-09-24): "Nekomiya Mana".
OCR_NEKOMATA = (
    "1 Ciudad 88& g& $ Liebres Astutas Nekomiya Mana OF THIN AIR SWALLOWING NGEROUS MUTANT CREATUR "
    "Atacante Nivel 60 MAX Fisico PV 11678 Ataque 1621 Defensa 941 Impacto 92 Probabilidad de 24.2 % "
    "Dano Critico 142.8 % Critico Tasa de Anomalia 97 Maestria de Anomalia 105 0 % Recuperación de "
    "Tasa de Perforación 1.2 Energia"
)


def test_el_nombre_en_pantalla_de_nekomata_resuelve_a_nekomata(roster_fresco):
    assert p._match_agent(p._name_region(OCR_NEKOMATA), None, "Físico")[0] == "Nekomata"


def test_billy_kid_estelar_es_billy_estelar_aunque_el_banner_diga_ataque(roster_fresco):
    """QA 2026-09-24: "Billy Kid Estelar" contiene las palabras de Billy y de Billy Estelar. El
    banner, mal recortado, leyó "Ataque" (la etiqueta del stat) y el bono de rol daba Billy."""
    assert p._match_agent("Liebres Astutas Billy Kid Estelar", "Ataque", "Físico")[0] == "Billy Estelar"


def test_billy_kid_sigue_siendo_billy(roster_fresco):
    assert p._match_agent("Liebres Astutas Billy Kid", "Ataque", "Físico")[0] == "Billy"


def test_el_alias_no_se_lleva_otros_nombres(roster_fresco):
    """El alias es de Lucy: no puede volver 'Lucía' (otra PJ, Éter) en Lucy."""
    assert p._match_agent("Lucía", None, None)[0] == "Lucía"


# --- la última defensa: el guardado ------------------------------------------------------------

@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.delenv("DANIBOD_READONLY", raising=False)
    ruta = tmp_path / "t.db"
    con = sqlite3.connect(ruta)
    con.executescript("""
        CREATE TABLE agents (id INTEGER PRIMARY KEY, nombre TEXT UNIQUE NOT NULL, elemento TEXT,
            rol TEXT,
            nivel INTEGER, pv INTEGER, ataque INTEGER, defensa INTEGER, impacto INTEGER,
            prob_critico REAL, dano_critico REAL, tasa_anomalia INTEGER, maestria_anomalia INTEGER,
            tasa_perforacion REAL, rec_energia REAL, protected_build INTEGER NOT NULL DEFAULT 0);
        INSERT INTO agents (id, nombre, elemento, rol) VALUES (41, 'Grace', 'Eléctrico', 'Anomalía');
        INSERT INTO agents (id, nombre, elemento, rol) VALUES (12, 'Billy', 'Físico', 'Ataque');
        INSERT INTO agents (id, nombre, elemento, rol)
            VALUES (47, 'Billy Estelar', 'Físico', 'Disruptivos');
    """)
    con.commit()
    con.close()
    return ruta


def _ficha(elemento):
    return AgentStatsParsed(agente_nombre="Grace", elemento=elemento, nivel=60, pv=12392,
                            ataque=1774, defensa=1003)


def _pv(ruta):
    con = sqlite3.connect(ruta)
    try:
        return con.execute("SELECT pv FROM agents WHERE nombre='Grace'").fetchone()[0]
    finally:
        con.close()


def test_una_ficha_de_otro_elemento_no_se_guarda_en_el_pj(db):
    """Lo de las 00:21:22: la ficha de Lucy (Fuego) resuelta como Grace (Eléctrico)."""
    assert AgentStatsSyncer(db).sync(_ficha("Fuego")) is None
    assert _pv(db) is None


def test_una_ficha_de_su_elemento_si_se_guarda(db):
    assert AgentStatsSyncer(db).sync(_ficha("Eléctrico")) and _pv(db) == 12392


def test_sin_elemento_leido_no_se_veta(db):
    """Si el banner no se leyó no hay contradicción: se guarda (B2, no borrar por ausencia)."""
    assert AgentStatsSyncer(db).sync(_ficha(None)) and _pv(db) == 12392


def _estelar(nombre):
    """La ficha de Billy Estelar: Fuerza Bruta, exclusiva de los Disruptivos."""
    return AgentStatsParsed(agente_nombre=nombre, elemento="Físico", nivel=60, pv=20573,
                            ataque=2043, defensa=689, fuerza_bruta=2669, acumulacion_adrenalina=2)


def _pv_de(ruta, nombre):
    con = sqlite3.connect(ruta)
    try:
        return con.execute("SELECT pv FROM agents WHERE nombre=?", (nombre,)).fetchone()[0]
    finally:
        con.close()


def test_una_ficha_de_disruptivo_no_se_guarda_en_un_pj_de_ataque(db):
    """Lo de las 00:40:18 y 00:47:58: la ficha de Billy Estelar resuelta como Billy."""
    assert AgentStatsSyncer(db).sync(_estelar("Billy")) is None
    assert _pv_de(db, "Billy") is None


def test_la_ficha_de_disruptivo_si_se_guarda_en_su_pj(db):
    assert AgentStatsSyncer(db).sync(_estelar("Billy Estelar")) and _pv_de(db, "Billy Estelar") == 20573


def test_guardar_refresca_el_roster_de_la_identificacion(db, monkeypatch):
    """Con la foto del arranque, la fila mal escrita de Billy "reconocía" la ficha de Estelar."""
    monkeypatch.setattr(p, "_ROSTER_CACHE", [{"nombre": "viejo"}])
    assert AgentStatsSyncer(db).sync(_ficha("Eléctrico"))
    assert p._ROSTER_CACHE is None
