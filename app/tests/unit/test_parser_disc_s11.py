"""Parser del panel DETAIL de la pantalla de Desmontaje (S11).

El panel vive a la derecha (xn 0.66-0.97) y tiene **una sola columna** de substats (nombre a la
izquierda, valor a la derecha), así que reusa el motor de S3 igual que `parse_disc_s5` — solo
cambia la banda. Lo único propio es el crop del ROI para el OCR (el panel es chico y OCR-ear el
frame completo dejaría entrar la grilla entera).

Ground-truth transcrito a mano de las 5 capturas de `12_Desmontaje/`. Los casos load-bearing
son Ejemplo_3 y Ejemplo_4: nivel 15 con 4 substats y 3 badges de rolls cada uno — es donde el
parser tiene que leer los `+N` que el juego pinta en naranja al lado del nombre. Ejemplo_4 suma
la trampa de tener **dos substats PV**, uno porcentual (9 %) y uno plano (224): si la
desambiguación por unidad falla, colapsan en uno.

Necesita PaddleOCR → skip si no está.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import cv2
import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[3]
_DIR = REPO / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers" / "12_Desmontaje"
_DB = REPO / "db" / "danibod_zzz_v2.db"


def _load(name: str) -> np.ndarray:
    return cv2.imdecode(np.fromfile(str(_DIR / name), np.uint8), cv2.IMREAD_COLOR)


def _paddle():
    try:
        from app.core.ocr_paddle import PaddleBackend
    except Exception:
        pytest.skip("PaddleOCR no disponible")
    return PaddleBackend()


def _same_set(raw: str, esperado: str) -> bool:
    """El set se compara resuelto contra el catálogo (el OCR rompe tildes)."""
    from app.db.repositories import DiscSetRepo
    con = sqlite3.connect(str(_DB))
    con.row_factory = sqlite3.Row
    try:
        repo = DiscSetRepo(con)
        got, want = repo.resolve_id(raw), repo.resolve_id(esperado)
        return got is not None and got == want
    finally:
        con.close()


# (fixture, set, slot, nivel, main_canon, main_valor, main_unidad, {sub_canon: (valor, rolls)})
_GT = [
    ("Ejemplo_6.png", "Firmamento llameante", 2, 0, "ATK", 79.0, "flat",
     {"DEF%": (4.8, 0), "DEF": (15.0, 0), "Prob. Crítica": (2.4, 0)}),
    # Los mains porcentuales de HP/ATK/DEF canonizan CON el sufijo (`_canon_with_unit`), así que
    # "Ataque 7.5 %" es ATK% y no ATK — el mismo stat plano y el porcentual son distintos.
    ("Ejemplo_2.png", "Firmamento llameante", 5, 0, "ATK%", 7.5, "%",
     {"DEF%": (4.8, 0), "Maestría de Anomalía": (9.0, 0), "HP%": (3.0, 0)}),
    ("Ejemplo_1.png", "Nana a la luz cenicienta", 4, 0, "DEF%", 12.0, "%",
     {"Prob. Crítica": (2.4, 0), "HP": (112.0, 0), "Perforación": (9.0, 0)}),
    ("Ejemplo_3.png", "Salón huracanado", 6, 15, "Recarga de Energía", 60.0, "%",
     {"DEF%": (14.4, 2), "Daño Crítico": (9.6, 1), "HP": (224.0, 1), "Perforación": (9.0, 0)}),
    ("Ejemplo_4.png", "Salón huracanado", 2, 15, "ATK", 316.0, "flat",
     {"Maestría de Anomalía": (18.0, 1), "HP%": (9.0, 2), "ATK%": (3.0, 0), "HP": (224.0, 1)}),
]


@pytest.mark.skipif(not (_DIR / "Ejemplo_1.png").exists(), reason="capturas S11 no presentes")
@pytest.mark.parametrize(
    "name,set_esp,slot,nivel,main,main_val,main_uni,subs_esp",
    _GT, ids=[g[0].replace(".png", "") for g in _GT],
)
def test_panel_detail_campo_por_campo(name, set_esp, slot, nivel, main, main_val, main_uni, subs_esp):
    from app.core.parser_disc_s3 import parse_disc_s11
    d = parse_disc_s11(_load(name), _paddle())

    assert _same_set(d.set_name_raw, set_esp), f"set: leyó {d.set_name_raw!r}"
    assert d.slot == slot, f"slot: {d.slot}"
    assert d.nivel == nivel, f"nivel: {d.nivel}"
    assert d.main_stat_canon == main, f"main: {d.main_stat_canon}"
    assert d.main_valor == pytest.approx(main_val), f"main_valor: {d.main_valor}"
    assert d.main_unidad == main_uni, f"main_unidad: {d.main_unidad}"

    got = {s.nombre_canon: (s.valor, s.rolls) for s in d.subs if s.nombre_canon}
    assert set(got) == set(subs_esp), f"substats: {sorted(got)} vs {sorted(subs_esp)}"
    for canon, (val, rolls) in subs_esp.items():
        assert got[canon][0] == pytest.approx(val), f"{canon} valor: {got[canon][0]}"
        assert got[canon][1] == rolls, f"{canon} rolls: {got[canon][1]}"


@pytest.mark.skipif(not (_DIR / "Ejemplo_4.png").exists(), reason="captura no presente")
def test_los_dos_pv_de_ejemplo_4_no_colapsan():
    """Ejemplo_4 tiene PV plano (224) y PV porcentual (9 %). Si la desambiguación por unidad
    falla, uno pisa al otro y el disco queda con 3 substats en vez de 4."""
    from app.core.parser_disc_s3 import parse_disc_s11
    d = parse_disc_s11(_load("Ejemplo_4.png"), _paddle())
    canons = [s.nombre_canon for s in d.subs]
    assert "HP" in canons and "HP%" in canons, canons
    assert len(d.subs) == 4, canons


@pytest.mark.skipif(not (_DIR / "Ejemplo_3.png").exists(), reason="captura no presente")
def test_rolls_totales_no_superan_el_maximo_fisico():
    """Invariante del juego: un disco no puede tener más de 5 rolls repartidos."""
    from app.core.parser_disc_s3 import parse_disc_s11
    for name in ("Ejemplo_3.png", "Ejemplo_4.png"):
        d = parse_disc_s11(_load(name), _paddle())
        assert sum(s.rolls for s in d.subs) <= 5, name


@pytest.mark.skipif(not (_DIR / "Ejemplo_1.png").exists(), reason="captura no presente")
def test_bench_panel_no_regresiona():
    """Guarda de regresión, no un objetivo.

    Medido en este hardware: el OCR del panel recortado cuesta ~700-900 ms, del mismo orden que
    el crop de S17 (~850 ms documentado). PaddleOCR corre 100 % en CPU y bajar de ahí es
    justamente el trabajo DIFERIDO de `2026-07-10_Futuro_Latencia_GPU_Distribucion.md`, que no
    se retoma hasta cerrar la cobertura de extracción — o sea, hasta después de este feature.

    Con clicks cada 1-2 s eso alcanza para seguir el ritmo, y cuando no alcanza el diseño
    degrada declarando el hueco en vez de mentir. Así que acá se fija un techo que atrapa una
    regresión real (2×) sin convertirse en un test que falla por la carga de la máquina: se toma
    el MÍNIMO de 3 corridas, que mide el costo propio y no la contención."""
    import time
    from app.core.parser_disc_s3 import parse_disc_s11
    ocr = _paddle()
    fr = _load("Ejemplo_1.png")
    parse_disc_s11(fr, ocr)                 # warmup (carga de modelos)
    muestras = []
    for _ in range(3):
        t0 = time.perf_counter()
        parse_disc_s11(fr, ocr)
        muestras.append((time.perf_counter() - t0) * 1000)
    assert min(muestras) < 1600, f"min={min(muestras):.0f} ms de {[f'{m:.0f}' for m in muestras]}"
