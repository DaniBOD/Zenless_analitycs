"""Resolvedor difuso de nombres de set: la señal que discrimina es el MARGEN, no el ratio.

Durante el censo del 2026-08-30, 18 detecciones de 433 no persistieron por dos lecturas que
el resolvedor nunca aceptaba: `Melodia Faett` (ratio 0.8148) y `Metalcolmilluda (i)` (0.8485),
las dos por debajo del cutoff absoluto de 0.86 y las dos INEQUÍVOCAS — el segundo candidato
estaba a 0.28-0.36 de distancia. Es el mismo error estructural que el guard de identidad: un
piso sobre el primer candidato mide otra cosa que la ambigüedad.

Los números salieron de medir contra dos corpus (ver `tools/measure_set_resolver.py`):
el de campo (89 lecturas reales del log del censo) y uno adversario de 3789 corrupciones
sintéticas de los 30 nombres del catálogo. En el barrido, `MAL = 0` en todas las
combinaciones y el rescate viene entero de bajar el cutoff; el margen es la guarda de
ambigüedad que se paga con abstenciones (0.12 → 7 de 3789; 0.15 → 22, y entre ellas la
familia `metal caótico`, que compite con `metal eléctrico` a 0.1474).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.db.repositories import DiscSetRepo

_DB = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"


@pytest.fixture(scope="module")
def repo():
    if not _DB.exists():
        pytest.skip("DB de dominio no presente")
    con = sqlite3.connect(f"file:{_DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        yield DiscSetRepo(con)
    finally:
        con.close()


def _id(repo: DiscSetRepo, nombre: str) -> int:
    sid = repo.get_id_by_name(nombre)
    assert sid, f"el catálogo no tiene {nombre!r}"
    return sid


# --- lo que el cutoff absoluto tiraba (las 3 lecturas reales del censo) ----------------------

@pytest.mark.parametrize("lectura, esperado", [
    ("Melodia Faett", "Melodía de Faetón"),          # 15 detecciones, ratio 0.8148, margen 0.3603
    ("Metalcolmilluda (i)", "Metal Colmilludo"),     #  3 detecciones, ratio 0.8485, margen 0.2771
    ("Nana cenicienta", "Nana a la luz cenicienta"), #  1 detección,  ratio 0.8235, margen 0.4532
])
def test_rescata_lecturas_inequivocas_del_censo(repo, lectura, esperado):
    assert repo.resolve_id(lectura) == _id(repo, esperado)


# --- lo que tiene que seguir rechazando (control negativo del mismo log) ---------------------

@pytest.mark.parametrize("basura", [
    "'Volver a intentar 0/60'",   # ratio 0.3784, margen 0.0147
    "'OBSIDIAN DIVISION'",        # ratio 0.4615, margen 0.0373
    "",
])
def test_rechaza_texto_que_no_es_un_set(repo, basura):
    assert repo.resolve_id(basura) is None


# --- la guarda de ambigüedad: dos sets distintos empatados ⇒ abstención -----------------------

def test_abstiene_si_dos_sets_empatan_dentro_del_margen(repo):
    """Con un margen chico a propósito, una lectura entre dos sets no elige ninguno.

    `metal eléctrico` y `metal caótico` son el par más parecido del catálogo (0.7692 entre
    sí): es el caso donde el margen tiene que mandar por encima de un ratio alto."""
    lectura = "metalcatoico"          # transposición: 0.9167 al caótico, margen 0.1474
    assert repo.resolve_id(lectura, margin=0.20) is None
    assert repo.resolve_id(lectura) == _id(repo, "Metal Caótico")


def test_el_margen_mira_todo_el_catalogo_no_solo_el_top_3(repo):
    """El competidor cercano puede no estar entre los 3 primeros por encima del cutoff.

    La versión anterior pedía los candidatos con `get_close_matches(n=3, cutoff=...)` y sólo
    miraba ESA lista, así que un rival a distancia de margen ranqueado 4º era invisible. Con
    un cutoff bajo entran muchos candidatos y la abstención tiene que seguir saliendo."""
    assert repo.resolve_id("metalcatoico", cutoff=0.10, margin=0.20) is None
