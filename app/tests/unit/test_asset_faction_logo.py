"""`faction_logo_path` — el logo de la facción de un PJ (celda del roster, portada del modal).

Los 23 archivos de `Facciones_Logos` no siguen ninguna convención: la mitad en español
(`Hijos_Caledon`, `Cabaña_Terror`), la otra con el prefijo del wiki (`Faction_…_Icon`), y dos
duplicados. Por eso el resolvedor es una TABLA explícita y no una normalización: una regla
mecánica o no resuelve o, peor, resuelve al archivo equivocado.

El test que importa es el de cobertura contra la DB real: una facción nueva (llega con cada patch)
sin logo tiene que fallar **con su nombre**, no aparecer en la UI como un hueco que nadie nota.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from app.core.asset_resolver import FACTIONS_DIR, faction_logo_path

DB = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"

#: Facciones de la DB SIN archivo de logo, a propósito. Agregar una acá es una decisión: se anota
#: por qué falta.
SIN_LOGO = {
    "Covenant of Dayat",   # Remielle Dan (v3.1): no se consiguió el logo todavía
}


def _facciones_db() -> set[str]:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        return {r[0] for r in con.execute("SELECT DISTINCT faccion FROM agents WHERE faccion IS NOT NULL")}
    finally:
        con.close()


def test_cada_faccion_del_roster_tiene_logo_o_esta_declarada_sin_logo():
    faltan = sorted(f for f in _facciones_db() - SIN_LOGO if faction_logo_path(f) is None)
    assert not faltan, f"facciones sin logo (agregar a la tabla o a SIN_LOGO): {faltan}"


def test_los_declarados_sin_logo_siguen_sin_logo():
    """Si alguien suma el archivo de Covenant of Dayat, este test pide sacarlo de SIN_LOGO —
    si no, la lista miente y deja de servir para ver lo que falta."""
    for f in SIN_LOGO:
        assert faction_logo_path(f) is None, f"{f} ya tiene logo: sacarlo de SIN_LOGO"


def test_resuelve_los_nombres_que_no_siguen_ninguna_convencion():
    assert faction_logo_path("Sons of Calydon").name == "Hijos_Caledon.webp"
    assert faction_logo_path("Spook Shack").name == "Cabaña_Terror.webp"
    assert faction_logo_path("Faetón").name == "Faction_Phaethon_Icon.webp"


def test_toda_ruta_devuelta_existe_y_vive_dentro_de_app():
    app_dir = Path(__file__).resolve().parents[2]
    for f in _facciones_db():
        p = faction_logo_path(f)
        if p is not None:
            assert p.exists(), p
            assert app_dir in p.parents and p.parent == FACTIONS_DIR


def test_se_abstiene_en_vez_de_adivinar():
    assert faction_logo_path(None) is None
    assert faction_logo_path("") is None
    assert faction_logo_path("Facción inventada") is None
