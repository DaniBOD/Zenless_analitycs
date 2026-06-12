"""
Hito 2.8 / Fase 5R — identificación de agente por avatar (RF-04 §4.1).

Las pantallas S8 (Equipamiento), S18/S19 y la grilla de discos S17 no muestran el
nombre del PJ; lo identificamos por su ícono de avatar. Desde Fase 5R esto usa el
descriptor ROBUSTO (`avatar_descriptor.AvatarMatcher`: histograma HSV + NCC Lab +
multi-ref + reject-set + abstención + ruta gris) en DOS matchers especializados
(comparar like-with-like es lo que da robustez — medido 2026-06-10):

  - `_row`   : avatar de FILA (tile rectangular, S8/S18/S19). Solo cosecha vía latch
               (bootstrap desde el OCR de S18). 100% leave-one-out.
  - `_badge` : badge de DUEÑO de la grilla S17 (retrato circular). Sembrado con los
               `-ico` del roster (día-1, incl. PJs grises no obtenidos) + cosecha.
               96% / 0% error.

Conservador (RNF-02): ante baja confianza o ambigüedad el matcher se ABSTIENE
(devuelve None) — preferimos "sin identificar" antes que afirmar un PJ equivocado.
Esto reemplaza el coseno de píxeles crudos que causaba el "imán Yixuan".
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np  # noqa: F401  (compat: tests/otros importan np de acá indirectamente)

from app.core.avatar_descriptor import AvatarMatcher, build_name_map
from app.core.detector import crop_selected_avatar
from app.core.stats_vocab import _norm_key
from app.db.connection import is_readonly

log = logging.getLogger(__name__)

_RESOURCES = Path(__file__).resolve().parents[1] / "resources"
_ICO_DIR = _RESOURCES / "avatar_refs"
_REJECT_DIR = _RESOURCES / "avatar_reject"

# Cache del seed -ico: los descriptores son inmutables (frozen) y caros de construir
# (53 PNGs + CLAHE + histogramas). Se construyen UNA vez y se comparten entre
# instancias (cada una recibe listas propias, así su cosecha no se filtra).
_ICO_SEED_CACHE: tuple[dict, list] | None = None

# Similitud mínima para confirmar "mismo PJ que el latch" (guarda S17). Con el
# descriptor robusto multi-ref, same-badge ~0.95+; distinto cae bastante.
_S17_GUARD_DEFAULT = 0.86


def _badge_harvest_enabled() -> bool:
    """Modo cosecha de badges (DANIBOD_BADGE_HARVEST): permite que `learn_s17` PERSISTA
    la librería de badges (avatar_badge_v2.npz) aunque la DB esté en readonly. Crece la
    cobertura del descriptor sin tocar la DB — la librería es un archivo aparte. La
    cosecha sigue gateada por el flujo-ancla (solo el disco EQUIPADO, label certero por
    latch), así que no entra ruido de candidatos."""
    return os.environ.get("DANIBOD_BADGE_HARVEST", "").strip() not in ("", "0", "false")


def _default_library_path() -> Path:
    override = os.environ.get("DANIBOD_AVATAR_LIB")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/AppData/Local")
    return Path(base) / "DaniBOD_ZZZ_Analytics" / "avatar_library.npz"


class AgentIdentifier:
    """Identificador de PJ por avatar, con aprendizaje (cosecha vía latch) y
    matching robusto. Dos matchers especializados (fila / badge), persistidos."""

    def __init__(self, library_path: Path | None = None, autoload: bool = True,
                 roster: set[str] | None = None):
        base = Path(library_path) if library_path else _default_library_path()
        self._row_path = base.with_name("avatar_row_v2.npz")
        self._badge_path = base.with_name("avatar_badge_v2.npz")
        self._row = AvatarMatcher()
        self._badge = AvatarMatcher()
        self._ico_names: set[str] = set()   # refs sembradas de -ico (no podar)
        self._roster_norm: dict[str, str] | None = (
            {_norm_key(n): n for n in roster} if roster is not None else None
        )
        if autoload:
            self._seed_ico()
            self.load()
            self.load_s17()
            self.prune_to_roster()

    # ---- semilla -ico (badge) -----------------------------------------------

    def _seed_ico(self) -> None:
        """Siembra el matcher de badge con los `-ico` del roster + reject-set. Los
        nombres se canonicalizan al roster (build_name_map); los PJs no obtenidos
        que igual tienen ico quedan con su stem (cobertura día-1 de grises)."""
        global _ICO_SEED_CACHE
        if not _ICO_DIR.is_dir():
            return
        try:
            if _ICO_SEED_CACHE is None:
                self._load_roster()
                roster = list((self._roster_norm or {}).values())
                stems = [p.stem for p in _ICO_DIR.glob("*.png")]
                nm = build_name_map(stems, roster)
                seeded = AvatarMatcher.from_folders(_ICO_DIR, _REJECT_DIR, name_map=nm)
                _ICO_SEED_CACHE = (seeded._refs, seeded._rejects)
            refs, rejects = _ICO_SEED_CACHE
            for name, lst in refs.items():        # listas propias, descriptores compartidos
                self._badge._refs.setdefault(name, []).extend(lst)
            self._badge._rejects = list(rejects)
            self._row._rejects = list(rejects)
            self._ico_names = set(refs.keys())
        except Exception:
            log.exception("AgentIdentifier: error sembrando -ico")

    # ---- Roster (validación de nombres) -------------------------------------

    def _load_roster(self) -> None:
        if self._roster_norm is not None:
            return
        try:
            from app.db.connection import get_connection
            con = get_connection()
            try:
                self._roster_norm = {
                    _norm_key(str(r[0])): str(r[0])
                    for r in con.execute("SELECT nombre FROM agents")
                }
            finally:
                con.close()
        except Exception:
            self._roster_norm = {}

    def _canonical_name(self, name: str | None) -> str | None:
        if not name:
            return None
        self._load_roster()
        if not self._roster_norm:
            return name
        return self._roster_norm.get(_norm_key(name))

    def prune_to_roster(self) -> int:
        """Quita refs cuyo nombre no esté en el roster (OCR espurio como 'Permiso'),
        PROTEGIENDO las sembradas de -ico (PJs válidos no obtenidos)."""
        self._load_roster()
        if not self._roster_norm:
            return 0
        valid = set(self._roster_norm.values()) | self._ico_names
        removed = 0
        for matcher in (self._row, self._badge):
            for n in [k for k in matcher._refs if k not in valid]:
                del matcher._refs[n]; removed += 1
        if removed and not is_readonly():
            log.info("AgentIdentifier: podadas %d refs fuera del roster", removed)
            self.save(); self.save_s17()
        return removed

    # ---- Persistencia -------------------------------------------------------

    def load(self) -> None:
        n = self._row.load_merge(self._row_path)
        if n:
            log.info("AgentIdentifier: %d refs de fila cargadas de %s", n, self._row_path)

    def save(self) -> None:
        self._row.save(self._row_path)

    def load_s17(self) -> None:
        n = self._badge.load_merge(self._badge_path)
        if n:
            log.info("AgentIdentifier: %d refs de badge cargadas de %s", n, self._badge_path)

    def save_s17(self) -> None:
        self._badge.save(self._badge_path)

    # ---- API: avatar de FILA (S8/S18/S19) -----------------------------------

    @property
    def names(self) -> list[str]:
        return list(self._row._refs.keys())

    def learn(self, frame, name: str) -> bool:
        """Aprende/cosecha el avatar de fila de `name` desde el frame (típicamente
        S18, nombre por OCR). Multi-ref. No escribe en readonly."""
        if not name or is_readonly():
            return False
        canon = self._canonical_name(name)
        if canon is None:
            log.debug("AgentIdentifier: '%s' fuera del roster → no se aprende", name)
            return False
        face = crop_selected_avatar(frame)
        if face is None:
            return False
        new = canon not in self._row._refs
        self._row.add_reference(canon, face)
        self.save()
        if new:
            log.info("AgentIdentifier: avatar de fila aprendido para '%s'", canon)
        return True

    def identify(self, frame) -> tuple[str, float] | None:
        return self.identify_face(crop_selected_avatar(frame))

    def identify_face(self, face) -> tuple[str, float] | None:
        if face is None:
            return None
        r = self._row.match(face)
        return (r.name, r.conf) if r.name else None

    # ---- API: badge de DUEÑO (grilla S17) -----------------------------------

    @property
    def names_s17(self) -> list[str]:
        return list(self._badge._refs.keys())

    def learn_s17(self, face, name: str) -> bool:
        """Aprende/cosecha el badge de `name` (ground-truth del latch). Multi-ref.
        En readonly NO persiste, SALVO en modo cosecha de badges (DANIBOD_BADGE_HARVEST),
        que escribe solo la librería de badges (no la DB)."""
        if not name or face is None or (is_readonly() and not _badge_harvest_enabled()):
            return False
        canon = self._canonical_name(name)
        if canon is None:
            log.debug("AgentIdentifier: S17 '%s' fuera del roster → no se aprende", name)
            return False
        new = canon not in self._badge._refs or canon in self._ico_names
        self._badge.add_reference(canon, face)
        self.save_s17()
        if new:
            log.info("AgentIdentifier: badge aprendido para '%s'", canon)
        return True

    def s17_similarity(self, face, name: str) -> float | None:
        """Similitud del badge a las refs de `name` (guarda mismo/distinto vs latch).
        None si `name` no tiene refs o el crop es inválido."""
        if face is None:
            return None
        return self._badge.similarity_to(face, name)

    def identify_s17(self, face, min_sim: float = _S17_GUARD_DEFAULT) -> tuple[str, float] | None:
        """Mejor match del badge contra TODA la librería (sembrado -ico + cosecha).
        Para nombrar el DUEÑO de un disco candidato de la grilla. Se abstiene
        (None) si conf<gate o margen chico o cae en el reject-set."""
        if face is None:
            return None
        r = self._badge.match(face)
        if r.name is None or r.conf < min_sim:
            return None
        return r.name, r.conf
