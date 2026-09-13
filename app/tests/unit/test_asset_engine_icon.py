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

Cobertura medida al 2026-09-12: **34 de las 40 armas distintas del inventario**. Las 6 que faltan
(`Última cena`, `Inocencia sacrificada`, `Caldero ardiente`, `Ecos bulliciosos`, `Sol exuvia`,
`Tetera esmeraldina`) **tienen el archivo**; lo que les falta es el `nombre_en` en la DB. Es deuda
de datos, no de interfaz.
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
