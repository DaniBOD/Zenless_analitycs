"""`engine_icon_path` — el ícono de un W-Engine para la card de armas de la pantalla en vivo.

El directorio tiene DOS convenciones de nombre conviviendo: los originales del wiki
(`W-Engine_<NombreEN>.webp`, 54 archivos) y slugs en español renombrados a mano (32). El orden de
resolución NO es arbitrario:

1. **el nombre inglés primero** — los originales vienen del wiki y son la fuente confiable;
2. **después el slug español**, que lo renombró una sesión pasada y tiene al menos un mapeo dudoso
   en su README (`camara_acorazada` figura como *Bashful Demon* cuando la DB dice *The Vault*).

Y si ninguno resuelve, **devuelve None**: la card dibuja un hueco neutro. Adivinar el ícono de un
arma es peor que no mostrarlo, y hay una familia entera (`W-Engine_29_*`) cuya correspondencia con
los nombres en español nadie verificó todavía.

Cobertura: **40 de las 40 armas distintas del inventario** desde el 2026-09-15, cuando Daniel
descargó los 3 íconos que faltaban (Sol Exuvia, Boisterous Echoes, Ice-Jade Teapot). Antes: 37/40
tras las migs `_33` y `_34` (al 2026-09-12 se había escrito que eran 6 y que a todas les faltaba el
nombre: estaba mal contado).
"""
from __future__ import annotations

from pathlib import Path

from app.core.asset_resolver import engine_icon_path, ENGINES_DIR


def test_resuelve_por_el_nombre_ingles():
    """El camino principal: el original del wiki."""
    p = engine_icon_path("Rotor de cañón", "Cannon Rotor")
    assert p is not None and p.name == "W-Engine_Cannon_Rotor.webp"
    assert p.exists()


def test_resuelve_por_el_slug_espanol_cuando_no_hay_nombre_ingles():
    """`Tránsito herciano` tiene `nombre_en` NULL en la DB y su archivo es el slug ES."""
    p = engine_icon_path("Tránsito herciano", None)
    assert p is not None and p.name == "transito_herciano.webp"
    assert p.exists()


def test_el_nombre_largo_matchea_por_prefijo():
    """El catálogo se renombró a los nombres completos (mig `_28`) y los archivos quedaron con el
    nombre corto: `Cilindro neumático de Bigger` → `cilindro_neumatico.webp`."""
    p = engine_icon_path("Cilindro neumático de Bigger", None)
    assert p is not None and p.name == "cilindro_neumatico.webp"


def test_el_prefijo_respeta_los_limites_de_palabra():
    """`cuter.webp` es el slug más corto (5 letras). No puede reclamar un nombre que sólo EMPIEZA
    con esas letras sin cortar en un borde de palabra, o un archivo corto se queda con todo."""
    assert engine_icon_path("Cuteria mecanica", None) is None


def test_se_abstiene_en_vez_de_adivinar():
    """Un arma que no tiene ícono devuelve None, y la card dibuja un hueco."""
    assert engine_icon_path("Arma que no existe", "Weapon That Does Not Exist") is None
    assert engine_icon_path(None, None) is None
    assert engine_icon_path("", "") is None


def test_la_ruta_cae_dentro_de_app():
    """Mismo invariante que `test_asset_paths_dentro_de_app`, visto desde esta función."""
    app_dir = Path(__file__).resolve().parents[2]          # .../app
    assert app_dir in ENGINES_DIR.parents
    p = engine_icon_path("Rotor de cañón", "Cannon Rotor")
    assert p is not None and app_dir in p.parents


def test_no_devuelve_los_pendientes():
    """Los `_pendiente_*.webp` son archivos sin confirmar a qué arma corresponden: no se sirven."""
    for p in ENGINES_DIR.glob("_pendiente_*.webp"):
        nombre = p.stem.replace("_pendiente_", "").replace("_", " ")
        resuelto = engine_icon_path(nombre, None)
        assert resuelto is None or not resuelto.name.startswith("_pendiente"), (
            f"{nombre} resolvió a un archivo pendiente de confirmación: {resuelto}"
        )


def test_cada_arma_del_inventario_real_tiene_icono():
    """Cobertura contra la DB real. Un arma nueva (llega con cada patch) sin ícono tiene que fallar
    con su nombre, no aparecer en la pantalla Armas como un hueco que nadie nota. Si falta el archivo
    a propósito, se declara en SIN_ICONO con el motivo."""
    import sqlite3

    SIN_ICONO: set[str] = set()   # 40/40 desde el 2026-09-15
    db = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        filas = con.execute(
            "SELECT DISTINCT w.nombre, w.nombre_en FROM inventory_weapons i "
            "JOIN weapons w ON w.id = i.weapon_id WHERE i.descartado = 0").fetchall()
    finally:
        con.close()
    faltan = sorted(n for n, en in filas if n not in SIN_ICONO and engine_icon_path(n, en) is None)
    assert not faltan, f"armas del inventario sin ícono (agregar el archivo o declararlas): {faltan}"
