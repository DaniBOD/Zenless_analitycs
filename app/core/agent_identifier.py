"""
Hito 2.8 — Etapa 2: identificación de agente por avatar (RF-04 §4.1).

Las pantallas S8 (Equipamiento) y S17/S19 no muestran el nombre del PJ; solo el
avatar resaltado en el row superior. Este módulo identifica al PJ por ese avatar.

Enfoque: **bootstrap desde S18 (Atributos base)**. Cuando el usuario está en
Atributos base tenemos el nombre por OCR Y el crop del avatar resaltado. Guardamos
el par (nombre → descriptor del avatar) en una librería persistente con el estilo
REAL del juego. Luego, en S8/S19, recortamos el avatar resaltado y lo matcheamos
contra la librería. Como el mismo PJ aparece en el mismo slot en todas las
pestañas, el crop de aprendizaje y el de match son casi idénticos (corr ~0.995) y
el match es trivial; PJs distintos correlan ≤ ~0.72.

Ventajas vs. assets del wiki: estilo in-game exacto, auto-rotulado por OCR de S18
(evita assets mal etiquetados), auto-mejora a medida que el usuario navega.

Conservador (RNF-02): ante baja correlación o ambigüedad (poco margen sobre el 2º)
devuelve None — preferimos "sin identificar" antes que afirmar un PJ equivocado.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import cv2
import numpy as np

from app.core.detector import crop_selected_avatar

log = logging.getLogger(__name__)

# Tamaño normalizado del descriptor (resize del crop de la cara).
_DESC_SIZE = 48
# Correlación mínima para aceptar un match (same-PJ ~0.995, distinto ≤ ~0.72).
_MATCH_MIN = 0.88
# Margen mínimo del mejor sobre el segundo (anti-ambigüedad).
_MATCH_GAP = 0.05


def _default_library_path() -> Path:
    # Override explícito (tests, o ubicación custom).
    override = os.environ.get("DANIBOD_AVATAR_LIB")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/AppData/Local")
    return Path(base) / "DaniBOD_ZZZ_Analytics" / "avatar_library.npz"


def _descriptor(face: np.ndarray) -> np.ndarray:
    """Descriptor invariante a brillo: resize 48×48 BGR, media-cero norma-unitaria."""
    g = cv2.resize(face, (_DESC_SIZE, _DESC_SIZE)).astype(np.float32)
    g = g - g.mean()
    norm = float(np.sqrt((g * g).sum()))
    if norm < 1e-6:
        return g.ravel()
    return (g / norm).ravel()


class AgentIdentifier:
    """
    Librería de avatares por nombre, con aprendizaje (bootstrap desde S18) y
    matching (en S8/S19). Persiste a disco (`avatar_library.npz`).
    """

    def __init__(self, library_path: Path | None = None, autoload: bool = True):
        self._path = Path(library_path) if library_path else _default_library_path()
        self._lib: dict[str, np.ndarray] = {}
        if autoload:
            self.load()

    # ---- Persistencia -------------------------------------------------------

    def load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = np.load(str(self._path), allow_pickle=True)
            names = list(data["names"])
            descs = data["descs"]
            self._lib = {str(n): descs[i] for i, n in enumerate(names)}
            log.info("AgentIdentifier: %d avatares cargados de %s", len(self._lib), self._path)
        except Exception:
            log.exception("AgentIdentifier: error cargando librería; se ignora")
            self._lib = {}

    def save(self) -> None:
        if not self._lib:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            names = np.array(list(self._lib.keys()), dtype=object)
            descs = np.stack(list(self._lib.values()))
            np.savez(str(self._path), names=names, descs=descs)
        except Exception:
            log.exception("AgentIdentifier: error guardando librería")

    # ---- API ----------------------------------------------------------------

    @property
    def names(self) -> list[str]:
        return list(self._lib.keys())

    def learn(self, frame: np.ndarray, name: str) -> bool:
        """
        Aprende/actualiza el avatar de `name` desde el frame (típicamente S18,
        donde el nombre viene por OCR). Devuelve True si guardó.
        """
        if not name:
            return False
        face = crop_selected_avatar(frame)
        if face is None:
            return False
        new = self._lib.get(name) is None
        self._lib[name] = _descriptor(face)
        self.save()
        if new:
            log.info("AgentIdentifier: avatar aprendido para '%s' (%d en librería)",
                     name, len(self._lib))
        return True

    def identify(self, frame: np.ndarray) -> tuple[str, float] | None:
        """
        Identifica al PJ del avatar resaltado contra la librería.
        Devuelve (nombre, correlación) si supera umbral+margen, o None.
        """
        if not self._lib:
            return None
        face = crop_selected_avatar(frame)
        if face is None:
            return None
        q = _descriptor(face)
        scored: list[tuple[str, float]] = []
        for name, d in self._lib.items():
            if d.shape != q.shape:
                continue
            scored.append((name, float(np.dot(q, d))))  # ambos norma-unitaria → coseno
        if not scored:
            return None
        scored.sort(key=lambda t: t[1], reverse=True)
        best_name, best = scored[0]
        if best < _MATCH_MIN:
            return None
        if len(scored) > 1 and (best - scored[1][1]) < _MATCH_GAP:
            return None  # ambiguo
        return best_name, best
