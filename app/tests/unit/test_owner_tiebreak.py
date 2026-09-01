"""Desempate de dueño por CONTEXTO (build) — `OwnerTiebreaker`.

Cuando el matcher de badges se abstiene por margen chico entre look-alikes, el build
(set firma 4pc/2pc en la DB) confirma el top-1 visual SOLO si lo distingue del top-2.
Tests herméticos: DB sqlite temporal con una tabla `agents` mínima + un resolutor de
set fake (no depende del fuzzy real de disc_sets). RNF-02: cero asignaciones MAL.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.core.owner_tiebreak import OwnerTiebreaker


# set_id de juguete: 100=Punk (firma de César), 200=Floración (compartido), 300=Monarca.
_SET_BY_NAME = {"punk": 100, "floracion": 200, "monarca": 300}


def _resolve_set_id_fake(disc) -> int | None:
    raw = (getattr(disc, "set_name_raw", "") or "").lower()
    for key, sid in _SET_BY_NAME.items():
        if key in raw:
            return sid
    return None


class _Disc:
    def __init__(self, set_name_raw, slot=None, main=None):
        self.set_name_raw = set_name_raw
        self.set_name_canon = None
        self.slot = slot
        self.main_stat_canon = main
        self.main_stat_raw = main


@pytest.fixture
def tb(tmp_path: Path) -> OwnerTiebreaker:
    db = tmp_path / "roster.db"
    con = sqlite3.connect(str(db))
    con.executescript(
        """
        CREATE TABLE agents (id INTEGER PRIMARY KEY, nombre TEXT, set_4p_id INT, set_2p_id INT);
        INSERT INTO agents VALUES (1, 'César', 100, 999);   -- corre Punk (4p)
        INSERT INTO agents VALUES (2, 'Lucía', 200, 100);   -- corre Floración + Punk (2p)
        INSERT INTO agents VALUES (3, 'Velina', NULL, NULL); -- recién onboardeada, sin build
        INSERT INTO agents VALUES (4, 'Sporos', 200, NULL); -- corre Floración
        INSERT INTO agents VALUES (5, 'Seth', 999, NULL);    -- sin Monarca de firma
        INSERT INTO agents VALUES (6, 'Yanagi', 999, NULL);

        CREATE TABLE inventory_discs (set_id INT, slot INT, main_stat TEXT, agente_asignado INT);
        -- Seth tiene un Monarca s1 HP equipado (filler, NO es su set firma).
        INSERT INTO inventory_discs VALUES (300, 1, 'HP', 5);
        -- Lucía también tiene un Monarca s1 HP (caso ambiguo entre dos dueños).
        INSERT INTO inventory_discs VALUES (300, 1, 'HP', 2);
        -- disco sin dueño: NO debe entrar al índice.
        INSERT INTO inventory_discs VALUES (300, 1, 'HP', NULL);
        """
    )
    con.commit()
    con.close()
    return OwnerTiebreaker(db_path=db, resolve_set_id=_resolve_set_id_fake)


def test_confirma_top1_si_distingue(tb):
    # Punk distingue a César (lo corre) de Velina (sin build) → confirma César.
    r = tb.resolve(_Disc("Punk Primitivo"), [("César", 0.10), ("Velina", 0.13)])
    assert r == ("César", "build")


def test_promueve_top2_con_margen_infimo(tb):
    # Caso real César/Punk s4: top-1 Corin (sin Punk) y top-2 César (corre Punk) casi
    # empatados (margen 0.02 ≤ 0.03) → promueve César por 'build_top2'.
    r = tb.resolve(_Disc("Punk Primitivo"), [("Velina", 0.10), ("César", 0.12)])
    assert r == ("César", "build_top2")


def test_no_promueve_top2_con_margen_grande(tb):
    # Si el empate NO es ínfimo (margen 0.10 > 0.03), NO se promueve el top-2 aunque el
    # contexto lo corrobore: el matcher visual mandó con holgura.
    assert tb.resolve(_Disc("Punk Primitivo"), [("Velina", 0.10), ("César", 0.20)]) is None


def test_abstiene_si_ambos_corren_el_set(tb):
    # Floración la corren Sporos y Lucía → no distingue → abstención.
    assert tb.resolve(_Disc("Floración del alba"), [("Sporos", 0.10), ("Lucía", 0.13)]) is None


def test_abstiene_si_top2_tambien_corre_punk(tb):
    # Punk: top-1 César (4p) y top-2 Lucía (2p) ambos lo corren → no distingue.
    assert tb.resolve(_Disc("Punk Primitivo"), [("César", 0.10), ("Lucía", 0.13)]) is None


def test_abstiene_si_ninguno_corre_el_set(tb):
    # Monarca (filler): ni César ni Velina lo tienen como firma → abstención.
    assert tb.resolve(_Disc("Monarca del Pináculo"), [("César", 0.10), ("Velina", 0.13)]) is None


def test_abstiene_si_set_no_resuelve(tb):
    assert tb.resolve(_Disc("basura ocr xyz"), [("César", 0.10), ("Velina", 0.13)]) is None


def test_abstiene_con_menos_de_dos_candidatos(tb):
    assert tb.resolve(_Disc("Punk Primitivo"), [("César", 0.10)]) is None
    assert tb.resolve(_Disc("Punk Primitivo"), []) is None


def test_acentos_y_normalizacion(tb):
    # Los nombres del matcher pueden venir con acentos/casing distintos; _norm_key alinea.
    assert tb.resolve(_Disc("Punk Primitivo"), [("cesar", 0.10), ("velina", 0.13)]) == ("cesar", "build")


# --- Señal 2: asignación existente en inventory_discs (filler / slots 1-3) -----------

def test_equip_rescata_filler_por_asignacion(tb):
    # Monarca s1 HP (filler, NO es set firma de nadie acá): Seth YA tiene uno asignado y
    # Yanagi no → confirma Seth por 'equip'. Modela el caso real Seth/Nana s1.
    d = _Disc("Monarca del Pináculo", slot=1, main="HP")
    assert tb.resolve(d, [("Seth", 0.04), ("Yanagi", 0.06)]) == ("Seth", "equip")


def test_equip_promueve_top2_con_margen_infimo(tb):
    # Seth (dueño real, tiene el disco) como top-2 casi empatado (margen 0.02) → 'equip_top2'.
    d = _Disc("Monarca del Pináculo", slot=1, main="HP")
    assert tb.resolve(d, [("Yanagi", 0.04), ("Seth", 0.06)]) == ("Seth", "equip_top2")


def test_equip_no_promueve_top2_con_margen_grande(tb):
    # Mismo Seth top-2 con el disco, pero margen 0.10 > 0.03 → NO se promueve.
    d = _Disc("Monarca del Pináculo", slot=1, main="HP")
    assert tb.resolve(d, [("Yanagi", 0.04), ("Seth", 0.14)]) is None


def test_equip_abstiene_si_ambos_tienen_el_disco(tb):
    # Seth y Lucía tienen ambos un Monarca s1 HP → no distingue → abstención.
    d = _Disc("Monarca del Pináculo", slot=1, main="HP")
    assert tb.resolve(d, [("Seth", 0.04), ("Lucía", 0.06)]) is None


def test_equip_ignora_discos_sin_dueno(tb):
    # El Monarca s1 HP sin dueño no entra al índice → no aporta corroboración espuria.
    # (Seth sí tiene uno → confirma; la fila NULL no cuenta como "Yanagi tiene".)
    d = _Disc("Monarca del Pináculo", slot=1, main="HP")
    assert tb.resolve(d, [("Seth", 0.04), ("Yanagi", 0.06)]) == ("Seth", "equip")


def test_equip_main_distinto_no_matchea(tb):
    # Mismo set+slot pero OTRO main (DEF) → fingerprint distinto → sin señal equip.
    d = _Disc("Monarca del Pináculo", slot=1, main="DEF")
    assert tb.resolve(d, [("Seth", 0.04), ("Yanagi", 0.06)]) is None


# --- Frescura: mark_dirty() recarga los índices (cambios de build en vivo, p.ej. Velina) ---

def test_mark_dirty_recarga_indices(tb):
    d = _Disc("Monarca del Pináculo", slot=1, main="HP")
    # Velina (sin build ni disco) no se puede desempatar todavía.
    assert tb.resolve(d, [("Velina", 0.04), ("Yanagi", 0.06)]) is None
    # Simula que el usuario le equipó un Monarca s1 HP a Velina (id 3) y se persistió.
    con = sqlite3.connect(str(tb._db_path))
    con.execute("INSERT INTO inventory_discs VALUES (300, 1, 'HP', 3)")
    con.commit()
    con.close()
    # Sin mark_dirty, el índice viejo (foto del arranque) NO lo ve.
    assert tb.resolve(d, [("Velina", 0.04), ("Yanagi", 0.06)]) is None
    # Tras mark_dirty, el próximo resolve recarga y la señal equip confirma a Velina.
    tb.mark_dirty()
    assert tb.resolve(d, [("Velina", 0.04), ("Yanagi", 0.06)]) == ("Velina", "equip")


# --- Promoción del top-2 con un censo abierto (2026-09-01) ------------------------------------
#
# El desempate lee la DB como si fuera una foto TERMINADA: "el top-1 no corre este set / no
# tiene un disco así" es una afirmación que sólo vale si lo que la DB sabe del top-1 está
# completo. Durante una pasada de censo eso es falso por construcción — la tabla se está
# llenando— y la ausencia significa "todavía no llegué", no "no lo tiene". CONFIRMAR al top-1
# visual con esa evidencia es tolerable (la vista ya lo puso primero); DARLO VUELTA no, porque
# entonces la decisión la toma entera una ausencia.

def test_con_censo_abierto_no_promueve_el_top2(tb):
    """Mismo caso que `test_promueve_top2_con_margen_infimo`, pero con la pasada abierta."""
    r = tb.resolve(_Disc("Punk Primitivo"), [("Velina", 0.10), ("César", 0.12)],
                   permitir_top2=False)
    assert r is None


def test_con_censo_abierto_sigue_confirmando_el_top1(tb):
    """La confirmación del top-1 NO se toca: no invierte lo que la vista ya decidió."""
    r = tb.resolve(_Disc("Punk Primitivo"), [("César", 0.10), ("Velina", 0.13)],
                   permitir_top2=False)
    assert r == ("César", "build")
