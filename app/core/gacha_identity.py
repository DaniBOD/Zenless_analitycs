"""Identidad de las recompensas de la grilla de sintonización (S28).

La rareza del tile ya se lee con altísima fiabilidad por la banda de color del badge (medido
70/70 sobre los 7 grids). Este módulo usa esa rareza como **filtro de candidatos**, que resultó
ser la mejor palanca disponible: un tile rango B solo puede ser un W-Engine rango B, y un tile
rango A no puede ser una agente rango S. Restringir el pool por rareza bajó las abstenciones de
27 % a 17 % y sacó de cuajo los errores más groseros (esferas B matcheando `Street_Superstar` y
`Steel_Cushion`, que son rango A).

ESTADO MEDIDO (2026-07-29, sobre los 7 grids de 3.1):

  ✔ W-Engines rango B: 60 tiles, **90 % nombrados**, 10 % abstenidos.
    Verificado a ojo par-a-par (recorte vs referencia): los nombrados se ven correctos.

  ✘ AGENTES: NO FUNCIONA. Se probaron tres caminos y ninguno identifica:
      1. descriptor contra `avatar_refs/` (recortes circulares de cara) → márgenes 0.02–0.05;
      2. descriptor contra `splash_arts/*-ico.webp` (busto completo) → ídem;
      3. NCC multi-escala contra los `-ico` → gaps de 0.002–0.029.
    El caso de control es un tile que a ojo es Piper (rubia, ojos verdes, guiñando): ninguno de
    los tres la pone primera. El nombre además CAMBIA según el encuadre del recorte, que es la
    firma de que se está midiendo ruido y no identidad.

    Por qué: el arte del tile es el mismo personaje pero con otro render, otra escala y sobre
    una tarjeta de color distinto según la rareza. El propio `AvatarMatcher` documenta que su
    librería es "HÍBRIDA: se siembra con los `-ico` y se puede pisar con recortes in-game
    cosechados" — o sea que el arte oficial como única semilla ya había resultado insuficiente
    antes, para los badges de S17. Acá pasa lo mismo.

    CAMINO: cosechar recortes de tiles reales durante el x10, etiquetarlos contra el historial
    de sintonización (que da los nombres en texto, gratis y repetible) y usarlos como
    referencia vía `AvatarMatcher.add_reference`. Hasta entonces el agente se reporta como
    "agente sin identificar", NUNCA con un nombre adivinado (RNF-02).

Display-only.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.core.avatar_descriptor import AvatarMatcher, build_name_map
from app.core.parser_gacha_result import GachaTile, crop_tile_art

log = logging.getLogger(__name__)

_REPO = Path(__file__).resolve().parent.parent.parent
AGENT_REFS_DIR = _REPO / "app" / "resources" / "avatar_refs"
ENGINE_REFS_DIR = _REPO / "app" / "resources" / "engine_refs"
_DB = _REPO / "db" / "danibod_zzz_v2.db"

# Prefijo de los íconos de W-Engine rango B en `Engines_icons`. Los 15 archivos `W-Engine_29_*`
# (Alpha, Arrow, Base, Bravo, Charlie, Cobalt, Decrescent, Hatchet, Inflection, Mark_I/II/III,
# Noviluna, Pleniluna, Revolver) son exactamente las "esferas" que llenan las tiradas.
_B_PREFIX = "29_"

# Gate de abstención para engines. Calibrado sobre los 60 tiles B: la mediana del margen es
# 0.115 y la cola mala está por debajo de 0.04. Se mantiene el default del matcher; lo que
# cambia el resultado es el filtro por rareza, no aflojar el gate.
_ENGINE_MIN_CONF = 0.45
_ENGINE_MIN_MARGIN = 0.04

# Gate para agentes: deliberadamente INALCANZABLE mientras la librería sea solo arte oficial.
# No es un número tuneado: es la forma explícita de decir "todavía no sabemos identificar
# agentes". Se baja a valores normales recién cuando la librería tenga recortes in-game.
_AGENT_MIN_CONF = 0.95
_AGENT_MIN_MARGIN = 0.30


@dataclass(frozen=True)
class TileIdentity:
    """Qué es un tile. `name` None = el sistema se abstiene (no es un error)."""
    kind: str                 # 'agente' | 'engine' | 'incierto'
    name: str | None
    conf: float
    margin: float

    @property
    def display(self) -> str:
        if self.name:
            return self.name
        return "agente sin identificar" if self.kind == "agente" else "sin identificar"


def _agent_rangos() -> dict[str, str]:
    """nombre de agente → rango ('S'/'A'/'∞'). Vacío si la DB no está disponible."""
    try:
        con = sqlite3.connect(f"file:{_DB}?mode=ro", uri=True)
        try:
            return {n: r for n, r in con.execute("SELECT nombre, rango FROM agents")}
        finally:
            con.close()
    except Exception as exc:                                    # pragma: no cover
        log.warning("gacha_identity: sin rangos de agents (%s)", exc)
        return {}


class GachaIdentifier:
    """Matchers de agentes y de W-Engines, con el pool filtrado por rareza del tile."""

    def __init__(self, agent_refs_dir: Path | str = AGENT_REFS_DIR,
                 engine_refs_dir: Path | str = ENGINE_REFS_DIR):
        self._rangos = _agent_rangos()
        stems = []
        if Path(agent_refs_dir).is_dir():
            stems = [os.path.splitext(f)[0] for f in os.listdir(agent_refs_dir)
                     if f.endswith(".png")]
        name_map = build_name_map(stems, list(self._rangos)) if stems else None

        self._agents = (AvatarMatcher.from_folders(agent_refs_dir, name_map=name_map,
                                                   min_conf=_AGENT_MIN_CONF,
                                                   min_margin=_AGENT_MIN_MARGIN)
                        if Path(agent_refs_dir).is_dir() else None)
        self._engines = (AvatarMatcher.from_folders(engine_refs_dir,
                                                    min_conf=_ENGINE_MIN_CONF,
                                                    min_margin=_ENGINE_MIN_MARGIN)
                         if Path(engine_refs_dir).is_dir() else None)

    # ---- pools filtrados por rareza -------------------------------------------------------

    def _engine_pool(self, rarity: str | None) -> AvatarMatcher | None:
        """Engines candidatos. B ⇒ solo los `29_*`; A/S ⇒ solo los que NO son `29_*`."""
        if self._engines is None or rarity is None:
            return self._engines
        want_b = (rarity == "B")
        refs = {n: v for n, v in self._engines._refs.items()
                if n.startswith(_B_PREFIX) == want_b}
        if not refs:
            return None
        return AvatarMatcher(refs, min_conf=_ENGINE_MIN_CONF, min_margin=_ENGINE_MIN_MARGIN)

    def _agent_pool(self, rarity: str | None) -> AvatarMatcher | None:
        """Agentes candidatos. Se EXCLUYE solo lo que sabemos que es de otro rango: un agente
        sin rango conocido (no está en la DB porque no se tiene) sigue siendo candidato — es
        preferible abstenerse a descartar al verdadero."""
        if self._agents is None or rarity is None:
            return self._agents
        refs = {n: v for n, v in self._agents._refs.items()
                if self._rangos.get(n, rarity) == rarity}
        if not refs:
            return None
        return AvatarMatcher(refs, min_conf=_AGENT_MIN_CONF, min_margin=_AGENT_MIN_MARGIN)

    # ---- API ------------------------------------------------------------------------------

    def identify(self, frame: np.ndarray, tile: GachaTile) -> TileIdentity:
        """Qué hay en el tile. Se abstiene antes que afirmar de más (RNF-02).

        Regla que ordena todo: **en ZZZ no existen agentes rango B** — el rango mínimo de un
        agente es A. Entonces:

          - tile B  ⇒ es un W-Engine, seguro. El pool queda restringido a los 15 `29_*` y el
            matcher trabaja sobre un problema cerrado y chico. Es el caso que funciona.
          - tile A/S ⇒ puede ser agente O engine, y hoy no sabemos distinguirlos: el matcher de
            agentes no identifica (ver el encabezado del módulo) y el clasificador
            `s17_detail_is_face` devuelve True para todo, incluidas las esferas, porque está
            hecho para otra pregunta. Correr igual el pool de engines produjo un error real y
            caro sobre los fixtures: un tile que es la agente Piper salió nombrado
            `Precious_Fossilized_Core`. Nombrar un agente con nombre de arma es peor que no
            decir nada ⇒ se abstiene.

        Lo que sí se reporta siempre, y es información verdadera: rareza, `NEW!` y duplicado.
        """
        art = crop_tile_art(frame, tile.box)
        if art is None or art.size == 0:
            return TileIdentity("incierto", None, 0.0, 0.0)

        if tile.rarity != "B":
            return TileIdentity("incierto", None, 0.0, 0.0)

        pool = self._engine_pool(tile.rarity)
        if pool is None:
            return TileIdentity("incierto", None, 0.0, 0.0)
        r = pool.match(art)
        return TileIdentity("engine", r.name, r.conf, r.margin)
