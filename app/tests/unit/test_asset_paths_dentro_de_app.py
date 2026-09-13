"""Todo directorio de imágenes que la app lee tiene que llegar al `.exe`.

Existe por un bug que estuvo vivo sin que nadie lo viera: `SetBadgeMatcher` carga sus referencias
desde `Set-Discos_Package_Logo`, que vivía en `Documentacion/` y **el spec de PyInstaller no
copiaba**. En el `.exe` el matcher de sets por badge arrancaba con **0 referencias, en silencio**.

Es la regla D1 de las prácticas (*todo lo que la app lee vive dentro de `app/`*) y ya había fallado
dos veces antes — `farm_nodes.toml` en agosto y los baselines de badges al día siguiente. El propio
`main.spec` lo tiene documentado. La lección no se había aplicado a los assets de interfaz.

Por qué un test y no un comentario: **en desarrollo la ruta vieja funciona igual**. Un
`Documentacion/...` resuelto con `parents[2]` anda perfecto desde el repo y sólo muere empaquetado,
que es cuando ya no hay nadie mirando. El único momento en que se puede detectar es acá.

Los dos invariantes son distintos a propósito:

- los assets de **interfaz** viven dentro de `app/resources/`, que el spec copia entera (así un
  recurso nuevo entra sin tocar el spec — enumerar carpeta por carpeta es lo que falló tres veces);
- cualquier otro directorio que la app lea y esté afuera **tiene que estar nombrado en el spec**.
  `Pj_stats/` es el único caso legítimo hoy: son 6 MB de fallback de avatares, no son de interfaz,
  y el spec los enumera.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.core import asset_resolver as AR

APP_DIR = Path(AR.__file__).resolve().parents[1]        # .../app
REPO_ROOT = APP_DIR.parent
SPEC = REPO_ROOT / "app" / "build" / "main.spec"

# Los directorios de imágenes de INTERFAZ. Se enumeran a mano y no por introspección: la lista es
# el contrato, y si alguien agrega una constante nueva que apunta afuera, el segundo test lo caza.
DIRS_DE_INTERFAZ = (
    "SET_LOGOS_DIR",
    "SET_BADGES_DIR",
    "SPLASH_ARTS_DIR",
    "ENGINES_DIR",
    "FACTIONS_DIR",
)


def test_los_assets_de_interfaz_viven_dentro_de_app():
    """Cada carpeta de imágenes de la UI cuelga de `app/resources/`, que el bundle copia entera."""
    ui_assets = APP_DIR / "resources" / "ui_assets"
    for nombre in DIRS_DE_INTERFAZ:
        d = getattr(AR, nombre)
        assert ui_assets in d.parents or d == ui_assets, (
            f"{nombre} = {d}\n"
            f"Tiene que colgar de {ui_assets}. Afuera de app/ anda en desarrollo y muere "
            f"empaquetado (D1)."
        )


def test_todo_directorio_que_la_app_lee_llega_al_exe():
    """El invariante fuerte: o está dentro de `app/`, o el spec lo nombra explícitamente.

    Este es el test que habría cazado el bug de `Set-Discos_Package_Logo`.
    """
    spec_txt = SPEC.read_text(encoding="utf-8")
    candidatos = {
        nombre: valor
        for nombre, valor in vars(AR).items()
        if nombre.endswith("_DIR") and isinstance(valor, Path)
    }
    assert candidatos, "no se encontró ninguna constante *_DIR en asset_resolver"

    for nombre, d in candidatos.items():
        if APP_DIR in d.parents:
            continue        # dentro de app/ → cubierto por la copia de la carpeta entera
        # Afuera: el spec tiene que nombrar el último tramo de la ruta.
        hoja = d.name
        assert re.search(rf'["\']{re.escape(hoja)}["\']', spec_txt) or f'"{hoja}"' in spec_txt, (
            f"{nombre} = {d}\n"
            f"Está afuera de app/ y `{hoja}` no aparece en {SPEC.name}. En el .exe ese directorio "
            f"no existe y lo que lo lea va a encontrar 0 archivos, sin error."
        )
