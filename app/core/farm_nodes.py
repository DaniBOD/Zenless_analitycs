"""Catálogo de nodos de farmeo (S13) → 2 sets predichos.

En la pantalla S13 (selección de set a farmear) el juego muestra el título del nodo. Este
catálogo mapea ese título — leído por OCR, con la misma tolerancia a tildes/ñ/mayúsculas que
el resolver de sets del parser (`app/core/sync_equip.py:_resolve_set_id`) — a los 2 sets que
dropea el nodo, resueltos a `set_id` por `nombre_en`.

Fase A del plan de predicción de sets (display-only, no persiste). Los 2 sets predichos se
guardan en `FarmSession` y se consultan en S2 para restringir el matcher de badges.
Doc canónico: Documentacion/Dev_IA/2026-07-08_PLAN_Prediccion_Sets_S13_y_Badge_S2.md
"""
from __future__ import annotations

import difflib
import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from app.core.stats_vocab import _norm_key

log = logging.getLogger(__name__)

# Ubicación del catálogo por defecto (junto a los demás recursos de la app).
_DEFAULT_TOML = Path(__file__).resolve().parent.parent / "resources" / "farm_nodes.toml"

# Umbrales de fuzzy sobre el TÍTULO del nodo. Mismos criterios que el resolver de sets
# (`sync_equip.py`): cutoff alto + guarda de ambigüedad para no adivinar (RNF-02).
_TITLE_FUZZY_CUTOFF = 0.82
_TITLE_FUZZY_MARGIN = 0.06

# Fuzzy del NOMBRE del set restringido a los 2 candidatos predichos (S13). El umbral es más
# permisivo que el resolver global de sync (_SET_FUZZY_CUTOFF=0.86) porque con solo 2 candidatos
# la ambigüedad es casi nula: el OCR puede cambiar una PALABRA entera del nombre ('brillante'→
# 'radiante') y aun así el set correcto gana por lejos. La guarda de margen abstiene si empatan.
_PRED_SET_MIN_RATIO = 0.60
_PRED_SET_MIN_MARGIN = 0.15


def best_predicted_set_id(
    ocr_name: str | None,
    candidates: list[tuple[int, str]],
    min_ratio: float = _PRED_SET_MIN_RATIO,
    min_margin: float = _PRED_SET_MIN_MARGIN,
) -> int | None:
    """Elige, entre los sets PREDICHOS en S13, el de nombre (ES) más parecido al leído por OCR.

    `candidates` = [(set_id, nombre_es), ...] (típicamente los 2 sets del nodo). Sirve de fallback
    cuando el match exacto/norm falla porque el OCR cambió una palabra del nombre del set (p.ej.
    'Aria brillante'→'Aria radiante', que `_norm_key` no arregla). Con pocos candidatos es seguro
    aunque el umbral sea modesto; abstiene (None) si el mejor no llega al piso o dos candidatos
    quedan dentro del margen. Comparación insensible a tildes/mayúsculas vía `_norm_key`."""
    key = _norm_key(ocr_name or "")
    if not key:
        return None
    scored = sorted(
        (
            (difflib.SequenceMatcher(None, key, _norm_key(nombre)).ratio(), sid)
            for sid, nombre in candidates
            if nombre
        ),
        key=lambda t: t[0],
        reverse=True,
    )
    if not scored or scored[0][0] < min_ratio:
        return None
    if len(scored) >= 2 and (scored[0][0] - scored[1][0]) < min_margin:
        return None
    return scored[0][1]


@dataclass(frozen=True)
class NodeSet:
    """Un set que dropea un nodo. `set_id` es None si el nombre_en no resolvió en la DB."""
    nombre_en: str
    set_id: int | None


@dataclass(frozen=True)
class FarmNode:
    """Un nodo de farmeo: título (ES, como aparece en S13) + sus 2 sets."""
    titulo_es: str
    sets: tuple[NodeSet, ...]
    _key: str = field(default="", repr=False, compare=False)


class FarmNodeCatalog:
    """Resuelve el título del nodo (OCR de S13) → `FarmNode` con los 2 sets predichos."""

    def __init__(self, nodes: list[FarmNode], unresolved: list[str]):
        self._nodes = nodes
        self._unresolved = unresolved
        # Índice por título normalizado (sin tildes/ñ, minúscula, sin espacios).
        self._by_key: dict[str, FarmNode] = {n._key: n for n in nodes}

    # -- construcción -------------------------------------------------------
    @classmethod
    def from_toml(
        cls, path: Path | str, set_id_by_en: Mapping[str, int]
    ) -> "FarmNodeCatalog":
        """Carga el catálogo desde un TOML y resuelve cada nombre_en → set_id.

        `set_id_by_en` = {nombre_en: id}. En la app se construye desde
        `DiscSetRepo.get_all()`. Los nombre_en que no resuelvan se acumulan en
        `unresolved` (y quedan con `set_id=None`) — no se inventa nada (RNF-02).
        """
        with open(path, "rb") as f:
            data = tomllib.load(f)

        nodes: list[FarmNode] = []
        unresolved: list[str] = []
        for raw in data.get("nodes", []):
            titulo = str(raw["titulo_es"])
            sets: list[NodeSet] = []
            for en in raw["sets_en"]:
                sid = set_id_by_en.get(en)
                if sid is None:
                    unresolved.append(en)
                    log.warning(
                        "farm_nodes: nombre_en '%s' (nodo '%s') no resuelve a set_id.",
                        en, titulo,
                    )
                sets.append(NodeSet(nombre_en=en, set_id=sid))
            nodes.append(
                FarmNode(titulo_es=titulo, sets=tuple(sets), _key=_norm_key(titulo))
            )
        return cls(nodes, unresolved)

    @classmethod
    def from_resources(cls, set_id_by_en: Mapping[str, int]) -> "FarmNodeCatalog":
        """Carga el catálogo por defecto (`app/resources/farm_nodes.toml`)."""
        return cls.from_toml(_DEFAULT_TOML, set_id_by_en)

    # -- consulta -----------------------------------------------------------
    @property
    def nodes(self) -> list[FarmNode]:
        return list(self._nodes)

    @property
    def unresolved(self) -> list[str]:
        """nombre_en del toml que no resolvieron a set_id (para diagnóstico/warn)."""
        return list(self._unresolved)

    def match_title(self, ocr_text: str) -> FarmNode | None:
        """Título OCR de S13 → nodo. Exacto (norm) → substring → difflib con guarda.

        Insensible a tildes/ñ/mayúsculas y tolerante a ruido OCR alrededor del título.
        Devuelve None si no hay match confiable (RNF-02: abstiene ante ambigüedad).
        """
        key = _norm_key(ocr_text or "")
        if not key:
            return None

        # 1. Exacto sobre clave normalizada.
        hit = self._by_key.get(key)
        if hit is not None:
            return hit

        # 2. Substring: el OCR puede capturar iconos/flechas alrededor del título,
        #    o recortarlo. Match si la clave del nodo está contenida (o contiene).
        for node in self._nodes:
            if node._key and (node._key in key or key in node._key):
                return node

        # 3. Fuzzy difuso (difflib): 1-2 chars alterados por el OCR. Umbral alto +
        #    guarda de ambigüedad (abstiene si dos nodos distintos empatan dentro
        #    del margen). Mismo patrón que _resolve_set_id (sync_equip.py:537-556).
        keys = [n._key for n in self._nodes if n._key]
        matches = difflib.get_close_matches(key, keys, n=3, cutoff=_TITLE_FUZZY_CUTOFF)
        if not matches:
            return None
        best = self._by_key[matches[0]]
        r_best = difflib.SequenceMatcher(None, key, matches[0]).ratio()
        for m in matches[1:]:
            if self._by_key[m] is not best:
                r_m = difflib.SequenceMatcher(None, key, m).ratio()
                if (r_best - r_m) < _TITLE_FUZZY_MARGIN:
                    return None  # ambiguo → no adivinar
                break
        return best
