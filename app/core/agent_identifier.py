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

from app.core.avatar_descriptor import (
    _MAX_REFS_PER_NAME,
    AvatarDescriptor,
    AvatarMatcher,
    build_name_map,
)
from app.core.badge_surface import BadgeSurface
from app.core.detector import crop_detail_badge, crop_grid_selected_badge, crop_selected_avatar
from app.core.stats_vocab import _norm_key
from app.db.connection import is_readonly

log = logging.getLogger(__name__)

_RESOURCES = Path(__file__).resolve().parents[1] / "resources"
_ICO_DIR = _RESOURCES / "avatar_refs"
_REJECT_DIR = _RESOURCES / "avatar_reject"
# Reject-set PROPIO del detalle (5R.L.8): crops reales del texto '(N)' del nº de slot
# que el localizador del detalle a veces recorta en discos LIBRES. Solo el matcher
# _detbadge los usa — el texto no debe rechazar crops del grid/row. Es la base de la
# PRESENCIA ESTRUCTURAL: crop no-rechazado = hay una cara (nombrable o no).
_REJECT_DET_DIR = _RESOURCES / "avatar_reject_det"

# Baselines VERSIONADOS de cada superficie (el repo sí se versiona; %LOCALAPPDATA% no). Si la
# librería del runtime no está, `BadgeSurface.load` la repone de acá — pasó dos veces: el detalle
# el 2026-07-28 y el grid + row el 2026-07-31, y esta última dejó al grid nombrando con arte
# `-ico` (4.3% top-1, Cissia llevándose 14 discos ajenos). Actualizar cuando se cosecha de más:
# `tools/preseed_badge_lib.py --save-snapshot` deja el archivo con este nombre.
#
# Los `_dedup` del 2026-08-11 son los mismos snapshots con los CLONES colapsados: la cosecha del
# flujo de discos llamaba a `learn` una vez por disco y el avatar del panel no cambia con el disco,
# así que la mitad de las refs eran copias (row 365→62, detail 193→85, grid 486→356). Ninguna clase
# se perdió. Los snapshots anteriores quedan como historia y NO se reescriben.
#
# El `_20260813` de `detail` (89 refs) fueron las 85 dedupeadas MÁS las 4 que cosechó el flujo de
# armas para Jane, Nangong Yu y Zhao. Con esas cuatro, los tres pasaron a tener al dueño correcto
# en el puesto 1 en el inventario S30 —Zhao venía saliendo detrás de Nicole—.
#
# `_roster51` (2026-08-16) suma a **Aria**, del banner de ese día, y por eso las tres superficies se
# mueven juntas: es el primer PJ onboardeado desde que existe el dedup, así que las tres traen
# refs reales y ninguna copia. El `row` salió de un screenshot (no cosecha en readonly); `grid` y
# `detail` de la pasada por sus 6 discos, y ahí se ve el dedup trabajando: el grid sumó 7 —su tile
# cambia con el disco— y el detail solo 3, porque el avatar del panel NO cambia y las repetidas se
# rechazaron. Con esto las tres cubren el roster completo (51/51). La medición contra etiquetados
# quedó IGUAL que antes (grid 93.3% top-1 · 2.4% wrong): sumar un PJ no desplazó a ninguno.
#
# Viven bajo `app/resources/` y NO en `audit/`, aunque los snapshots HISTÓRICOS sigan ahí. La
# ruta vieja era `Path(__file__).parents[2] / "audit"`: en desarrollo eso da la raíz del repo y
# funciona, pero congelado `__file__` es `_internal/app/core/agent_identifier.py`, así que
# `parents[2]` es `_internal` y apuntaba a `_internal/audit/` — una carpeta que el spec nunca
# copió. O sea que en el `.exe` esta red de emergencia no existía, en silencio (hallado el
# 2026-08-19 revisando el empaquetado de `farm_nodes.toml`).
#
# Bajo `app/resources/` resuelven con el MISMO mecanismo que `detector.TEMPLATES_DIR` y
# `farm_nodes._DEFAULT_TOML`, que ya se sabe que anda empaquetado, y entran al bundle sin
# tocar el spec porque desde el 2026-08-18 copia `app/resources` entera. Cuestan 34 MB sobre
# 1335: 2.5 %. Los snapshots viejos se quedan en `audit/` como historia — el que la app repone
# tiene UN solo lugar, que es de lo que se trata.
_BASELINE_DIR = _RESOURCES / "badge_baselines"
_BASELINES = {
    "row": _BASELINE_DIR / "avatar_row_v2_snapshot_20260816_roster51.npz",
    "grid": _BASELINE_DIR / "avatar_badge_v2_snapshot_20260816_roster51.npz",
    "detail": _BASELINE_DIR / "avatar_detbadge_v2_snapshot_20260816_roster51.npz",
}

# Cache del seed -ico: los descriptores son inmutables (frozen) y caros de construir
# (53 PNGs + CLAHE + histogramas). Se construyen UNA vez y se comparten entre
# instancias (cada una recibe listas propias, así su cosecha no se filtra).
_ICO_SEED_CACHE: tuple[dict, list] | None = None
# Cache de los rejects de texto del detalle (mismo criterio: frozen + compartidos).
_DET_REJECT_CACHE: list | None = None

# Similitud mínima para NOMBRAR al dueño de un candidato (identify_s17). Bajado de
# 0.86 → 0.80 (sub-fase B, 2026-06-12): recupera matches correctos sub-0.86 (Burnice,
# Nicole) manteniendo el techo seguro > 0.766 (la conf de los falsos-Seth César/Sunna,
# que a 0.80 quedan en "dueño incierto", nunca asertados). El guard latch (mismo PJ)
# es aparte (_S17_GUARD_MIN en monitor, sigue 0.86).
_S17_GUARD_DEFAULT = 0.80


def _badge_harvest_enabled() -> bool:
    """Modo cosecha de badges (DANIBOD_BADGE_HARVEST): permite que `learn_s17` PERSISTA
    la librería de badges (avatar_badge_v2.npz) aunque la DB esté en readonly. Crece la
    cobertura del descriptor sin tocar la DB — la librería es un archivo aparte. La
    cosecha sigue gateada por el flujo-ancla (solo el disco EQUIPADO, label certero por
    latch), así que no entra ruido de candidatos."""
    return os.environ.get("DANIBOD_BADGE_HARVEST", "").strip() not in ("", "0", "false")


def _demojibake(s: str) -> str | None:
    """Re-decodifica una clave DOBLE-CODIFICADA (bytes UTF-8 leídos como latin-1):
    'n.\\xc2\\xba11' → 'n.º11'. Devuelve None si `s` no era mojibake (o no se puede
    re-decodificar). Canonicalizar solo no alcanza: `_norm_key` normaliza 'Â' a 'a',
    así que la clave rota nunca matchea el roster."""
    try:
        fixed = s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None
    return fixed if fixed != s else None


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
                 roster: set[str] | None = None, prune: bool = True):
        """`prune=False` carga las librerías SIN podarlas ni persistirlas: para
        herramientas de INSPECCIÓN (tools/audit_badge_lib.py) — un audit no debe
        modificar su objeto de estudio (regresión 2026-07-31)."""
        base = Path(library_path) if library_path else _default_library_path()
        # El baseline repone la librería DEL RUNTIME, y SOLO esa. Apuntar a otro lado —un
        # `library_path` explícito, o `DANIBOD_AVATAR_LIB`, que es como el conftest aísla cada
        # test en su tmp— es una decisión deliberada: ahí que el archivo no exista es
        # información, no una avería, y volcarle 459 refs del repo rompe el aislamiento.
        _bl = ({} if (library_path is not None or os.environ.get("DANIBOD_AVATAR_LIB"))
               else _BASELINES)
        self._row_path = base.with_name("avatar_row_v2.npz")
        self._badge_path = base.with_name("avatar_badge_v2.npz")
        # Detalle-badge (5R.C.4): librería PROPIA del avatar del panel de detalle S17
        # (junto a 'Nivel 15/15'). Encuadre distinto al grid-badge → no comparte refs.
        # Localización 100% (vs 73% del grid) → sube el yield del voto en S17.
        self._detbadge_path = base.with_name("avatar_detbadge_v2.npz")
        self._row = AvatarMatcher()
        self._badge = AvatarMatcher()
        self._detbadge = AvatarMatcher()
        self._det_text_rejects: list = []   # anclas de texto '(N)' (presencia, 5R.L.8)
        self._ico_names: set[str] = set()   # refs sembradas de -ico (no podar)
        self._roster_norm: dict[str, str] | None = (
            {_norm_key(n): n for n in roster} if roster is not None else None
        )
        # Superficies de badge (5R.L.8/B1): el boilerplate crop+match+cosecha+presencia
        # de cada encuadre, empaquetado reusable (app/core/badge_surface.py). Los métodos
        # históricos de abajo delegan acá; una pantalla NUEVA (S9/S23) registra la suya
        # con su crop_fn + librería propia y consume sample()/learn().
        _harvest_gate = lambda: not is_readonly() or _badge_harvest_enabled()  # noqa: E731
        self.surfaces: dict[str, BadgeSurface] = {
            "row": BadgeSurface(
                "row", crop_selected_avatar, self._row, self._row_path,
                canonicalize=self._canonical_name,
                persist_gate=lambda: not is_readonly(),
                baseline_path=_bl.get("row"),
            ),
            "grid": BadgeSurface(
                "grid", crop_grid_selected_badge, self._badge, self._badge_path,
                canonicalize=self._canonical_name, persist_gate=_harvest_gate,
                baseline_path=_bl.get("grid"),
            ),
            "detail": BadgeSurface(
                "detail", crop_detail_badge, self._detbadge, self._detbadge_path,
                canonicalize=self._canonical_name, persist_gate=_harvest_gate,
                presence_fn=self.s17_detail_is_face,
                baseline_path=_bl.get("detail"),
            ),
        }
        if autoload:
            self._seed_ico()              # reject-set + nombres con -ico (no siembra refs)
            self._seed_det_rejects()
            self.load()
            self.load_s17()
            self.load_s17_detail()
            self._seed_ico_refs()         # DESPUÉS de cargar: solo tapa huecos, no duplica
            if prune:
                self.prune_to_roster()

    # ---- semilla -ico (badge) -----------------------------------------------

    def _seed_ico(self) -> None:
        """Carga el reject-set de las tres superficies y los nombres con `-ico`.

        NO siembra refs: eso lo hace `_seed_ico_refs` DESPUÉS de cargar las librerías. Ver ahí
        el porqué de la separación.
        """
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
            self._badge._rejects = list(rejects)
            self._row._rejects = list(rejects)
            self._detbadge._rejects = list(rejects)   # detalle comparte reject-set, NO los -ico
            # TODOS los nombres con -ico, tengan o no refs sembradas: `prune_to_roster` usa este
            # set para proteger a los PJs no obtenidos, y esa protección no depende de que la
            # semilla haya entrado.
            self._ico_names = set(refs.keys())
        except Exception:
            log.exception("AgentIdentifier: error cargando el reject-set -ico")

    def _seed_ico_refs(self) -> None:
        """Siembra el badge con los `-ico`, SOLO para los PJs que quedaron sin refs cosechadas.

        El `-ico` es arte de comunidad recortado del splash: **otro dominio** que el badge
        in-game. Su función declarada es dar cobertura día-1 de los PJs grises que no se poseen
        (2026-06-10), no competir con la cosecha real — contra `-ico` solo, el badge real da 34%.

        Antes se sembraba SIEMPRE y ANTES de cargar el `.npz`. Como el `.npz` ya contenía una
        copia guardada de la semilla, cada ciclo seed → load → save sumaba otra: el 2026-07-31 el
        grid tenía 2 refs IDÉNTICAS por clase (distancia intra-clase 0.0) y ninguna cosechada. Ni
        `_seed_ico` ni `load_merge` aplican `_MAX_REFS_PER_NAME`, así que nada lo frenaba.

        Sembrar solo los huecos corta la duplicación y saca al `-ico` de la competencia en los
        PJs que tienen refs del dominio correcto. El clasificador cara-vs-texto no se ve afectado:
        `s17_detail_is_face` toma sus anclas de `_ICO_SEED_CACHE`, no de `_badge._refs`.
        """
        if _ICO_SEED_CACHE is None:
            return
        refs, _rejects = _ICO_SEED_CACHE
        for name, lst in refs.items():        # listas propias, descriptores compartidos
            if not self._badge._refs.get(name):
                self._badge._refs[name] = list(lst)

    def _seed_det_rejects(self) -> None:
        """Carga las anclas de TEXTO '(N)' del detalle (avatar_reject_det/) para el
        clasificador de PRESENCIA estructural (5R.L.8, `s17_detail_is_face`). NO se
        mezclan con el reject-set de naming del matcher: la presencia y el naming son
        señales separadas (mezclarlas causaba abstenciones nuevas en caras grises —
        Nangong Yu dista 0.349 del texto por la ruta de luminancia)."""
        global _DET_REJECT_CACHE
        if not _REJECT_DET_DIR.is_dir():
            return
        try:
            if _DET_REJECT_CACHE is None:
                import cv2
                from app.core.avatar_descriptor import build_descriptor
                descs = []
                for p in sorted(_REJECT_DET_DIR.glob("*.png")):
                    d = build_descriptor(cv2.imread(str(p)))
                    if d is not None:
                        descs.append(d)
                _DET_REJECT_CACHE = descs
            self._det_text_rejects = list(_DET_REJECT_CACHE)
        except Exception:
            log.exception("AgentIdentifier: error cargando anclas de texto del detalle")

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

    def resolve_to_roster(self, name: str) -> str | None:
        """Canónico del roster para `name`, tolerando OCR sin tilde / espaciado
        distinto Y claves DOBLE-CODIFICADAS. None = el roster no lo resuelve, que es
        exactamente lo que `prune_to_roster` poda. Única fuente de esa decisión: las
        herramientas de inspección la consultan para no describir mal lo que la poda
        va a hacer."""
        self._load_roster()
        if not self._roster_norm:
            return None
        canon = self._canonical_name(name)
        if canon is not None:
            return canon
        fixed = _demojibake(name)
        return self._canonical_name(fixed) if fixed else None

    def prune_to_roster(self) -> int:
        """Quita refs cuyo nombre no esté en el roster (OCR espurio como 'Permiso'),
        PROTEGIENDO las sembradas de -ico (PJs válidos no obtenidos).

        RECUPERA antes de podar: si el roster resuelve la clave canonicalizándola
        (OCR sin tilde, espaciado distinto) o re-decodificando su mojibake, la clave
        se RENOMBRA al canónico y conserva sus refs. Podar es para basura
        irrecuperable, no para cosecha buena con la etiqueta mal escrita —
        regresión 2026-07-31: se tiraron las 4 refs de 'n.\\xc2\\xba11' (= 'N.º 11').

        Devuelve cuántas claves se BORRARON (los renombres no cuentan: no se perdió
        nada). Persiste si hubo cualquiera de las dos cosas."""
        self._load_roster()
        if not self._roster_norm:
            return 0
        valid = set(self._roster_norm.values()) | self._ico_names
        removed = renamed = 0
        for matcher in (self._row, self._badge, self._detbadge):
            for n in [k for k in matcher._refs if k not in valid]:
                canon = self.resolve_to_roster(n)
                if canon is None:
                    del matcher._refs[n]; removed += 1
                    continue
                lst = matcher._refs.setdefault(canon, [])
                lst.extend(matcher._refs.pop(n))
                del lst[:-_MAX_REFS_PER_NAME]     # FIFO, igual que add_reference
                log.info("AgentIdentifier: '%s' renombrada a '%s' (%d refs rescatadas)",
                         n, canon, len(lst))
                renamed += 1
        if (removed or renamed) and not is_readonly():
            if removed:
                log.info("AgentIdentifier: podadas %d refs fuera del roster", removed)
            self.save(); self.save_s17(); self.save_s17_detail()
        return removed

    # ---- Persistencia -------------------------------------------------------

    def load(self) -> None:
        self.surfaces["row"].load()

    def save(self) -> None:
        self.surfaces["row"].save()

    def load_s17(self) -> None:
        self.surfaces["grid"].load()

    def save_s17(self) -> None:
        self.surfaces["grid"].save()

    def load_s17_detail(self) -> None:
        self.surfaces["detail"].load()

    def save_s17_detail(self) -> None:
        self.surfaces["detail"].save()

    # ---- API: avatar de FILA (S8/S18/S19) -----------------------------------

    @property
    def names(self) -> list[str]:
        return list(self._row._refs.keys())

    def learn(self, frame, name: str) -> bool:
        """Aprende/cosecha el avatar de fila de `name` desde el frame (típicamente
        S18, nombre por OCR). Multi-ref. No escribe en readonly. Delegado a la
        superficie `row` (canonicalización + gate + persistencia, 5R.L.8/B1)."""
        if not name:
            return False
        canon = self._canonical_name(name)
        new = canon is not None and canon not in self._row._refs
        if not self.surfaces["row"].learn(crop_selected_avatar(frame), name):
            return False
        if new:
            log.info("AgentIdentifier: avatar de fila aprendido para '%s'", canon)
        return True

    def identify(self, frame) -> tuple[str, float] | None:
        return self.identify_face(crop_selected_avatar(frame))

    def identify_face(self, face) -> tuple[str, float] | None:
        """Identifica al PJ por su avatar de FILA, bajo el guard de la superficie.

        Hasta 2026-08-01 esta ruta devolvía cualquier match que pasara los gates internos del
        matcher (`min_conf=0.45`, `min_margin=0.04`) — la mitad del guard que usa el resto del
        sistema. Con la librería completa casi no se notaba; con huecos miente: en el QA en vivo
        la página de **Remielle Dan** —que no tiene refs de fila— dio `Vivian conf=0.550`, y dos
        frames de eso fijaron el latch en Vivian. Los discos eran de Remielle, así que el
        cross-check del badge tuvo que desautorizar al ancla en los 6 slots.

        El guard sale medido, no elegido: leave-one-out sobre las 328 refs de fila, la confianza
        MÍNIMA de un match correcto es **0.928** (mediana 1.000). A 0.80 no cae ni uno, y el
        falso Vivian de 0.550 queda afuera con margen. Un PJ sin refs pasa a ABSTENERSE, que es
        lo que corresponde (RNF-02): el monitor sostiene al último conocido en vez de saltar a
        uno equivocado.
        """
        if face is None:
            return None
        r = self._row.match(face)
        if r.name is None or r.conf < self.surfaces["row"].guard:
            return None
        return r.name, r.conf

    # ---- API: badge de DUEÑO (grilla S17) -----------------------------------

    @property
    def names_s17(self) -> list[str]:
        return list(self._badge._refs.keys())

    def learn_s17(self, face, name: str) -> bool:
        """Aprende/cosecha el badge de `name` (ground-truth del latch). Multi-ref.
        En readonly NO persiste, SALVO en modo cosecha de badges (DANIBOD_BADGE_HARVEST),
        que escribe solo la librería de badges (no la DB). Delegado a la superficie
        `grid` (5R.L.8/B1)."""
        if not name:
            return False
        canon = self._canonical_name(name)
        new = canon is not None and (canon not in self._badge._refs or canon in self._ico_names)
        if not self.surfaces["grid"].learn(face, name):
            return False
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

    def s17_match(self, face, min_sim: float = _S17_GUARD_DEFAULT):
        """Match del badge con detalle para el detector LIBRE/equipado (5R.B): devuelve
        (nombre|None, conf, rejected). nombre no-None solo si conf≥guard. rejected=True
        si el crop cae en el reject-set (lock/disco/vacío → señal de disco SUELTO)."""
        if face is None:
            return None, 0.0, False
        r = self._badge.match(face)
        name = r.name if (r.name is not None and r.conf >= min_sim) else None
        return name, r.conf, r.rejected

    def s17_match_full(self, face):
        """Como `s17_match` pero devuelve el `MatchResult` CRUDO (name, conf, margin,
        rejected, top) para el desempate por contexto (OwnerTiebreaker). `name` aquí ya
        viene None si el matcher se abstuvo (conf/margen/reject); `top` trae los candidatos
        best-first para desempatar. None si no hay cara."""
        if face is None:
            return None
        return self._badge.match(face)

    # ---- API: DETALLE-badge (panel de detalle S17, librería propia) ----------

    def knows_detail_badge(self, name: str | None) -> bool:
        """¿La librería del DETALLE tiene refs de `name`?

        Es la pregunta "¿puede esta superficie opinar sobre este PJ?". Un matcher contesta
        eligiendo entre las clases que tiene: sin refs del PJ verdadero, su respuesta no es una
        opinión sobre él sino lo más parecido que encontró en un conjunto que no lo contiene.

        Medido en vivo (QA 2026-07-31) sobre la página de Rina, que tiene 0 refs de detalle:
        `det_votes=[Lucía:1.72]` — dos matches confiados a un PJ equivocado. Por eso "se
        abstuvo" NO sirve como proxy de "no tiene opinión": a veces se abstiene (Velina, Pyrois,
        N.º 0) y a veces nombra a otro, y las dos cosas significan lo mismo.

        Es SOLO el detalle a propósito: el grid tiene refs de todo el roster (sembradas de
        `-ico` + cosecha vieja), así que preguntarle a él da siempre que sí y no discrimina nada.
        """
        canon = self._canonical_name(name) if name else None
        return bool(canon) and bool(self._detbadge._refs.get(canon))

    def detail_refs_count(self, name: str) -> int:
        """Cuántas referencias tiene `name` en la librería del DETALLE (0 si no está).

        Lo consulta quien vaya a cosechar, para no pasarse del techo: `add_reference` desaloja la
        ref más vieja cuando se llena, así que cosechar sobre un PJ completo no agrega cobertura,
        la CAMBIA — y lo que se pierde es el encuadre más viejo, que suele ser el diverso.
        """
        canon = self._canonical_name(name) if name else None
        return len(self._detbadge._refs.get(canon, [])) if canon else 0

    def detail_is_near_duplicate(self, face, name: str) -> bool:
        """¿`face` es prácticamente la misma imagen que alguna ref que `name` ya tiene?

        Delega en la superficie, que es la dueña del criterio — `BadgeSurface.learn` aplica el
        mismo chequeo por su cuenta, y dos implementaciones del mismo umbral se desincronizan.
        Lo usa la cosecha de armas para poder REPORTAR el desenlace (`veto_clon`) en el
        diagnóstico, cosa que un `learn` que devuelve False no permite distinguir.
        """
        return self.surfaces["detail"].is_near_duplicate(face, name)

    def learn_s17_detail(self, face, name: str) -> bool:
        """Cosecha el detalle-badge de `name` (ground-truth del latch) a su librería
        PROPIA. Mismo gating que learn_s17: en readonly NO persiste salvo en cosecha
        de badges (DANIBOD_BADGE_HARVEST), que escribe solo la librería (no la DB).
        Delegado a la superficie `detail` (5R.L.8/B1)."""
        if not name:
            return False
        canon = self._canonical_name(name)
        new = canon is not None and canon not in self._detbadge._refs
        if not self.surfaces["detail"].learn(face, name):
            return False
        if new:
            log.info("AgentIdentifier: detalle-badge aprendido para '%s'", canon)
        return True

    def s17_detail_is_face(self, face) -> bool:
        """PRESENCIA ESTRUCTURAL del crop del detalle (5R.L.8): ¿el crop es una CARA
        (de cualquier PJ, nombrable o no) o el texto '(N)' del nº de slot que el
        localizador recorta a veces en discos libres? Compara la distancia mínima a
        las anclas de CARA (refs cosechadas del detalle ∪ semilla -ico del roster,
        disponibles desde día-1) contra las anclas de TEXTO (avatar_reject_det/).
        Independiente del NAMING: un avatar real con matcher débil (gap de refs,
        p.ej. Jane visto desde Velina QA 2026-07-18) sigue contando como presente.
        Medido sobre el gold set (audit/harvest_badges): 163/163 caras → True (0
        falso-texto = 0 falso-LIBRE); texto de estilo no visto puede dar True (costo:
        'incierto' en vez de LIBRE — dirección segura, RNF-02).
        Sin anclas (de texto o de cara) → True: ante la duda, presencia (nunca
        habilitar un falso LIBRE por falta de calibración)."""
        if face is None:
            return False
        from app.core.avatar_descriptor import build_descriptor, descriptor_distance
        q = build_descriptor(face)
        if q is None:
            return False
        if not self._det_text_rejects:
            return True
        anchors = [d for lst in self._detbadge._refs.values() for d in lst]
        if _ICO_SEED_CACHE is not None:
            anchors += [d for lst in _ICO_SEED_CACHE[0].values() for d in lst]
        if not anchors:
            return True
        d_face = min(descriptor_distance(q, a, None, q.is_gray) for a in anchors)
        d_text = min(descriptor_distance(q, t, None, q.is_gray) for t in self._det_text_rejects)
        return d_face < d_text

    def s17_match_detail(self, face, min_sim: float = _S17_GUARD_DEFAULT):
        """Match del detalle-badge contra su librería propia: (nombre|None, conf, margin,
        rejected). Inerte (None, 0, 0, False) hasta que la librería se cosecha. nombre
        no-None solo si conf≥guard. Señal PRIMARIA en S17 por su localización 100% (vs 73%
        del grid). El `margin` (distancia al 2º mejor) distingue un avatar REAL (margen
        claro) de un crop espurio tipo texto '(N)' del nº de slot (conf baja + margen ~0 =
        equidistante entre refs → no es una cara; 5R.L.7.3, QA 2026-06-20)."""
        if face is None or not self._detbadge._refs:
            return None, 0.0, 0.0, False
        r = self._detbadge.match(face)
        name = r.name if (r.name is not None and r.conf >= min_sim) else None
        return name, r.conf, r.margin, r.rejected
