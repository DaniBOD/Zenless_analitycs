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
from app.db.connection import is_readonly

log = logging.getLogger(__name__)

# Tamaño normalizado del descriptor (resize del crop de la cara).
_DESC_SIZE = 48
# Correlación mínima para aceptar un match (same-PJ ~0.995, distinto ≤ ~0.72).
_MATCH_MIN = 0.88
# Margen mínimo del mejor sobre el segundo (anti-ambigüedad).
_MATCH_GAP = 0.05

# --- Avatar circular S17 (asignación de disco equipado) ---------------------
# El avatar del PJ asignado en S17 es un círculo (a la derecha de "Nivel X/15"),
# NO el tile rectangular del row. Tiene fondo rayado oscuro en las esquinas, que
# domina el descriptor rectangular y colapsa todos los matches (medido 2026-06-06:
# todo → "Miyabi" ~0.58 contra la librería del row). Por eso S17 usa:
#   1. un descriptor con MÁSCARA CIRCULAR (anula las esquinas), y
#   2. una librería PROPIA (`avatar_library_s17.npz`) bootstrapeada del latch.
# Medido sobre 7 crops reales: same-PJ 0.87–0.97; distinto ≤ 0.85. El umbral de
# guarda separa "mismo PJ que el latch" de "otro PJ" (disco del grid de otro PJ).
_S17_DESC_SIZE = 48
_yy, _xx = np.ogrid[:_S17_DESC_SIZE, :_S17_DESC_SIZE]
_S17_CMASK = (
    (_xx - _S17_DESC_SIZE / 2) ** 2 + (_yy - _S17_DESC_SIZE / 2) ** 2
) <= (_S17_DESC_SIZE / 2 - 1) ** 2


def _default_library_path() -> Path:
    # Override explícito (tests, o ubicación custom).
    override = os.environ.get("DANIBOD_AVATAR_LIB")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/AppData/Local")
    return Path(base) / "DaniBOD_ZZZ_Analytics" / "avatar_library.npz"


def _s17_library_path(main_path: Path) -> Path:
    """Librería S17 hermana de la del row (mismo dir, sufijo _s17)."""
    override = os.environ.get("DANIBOD_AVATAR_LIB_S17")
    if override:
        return Path(override)
    return main_path.with_name("avatar_library_s17.npz")


def _descriptor(face: np.ndarray) -> np.ndarray:
    """Descriptor invariante a brillo: resize 48×48 BGR, media-cero norma-unitaria."""
    g = cv2.resize(face, (_DESC_SIZE, _DESC_SIZE)).astype(np.float32)
    g = g - g.mean()
    norm = float(np.sqrt((g * g).sum()))
    if norm < 1e-6:
        return g.ravel()
    return (g / norm).ravel()


def _descriptor_circular(face: np.ndarray) -> np.ndarray:
    """
    Descriptor para el avatar circular S17: resize 48×48, media-cero calculada
    SOLO dentro del círculo, esquinas anuladas (máscara), norma-unitaria. Anula
    el fondo rayado de las esquinas que de otro modo domina el coseno.
    """
    g = cv2.resize(face, (_S17_DESC_SIZE, _S17_DESC_SIZE)).astype(np.float32)
    mean = g[_S17_CMASK].mean(axis=0)
    g = (g - mean) * _S17_CMASK[..., None]
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
        self._path_s17 = _s17_library_path(self._path)
        self._lib: dict[str, np.ndarray] = {}
        self._lib_s17: dict[str, np.ndarray] = {}
        if autoload:
            self.load()
            self.load_s17()

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

    def load_s17(self) -> None:
        if not self._path_s17.exists():
            return
        try:
            data = np.load(str(self._path_s17), allow_pickle=True)
            names = list(data["names"])
            descs = data["descs"]
            self._lib_s17 = {str(n): descs[i] for i, n in enumerate(names)}
            log.info("AgentIdentifier: %d avatares S17 cargados de %s",
                     len(self._lib_s17), self._path_s17)
        except Exception:
            log.exception("AgentIdentifier: error cargando librería S17; se ignora")
            self._lib_s17 = {}

    def save_s17(self) -> None:
        if not self._lib_s17:
            return
        try:
            self._path_s17.parent.mkdir(parents=True, exist_ok=True)
            names = np.array(list(self._lib_s17.keys()), dtype=object)
            descs = np.stack(list(self._lib_s17.values()))
            np.savez(str(self._path_s17), names=names, descs=descs)
        except Exception:
            log.exception("AgentIdentifier: error guardando librería S17")

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
        if is_readonly():
            return False  # modo offline: librería de avatares inerte
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
        Identifica al PJ del avatar resaltado (row) contra la librería.
        Devuelve (nombre, correlación) si supera umbral+margen, o None.
        """
        face = crop_selected_avatar(frame)
        if face is None:
            return None
        return self.identify_face(face)

    def identify_face(self, face: np.ndarray) -> tuple[str, float] | None:
        """
        Matchea un crop de cara arbitrario (descriptor rectangular) contra la
        librería del row. Núcleo reutilizable de `identify()`.
        """
        if not self._lib or face is None or face.size == 0:
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

    # ---- Avatar S17 (librería circular propia, guarda de asignación) ---------

    @property
    def names_s17(self) -> list[str]:
        return list(self._lib_s17.keys())

    def learn_s17(self, face: np.ndarray, name: str) -> bool:
        """
        Aprende/actualiza el descriptor circular S17 de `name` desde un crop de
        avatar. `name` es ground-truth del latch (PJ cuya pantalla se ve).
        Devuelve True si guardó.
        """
        if not name or face is None or face.size == 0:
            return False
        if is_readonly():
            return False  # modo offline: librería S17 inerte
        new = self._lib_s17.get(name) is None
        self._lib_s17[name] = _descriptor_circular(face)
        self.save_s17()
        if new:
            log.info("AgentIdentifier: avatar S17 aprendido para '%s' (%d en librería S17)",
                     name, len(self._lib_s17))
        return True

    def s17_similarity(self, face: np.ndarray, name: str) -> float | None:
        """
        Coseno entre el descriptor circular del crop y el descriptor S17 guardado
        de `name`. None si `name` no tiene descriptor aprendido todavía o el crop
        es inválido. Es la GUARDA mismo/distinto vs el PJ latcheado (no un matcher
        de 46 vías): ≥ umbral ⇒ "mismo PJ"; < umbral ⇒ "otro PJ / abstener".
        """
        if face is None or face.size == 0:
            return None
        stored = self._lib_s17.get(name)
        if stored is None:
            return None
        q = _descriptor_circular(face)
        if q.shape != stored.shape:
            return None
        return float(np.dot(q, stored))

    def identify_s17(self, face: np.ndarray, min_sim: float = 0.86) -> tuple[str, float] | None:
        """
        Mejor match del avatar circular S17 contra TODA la librería S17 (a
        diferencia de `s17_similarity`, que compara contra UN nombre). Para el modo
        VISUALIZACIÓN: nombrar qué PJ tiene equipado un disco candidato de la grilla.
        Devuelve (nombre, sim) del mejor match ≥ `min_sim`, o None si no hay
        librería / el crop es inválido / ningún PJ supera el umbral.
        """
        if face is None or face.size == 0 or not self._lib_s17:
            return None
        q = _descriptor_circular(face)
        best_name, best_sim = None, -1.0
        for name, stored in self._lib_s17.items():
            if q.shape != stored.shape:
                continue
            sim = float(np.dot(q, stored))
            if sim > best_sim:
                best_sim, best_name = sim, name
        if best_name is None or best_sim < min_sim:
            return None
        return best_name, best_sim
