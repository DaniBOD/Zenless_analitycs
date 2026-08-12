"""
Fase 5R — Descriptor robusto de identidad por ícono de avatar (icon-agnóstico).

Reemplaza el descriptor débil de `agent_identifier.py` (resize 48×48 BGR + coseno
de píxeles crudos, el "imán Yixuan" que matcheaba ~todo a 0.86–0.91). Diseñado
para identificar al PJ desde su ícono circular en pantalla (badge de dueño en la
grilla S17, avatar de fila S8/S18) y reusable a futuro para íconos de W-engines y
discos cambiando solo la librería de referencia.

Híbrido CLÁSICO (solo cv2+numpy, microsegundos por comparación):
  1. Segmentación: máscara circular erosionada (anula el "aura" del fondo del filo).
  2. Normalización de color: CLAHE sobre L (Lab) → robustez a iluminación in-game.
  3. Componente A — histograma HSV H×S (paleta): filtro grueso por color pelo/ropa.
  4. Componente B — plantilla espacial Lab color-normalizada (NCC/coseno): desempate
     fino entre paletas parecidas (Zhao/Nicole) por DÓNDE está cada color.
  5. Componente C — medias de color por banda (pelo/ojos/boca): los ojos en ZZZ son
     muy distintivos.

`AvatarMatcher` agrega: librería de referencia + reject-set (círculos no-PJ:
disco, candado, rareza, slot vacío) + gate de ABSTENCIÓN (confianza + margen +
reject) — preferimos "incierto" a afirmar un PJ equivocado (RNF-02).
"""
from __future__ import annotations

import glob
import logging
import os
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app.core.stats_vocab import _norm_key

log = logging.getLogger(__name__)

# Alias de stems de `-ico` cuya normalización no coincide con el nombre de roster
# (acento/traducción/variante). El resto matchea por `_norm_key` (sin guiones).
ICO_ALIAS: dict[str, str] = {
    "Caesar": "César",
    "Trigger": "Gatillo",
    "Jane-Doe": "Jane",
    "Anby-Soldier-0": "N.º 0: Anby",
    "Soldier-11": "N.º 11",
    "Orphie": "Orfia y Magas",
    "Billy-starlight": "Billy Estelar",   # Billy Kid Estelar (v2.x) — NO es Billy (id 12)
    "Remielle": "Remielle Dan",           # el archivo usa el nombre corto; la DB, el completo
    "Seed": "Sporos",                     # nombre EN del juego; el inverso ya estaba en
                                          # `asset_resolver._AGENT_SPLASH_OVERRIDES`
}


def build_name_map(stems: list[str], roster_names: list[str]) -> dict[str, str]:
    """Mapea stem de archivo `-ico` → nombre canónico de `agents` (o el stem tal
    cual si el PJ todavía no está en la DB, p.ej. Aria/Hugo/Seed). Combina alias
    manuales + match por `_norm_key` (ignorando guiones/underscores)."""
    rk = {_norm_key(n): n for n in roster_names}
    out: dict[str, str] = {}
    for s in stems:
        if s in ICO_ALIAS:
            out[s] = ICO_ALIAS[s]
            continue
        k = _norm_key(s.replace("-", "").replace("_", ""))
        out[s] = rk.get(k, s)
    return out

# Tamaño normalizado de trabajo. Los íconos in-game rondan 40 px; 64 da margen sin
# inventar detalle.
_SIZE = 64

# Máscara circular erosionada ~6%: el filo queda fuera, así no entra el fondo
# casi-blanco/rayado del borde del recorte. Consistente con la erosión de
# `tools/crop_ico_refs.py`.
_yy, _xx = np.ogrid[:_SIZE, :_SIZE]
_ERODE = max(2.0, 0.06 * _SIZE)
_MASK = ((_xx - _SIZE / 2) ** 2 + (_yy - _SIZE / 2) ** 2) <= (_SIZE / 2 - _ERODE) ** 2
_MASK_U8 = _MASK.astype(np.uint8)

# Bins del histograma de paleta.
_H_BINS, _S_BINS = 24, 8

# Pesos del score combinado (calibrables por el harness 5R.2).
_W_HIST, _W_NCC, _W_REG = 0.40, 0.45, 0.15

# Saturación media (en el círculo) por debajo de la cual el avatar se considera GRIS (PJ no
# obtenido: el juego lo desatura). Solo informativo desde 2026-08-12: ya NO decide la métrica.
#
# Por qué dejó de decidir: era un umbral ABSOLUTO fijado en 2026-06-10 "sin muestras grises reales,
# a calibrar", y la medición mostró que no separa lo que dice. No hay bimodalidad: es una sola
# distribución continua cortada al medio. Lo que separa es la PALETA del personaje — el arte de
# Seth tiene saturación 7.3, Anby 10.6, Lycaon 16.6, todos obtenidos y a color. A esos les tiraba
# el color, que es lo único que los distingue entre sí, y los comparaba por luminancia: en la
# librería del detalle, Seth caía a 0.084 de Zhao (dos personajes de oscuro).
_GRAY_SAT_MAX = 45.0

# La ruta gris se decide RELATIVA: un avatar está grisado si tiene mucha MENOS saturación que la
# referencia contra la que se compara. Un umbral absoluto no puede expresar eso — un personaje de
# negro (7.3) y un avatar realmente grisado (10-20) se solapan; una razón sí los separa, porque
# "grisado" significa perder el color PROPIO, no tener poco.
#
# Calibrado 2026-08-12 sobre las tres librerías: entre refs legítimas del MISMO PJ la razón nunca
# baja de 0.75 (detail) ni 0.98 (row); una Ellen desaturada al 12% da 0.14. 0.25 deja aire para un
# grisado más suave sin rozar la variación normal. Medido 1-NN: detail 87% → 97%, grid 91% → 94%.
_GRAY_SAT_RATIO = 0.25

# Gates de abstención por defecto. Calibrados con el harness leave-one-out multi-ref
# sobre la cosecha real de 41 PJs (2026-06-10): con multi-ref, min_margin=0.04 da
# 96% top-1 / 0% error / 4% abstención — robustez = CERO dueño equivocado (RNF-02).
# min_conf=0.45 es el piso (todo acierto real tiene conf>0.50; el reject-set + margen
# son la guarda fina).
_MIN_CONF = 0.45
_MIN_MARGIN = 0.04
# Refs por PJ (multi-ref). Subido 6→10 (Fase 5R.C): el pase full-roster cosecha 6
# badges/PJ (slots 1-6) + acumulación entre sesiones → más variación de render por PJ
# = menor distancia-mínima en queries imperfectas (cierra "dueño incierto"). FIFO.
_MAX_REFS_PER_NAME = 10


@dataclass(frozen=True)
class AvatarDescriptor:
    """Descriptor de un ícono de avatar (ya enmascarado)."""
    hist: np.ndarray      # H×S L1-norm (paleta)
    ncc: np.ndarray       # plantilla Lab color-normalizada, media-cero norma-unidad
    regions: np.ndarray   # medias de color por banda (pelo/ojos/boca)
    gray: np.ndarray      # plantilla L (luminancia) media-cero norma-unidad — para PJ gris
    is_gray: bool         # avatar desaturado (PJ no obtenido) → matchear por luminancia


@dataclass(frozen=True)
class MatchResult:
    """Resultado del match. `name` es None cuando el matcher se ABSTIENE."""
    name: str | None
    conf: float                       # 1 - distancia del mejor (0..1)
    margin: float                     # distancia_2º - distancia_1º (>0 = más seguro)
    rejected: bool                    # True si el mejor cae en el reject-set
    top: list[tuple[str, float]]      # [(nombre, distancia), ...] top-k para log


# --------------------------------------------------------------------------- #
# Construcción del descriptor
# --------------------------------------------------------------------------- #

def _preprocess(bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Resize a _SIZE, devuelve (hsv, lab) con L (Lab) normalizado por CLAHE."""
    img = cv2.resize(bgr, (_SIZE, _SIZE), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
    lab[:, :, 0] = clahe.apply(lab[:, :, 0])
    return hsv, lab


def build_descriptor(bgr: np.ndarray) -> AvatarDescriptor | None:
    """Construye el descriptor de 3 componentes de un crop BGR del ícono."""
    if bgr is None or getattr(bgr, "size", 0) == 0:
        return None
    hsv, lab = _preprocess(bgr)

    # --- A: histograma HSV H×S sobre el círculo ---
    hist = cv2.calcHist([hsv], [0, 1], _MASK_U8, [_H_BINS, _S_BINS], [0, 180, 0, 256])
    hist = cv2.normalize(hist, hist, norm_type=cv2.NORM_L1).flatten().astype(np.float32)

    # --- B: plantilla espacial Lab color-normalizada (media-cero por canal, masked) ---
    labf = lab.astype(np.float32)
    for c in range(3):
        ch = labf[:, :, c]
        ch[_MASK] -= ch[_MASK].mean()
        ch[~_MASK] = 0.0
    ncc = labf.reshape(-1).astype(np.float32)
    n = float(np.sqrt((ncc * ncc).sum()))
    if n > 1e-6:
        ncc = ncc / n

    # --- Componente GRIS: canal L (luminancia) masked, media-cero norma-unidad.
    # Invariante a saturación → matchea un PJ gris (no obtenido) contra su ref a
    # color, porque el filtro gris del juego preserva la luz. ---
    Lf = lab[:, :, 0].astype(np.float32).copy()
    Lf[_MASK] -= Lf[_MASK].mean()
    Lf[~_MASK] = 0.0
    gray = Lf.reshape(-1)
    gn = float(np.sqrt((gray * gray).sum()))
    if gn > 1e-6:
        gray = gray / gn
    is_gray = float(hsv[:, :, 1][_MASK].mean()) < _GRAY_SAT_MAX

    # --- C: medias de color por banda (pelo/ojos/boca), H como (cos,sin) + S ---
    regions: list[float] = []
    for y0, y1 in [(0, _SIZE // 3), (_SIZE // 3, 2 * _SIZE // 3), (2 * _SIZE // 3, _SIZE)]:
        bmask = _MASK[y0:y1]
        if bmask.sum() == 0:
            regions.extend([0.0, 0.0, 0.0])
            continue
        px = hsv[y0:y1][bmask]
        hrad = px[:, 0].astype(np.float32) * (np.pi / 90.0)  # 0..180 → 0..2π
        regions.extend([
            float(np.cos(hrad).mean()),
            float(np.sin(hrad).mean()),
            float(px[:, 1].mean() / 255.0),
        ])
    return AvatarDescriptor(hist, ncc, np.asarray(regions, dtype=np.float32), gray, is_gray)


def _saturacion(d: AvatarDescriptor) -> float:
    """Saturación media (0..1) del descriptor, leída de las medias por banda de `regions`."""
    return float((d.regions[2] + d.regions[5] + d.regions[8]) / 3.0)


def _esta_grisado(q: AvatarDescriptor, ref: AvatarDescriptor) -> bool:
    """¿`q` está DESATURADO respecto de `ref`? Ver `_GRAY_SAT_RATIO`."""
    s_ref = _saturacion(ref)
    return s_ref > 1e-6 and _saturacion(q) < _GRAY_SAT_RATIO * s_ref


def descriptor_distance(a: AvatarDescriptor, b: AvatarDescriptor,
                        weights: tuple[float, float, float] | None = None,
                        gray_only: bool | None = False) -> float:
    """Distancia combinada en [0..~1] (0 = idéntico). Pesos = (hist, ncc, regiones).

    `gray_only`: `True`/`False` deciden la métrica explícitamente. **`None` = decidí vos**, y ahí
    se aplica la regla RELATIVA de `_GRAY_SAT_RATIO`: `a` es el query y `b` la referencia.
    """
    if gray_only is None:
        gray_only = _esta_grisado(a, b)
    if gray_only:
        cos = float(np.dot(a.gray, b.gray)) if a.gray.shape == b.gray.shape else -1.0
        return (1.0 - cos) / 2.0
    w_h, w_n, w_r = weights or (_W_HIST, _W_NCC, _W_REG)
    d_hist = float(cv2.compareHist(a.hist, b.hist, cv2.HISTCMP_BHATTACHARYYA))  # 0..1
    cos = float(np.dot(a.ncc, b.ncc)) if a.ncc.shape == b.ncc.shape else -1.0
    d_ncc = (1.0 - cos) / 2.0                                                   # 0..1
    d_reg = float(np.abs(a.regions - b.regions).mean()) if a.regions.shape == b.regions.shape else 1.0
    return w_h * d_hist + w_n * d_ncc + w_r * min(1.0, d_reg)


# --------------------------------------------------------------------------- #
# Matcher con librería de referencia + reject-set + abstención
# --------------------------------------------------------------------------- #

class AvatarMatcher:
    """
    Matchea un ícono contra una librería de referencia con abstención segura.

    `refs`: dict nombre → descriptor. `rejects`: lista de descriptores de círculos
    no-PJ. La librería es HÍBRIDA: se siembra con los `-ico` y se puede pisar con
    recortes in-game cosechados (mismo nombre → override) vía `add_reference`.
    """

    def __init__(self, refs: dict[str, AvatarDescriptor] | None = None,
                 rejects: list[AvatarDescriptor] | None = None,
                 min_conf: float = _MIN_CONF, min_margin: float = _MIN_MARGIN,
                 weights: tuple[float, float, float] | None = None):
        # name → LISTA de descriptores (multi-ref: -ico + N badges cosechados).
        # La distancia a un PJ = mínimo sobre sus descriptores (el más parecido).
        self._refs: dict[str, list[AvatarDescriptor]] = {}
        for name, v in (refs or {}).items():
            self._refs[name] = list(v) if isinstance(v, list) else [v]
        self._rejects: list[AvatarDescriptor] = list(rejects or [])
        self.min_conf = min_conf
        self.min_margin = min_margin
        self.weights = weights

    # ---- construcción ----
    @classmethod
    def from_folders(cls, refs_dir: str | Path, reject_dir: str | Path | None = None,
                     name_map: dict[str, str] | None = None, **kw) -> "AvatarMatcher":
        """Carga refs de `refs_dir/*.png` (stem→nombre, opcional `name_map`) y
        reject-set de `reject_dir/*.png`."""
        refs: dict[str, AvatarDescriptor] = {}
        for p in sorted(glob.glob(str(Path(refs_dir) / "*.png"))):
            stem = os.path.splitext(os.path.basename(p))[0]
            name = (name_map or {}).get(stem, stem)
            d = build_descriptor(cv2.imread(p))
            if d is not None:
                refs[name] = d
        rejects: list[AvatarDescriptor] = []
        if reject_dir and Path(reject_dir).is_dir():
            for p in sorted(glob.glob(str(Path(reject_dir) / "*.png"))):
                d = build_descriptor(cv2.imread(p))
                if d is not None:
                    rejects.append(d)
        m = cls(refs, rejects, **kw)
        log.info("AvatarMatcher: %d refs + %d rejects (%s)", len(refs), len(rejects), refs_dir)
        return m

    # ---- mantenimiento de la librería ----
    @property
    def names(self) -> list[str]:
        return list(self._refs.keys())

    def add_reference(self, name: str, bgr_or_desc, max_per_name: int = _MAX_REFS_PER_NAME) -> bool:
        """Agrega una referencia al PJ `name` (p.ej. cosecha in-game). Multi-ref:
        se acumulan hasta `max_per_name` por PJ (la cosecha más nueva desplaza a la
        más vieja)."""
        d = bgr_or_desc if isinstance(bgr_or_desc, AvatarDescriptor) else build_descriptor(bgr_or_desc)
        if d is None or not name:
            return False
        lst = self._refs.setdefault(name, [])
        lst.append(d)
        if len(lst) > max_per_name:
            del lst[0]
        return True

    def add_reject(self, bgr_or_desc) -> bool:
        d = bgr_or_desc if isinstance(bgr_or_desc, AvatarDescriptor) else build_descriptor(bgr_or_desc)
        if d is None:
            return False
        self._rejects.append(d)
        return True

    # ---- persistencia (multi-ref) ----
    def save(self, path) -> None:
        """Serializa las refs cosechadas a .npz (aplana todas las instancias)."""
        names, hist, ncc, reg, gray, isg = [], [], [], [], [], []
        for name, lst in self._refs.items():
            for d in lst:
                names.append(name); hist.append(d.hist); ncc.append(d.ncc)
                reg.append(d.regions); gray.append(d.gray); isg.append(d.is_gray)
        if not names:
            return
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            np.savez(str(path), names=np.array(names, dtype=object),
                     hist=np.stack(hist), ncc=np.stack(ncc), regions=np.stack(reg),
                     gray=np.stack(gray), is_gray=np.array(isg, dtype=bool))
        except Exception:
            log.exception("AvatarMatcher.save falló")

    def load_merge(self, path) -> int:
        """Carga refs de un .npz y las FUSIONA (multi-ref). Devuelve cuántas cargó."""
        if not Path(path).exists():
            return 0
        try:
            data = np.load(str(path), allow_pickle=True)
            # RNF-06: leer cada array UNA vez. `data["ncc"]` recarga la array completa del
            # npz en CADA acceso, y `data["ncc"][i]` es una VIEW que mantiene viva esa array
            # completa (~23 MB) → con N refs se retenían N copias completas (~28 GB en el
            # arranque con las 3 librerías). `.copy()` deja cada descriptor con su fila chica
            # y libera las arrays completas al salir. Ver audit/mem_diag_20260613.md.
            names = data["names"]
            hist, ncc = data["hist"], data["ncc"]
            reg, gray, isg = data["regions"], data["gray"], data["is_gray"]
            n = 0
            for i in range(len(names)):
                d = AvatarDescriptor(hist[i].copy(), ncc[i].copy(), reg[i].copy(),
                                     gray[i].copy(), bool(isg[i]))
                self._refs.setdefault(str(names[i]), []).append(d)
                n += 1
            return n
        except Exception:
            log.exception("AvatarMatcher.load_merge falló")
            return 0

    def similarity_to(self, bgr_or_desc, name: str) -> float | None:
        """Similitud (1 - distancia mínima) del query a las refs de UN PJ. None si el
        PJ no tiene refs. Respeta la ruta gris si el query es desaturado."""
        q = bgr_or_desc if isinstance(bgr_or_desc, AvatarDescriptor) else build_descriptor(bgr_or_desc)
        lst = self._refs.get(name)
        if q is None or not lst:
            return None
        d = min(descriptor_distance(q, r, self.weights, None) for r in lst)
        return 1.0 - d

    # ---- match ----
    def match(self, bgr_or_desc) -> MatchResult:
        """Identifica el ícono. Se ABSTIENE (name=None) si conf<min_conf, o
        margen<min_margin, o el mejor cae más cerca del reject-set que de un PJ."""
        q = bgr_or_desc if isinstance(bgr_or_desc, AvatarDescriptor) else build_descriptor(bgr_or_desc)
        if q is None or not self._refs:
            return MatchResult(None, 0.0, 0.0, False, [])
        # La ruta gris se decide POR COMPARACIÓN (`gray_only=None`), no por una propiedad del
        # query: un personaje de paleta oscura no es un PJ grisado, y decidirlo mirando solo al
        # query hacía que Seth y Zhao —los dos de oscuro— se compararan sin color.
        gray_only = None
        # distancia a un PJ = mínimo sobre sus descriptores (multi-ref)
        scored = sorted(
            ((name, min(descriptor_distance(q, d, self.weights, gray_only) for d in lst))
             for name, lst in self._refs.items()),
            key=lambda t: t[1],
        )
        best_name, d1 = scored[0]
        d2 = scored[1][1] if len(scored) > 1 else 1.0
        conf = max(0.0, 1.0 - d1)
        margin = d2 - d1
        # reject-set: ¿el query está más cerca de un no-PJ que del mejor PJ?
        rejected = False
        if self._rejects:
            d_rej = min(descriptor_distance(q, r, self.weights, gray_only) for r in self._rejects)
            rejected = d_rej <= d1
        name = best_name
        if conf < self.min_conf or margin < self.min_margin or rejected:
            name = None  # abstención
        return MatchResult(name, round(conf, 3), round(margin, 3), rejected, scored[:5])
