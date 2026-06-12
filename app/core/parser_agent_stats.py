"""
Hito 2.8 — Parser de stats de agente: frame OCR -> AgentStatsParsed.
Extrae los 11 atributos base + nombre + rol + elemento del personaje
desde la pantalla S18 (Perfil agente -> pestaña Atributos base).

Dos modos de operacion:
- Backend PaddleOCR: OCR una sola vez sobre frame completo, extrae por regex
  del texto concatenado. Valida rol contra DB para filtrar stats segun tipo.
- Backend Tesseract/otro: OCR per-ROI (22 crops individuales).

Layout de columnas (confirmado por DaniBOD):
  Columna izquierda:  Nivel | PV | Defensa | Prob. CRIT | Tasa Anomalia | [varia segun rol]
  Columna derecha:    (vacio) | Ataque | Impacto | Dano CRIT | Maestria Anomalia | Recup. Energia

  El slot bottom-left varia segun el rol:
  - Atacante/Aturdimiento/Defensa/Soporte: Tasa de Perforacion
  - Anomalia/Disruptivos: Fuerza Bruta (ignorada por el parser actual)
"""
from __future__ import annotations

import re
import sqlite3
import tomllib
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from app.core.ocr_backend import OcrBackend

from app.core.capturer import crop_named_roi

# Roles validos en DB
_ROLES_DB: set[str] = {
    "ataque", "anomalia", "anomalia", "aturdimiento", "defensa",
    "soporte", "disruptivos",
}
_ELEMENTOS_DB: set[str] = {
    "fisico", "fuego", "hielo", "electrico", "eter",
    # Viento (Wind): elemento estándar nuevo, incorporado proactivamente al
    # dominio para PJs futuros (decisión DaniBOD 2026-06-01). Aún sin agentes.
    "viento",
}
# Mapping OCR noise -> roles canonicales (legacy, lowercase)
_ROL_OCR_MAP: dict[str, str] = {
    "auxiliar": "soporte",
    "aturdidor": "aturdimiento",
    "anomalo": "anomalia",
    "disruptivo": "disruptivos",
}

# ---------------------------------------------------------------------------
# R1 (2026-05-31) — Rol + elemento desde PANTALLA (ground truth, autoritativo).
# La pantalla muestra el nombre display ZZZ ("Ígneo", "Aturdidor", "Tinta
# áurica"); la DB guarda otra forma ("Fuego", "Aturdimiento") y a veces tiene
# data vieja/placeholder (ej.: Ju Fufu figuraba "Soporte" en DB pero la pantalla
# dice "Aturdidor"). Por RNF-02, la PANTALLA manda; la DB queda como respaldo si
# el OCR no lee. Las llaves están sin acentos y en minúscula (se matchea sobre
# texto normalizado con _strip_accents); el valor es la forma canónica de la DB.
#
# POLÍTICA DE ELEMENTOS (DaniBOD 2026-06-01, mig 08): los atributos "especiales"
# del juego se mapean a su EQUIVALENTE ESTÁNDAR, porque heredan los modificadores
# del estándar y el resto del sistema razona sobre los 6 estándar:
#   Tinta áurica (Auric Ink, Yixuan)   -> Éter
#   Escarcha/Frost (Miyabi)            -> Hielo
#   Honed Edge (Ye Shunguang)          -> Físico
# Viento (Wind) SÍ es un estándar nuevo (no equivalente a otro) y tiene su propia
# entrada para PJs futuros.
# ---------------------------------------------------------------------------
_ELEMENTO_SCREEN_MAP: dict[str, str] = {
    "fisico":       "Físico",
    "igneo":        "Fuego",
    "gelido":       "Hielo",
    "escarcha":     "Hielo",      # Frost (Miyabi) ≡ Hielo
    "electrico":    "Eléctrico",
    "eter":         "Éter",
    "tinta aurica": "Éter",       # Auric Ink (Yixuan) ≡ Éter
    "aurica":       "Éter",
    "viento":       "Viento",     # Wind (PJs futuros) — estándar nuevo
}
_ROL_SCREEN_MAP: dict[str, str] = {
    "ataque":       "Ataque",
    "aturdidor":    "Aturdimiento",
    "aturdimiento": "Aturdimiento",
    "anomalia":     "Anomalía",
    "anomalo":      "Anomalía",
    "soporte":      "Soporte",
    "auxiliar":     "Soporte",
    "defensa":      "Defensa",
    "disruptivo":   "Disruptivos",
    "disruptivos":  "Disruptivos",
    "destrozo":     "Disruptivos",
}


def _strip_accents(s: str) -> str:
    """Quita tildes/diacríticos para matchear OCR con/sin acentos."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _canon_elemento(text: str) -> str | None:
    """Detecta el elemento display ZZZ en `text` y devuelve la forma canónica DB."""
    t = _strip_accents(text).lower()
    for key, canon in _ELEMENTO_SCREEN_MAP.items():
        if key in t:
            return canon
    return None


def _canon_rol(text: str) -> str | None:
    """Detecta el rol display ZZZ en `text` y devuelve la forma canónica DB."""
    t = _strip_accents(text).lower()
    for key, canon in _ROL_SCREEN_MAP.items():
        if key in t:
            return canon
    return None


def _banner_rol_elem_region(full_text: str) -> str:
    """
    Región del banner que contiene elemento + rol: desde 'MAX' (o inicio) hasta
    el primer 'PV'. Se corta antes de los stats para NO capturar 'Anomalía' de
    los labels 'Tasa/Maestría de Anomalía' (que contaminarían el rol).
    """
    idx_pv = full_text.find("PV")
    region = full_text[:idx_pv] if idx_pv > 0 else full_text[:200]
    mi = region.rfind("MAX")
    if mi >= 0:
        return region[mi + 3:]
    return region


def _name_region(full_text: str) -> str:
    """Región del nombre: desde el inicio hasta 'Nivel'/'MAX'."""
    for anchor in ("Nivel", "NIVEL", "Nivol", "MAX"):
        idx = full_text.find(anchor)
        if idx > 0:
            return full_text[:idx]
    return full_text[:120]


def _name_appears_twice(full_text: str, candidate: str) -> bool:
    """
    R2: el nombre aparece DOS veces en el banner (blanco grande + gris tenue,
    a veces con letras espaciadas 'J u F u f u'). Colapsamos espacios y acentos
    para que ambas variantes matcheen. >=2 ocurrencias ⇒ nombre de alta
    confianza (descarta facciones/UI que aparecen una sola vez).
    """
    cand = _strip_accents(candidate).lower().replace(" ", "")
    if len(cand) < 3:
        return False
    region = _strip_accents(_name_region(full_text)).lower().replace(" ", "")
    return region.count(cand) >= 2

# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------

_RE_NUMBER = re.compile(r"(\d+(?:[.,]\d+)?)")
_RE_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

_STAT_KEYS = [
    "nivel", "pv", "ataque", "defensa", "impacto",
    "prob_crit", "dano_crit", "tasa_anomalia", "maestria_anomalia",
    "tasa_perforacion", "recup_energia", "fuerza_bruta", "adrenalina",
]

# Keywords para matchear nombres de stat contra texto OCR.
# Orden: mas especifico primero para evitar matches parciales.
_STAT_KEYWORDS: dict[str, list[str]] = {
    "nivel":               ["Nv"],
    "pv":                  ["PV"],
    "ataque":              ["Ataque", "ATQ"],
    "defensa":             ["Defensa", "DEF"],
    "impacto":             ["Impacto", "IMP"],
    "prob_crit":           ["Prob", "Probabilidad", "CRIT"],
    "dano_crit":           ["Dano", "Critico"],
    "tasa_anomalia":       ["Tasa", "Anomalia"],
    "maestria_anomalia":   ["Maestria", "Anomalia"],
    "tasa_perforacion":    ["Tasa", "Perforacion", "PEN"],
    "recup_energia":       ["Recuperacion", "Energia", "Recup"],
}

# Carga de ROIs (una sola vez a nivel modulo)
_ROIS_CACHE: dict | None = None


def _get_rois() -> dict:
    global _ROIS_CACHE
    if _ROIS_CACHE is None:
        toml_path = Path(__file__).parent.parent / "config" / "rois.toml"
        with open(toml_path, "rb") as f:
            _ROIS_CACHE = tomllib.load(f)
    return _ROIS_CACHE


def _roi_centroid(key: str) -> tuple[float, float]:
    """Devuelve (cx_norm, cy_norm) del centro de una ROI."""
    rois = _get_rois()
    entry = rois.get("perfil_agente_atributos", {}).get(key)
    if not entry or len(entry) < 4:
        return (0.5, 0.5)
    x, y, w, h = entry
    return (x + w / 2, y + h / 2)


def _centroid_in_roi(cx: float, cy: float, roi_key: str) -> bool:
    """True si (cx_norm, cy_norm) cae dentro de la ROI."""
    rois = _get_rois()
    entry = rois.get("perfil_agente_atributos", {}).get(roi_key)
    if not entry or len(entry) < 4:
        return False
    x, y, w, h = entry
    return x <= cx <= x + w and y <= cy <= y + h


@dataclass
class AgentStatsParsed:
    """Resultado estructurado de la extraccion de atributos base del agente."""
    nivel: int | None = None
    pv: int | None = None
    ataque: int | None = None
    defensa: int | None = None
    impacto: int | None = None
    prob_crit: float | None = None
    dano_crit: float | None = None
    tasa_anomalia: int | None = None
    maestria_anomalia: int | None = None
    tasa_perforacion: float | None = None
    recuperacion_energia: float | None = None
    fuerza_bruta: int | None = None
    # Acumulación Automática de Adrenalina — slot inferior-derecho EXCLUSIVO de
    # Disruptivos (reemplaza a recuperacion_energia, igual que fuerza_bruta
    # reemplaza a tasa_perforacion). Hito 2.8 QA 2026-05-31.
    acumulacion_adrenalina: int | None = None
    confianza_global: float = 0.0
    notas: list[str] = field(default_factory=list)
    # Identificacion del agente (extraida del OCR + validada contra DB)
    agente_nombre: str | None = None
    rol: str | None = None
    elemento: str | None = None


# Campos numericos que el aggregator merge entre capturas. agente_nombre/rol/
# elemento se manejan especialmente (cambio de agente = reset). confianza_global
# y notas no se mergean — se toma el valor de la captura mas reciente.
_AGGREGATABLE_FIELDS: tuple[str, ...] = (
    "nivel", "pv", "ataque", "defensa", "impacto",
    "prob_crit", "dano_crit",
    "tasa_anomalia", "maestria_anomalia",
    "tasa_perforacion", "recuperacion_energia", "fuerza_bruta",
    "acumulacion_adrenalina",
)


class AgentStatsAggregator:
    """
    Acumula stats por agente entre capturas consecutivas para madurar la
    extraccion.

    Tesseract es no-deterministico frame-a-frame: cada F8 puede capturar
    distintos stats correctamente, otros None. El aggregator preserva los
    "best-known" valores: si la nueva captura tiene un campo None pero el
    aggregator ya tenia valor previo (mismo agente), se conserva el previo.

    Reset implicito cuando cambia el agente_nombre (e.g. de Nangong Yu a
    Yuzuha) — los stats anteriores no aplican.

    El campo `confianza_global` y `notas` se sobreescriben con la captura
    nueva. El nombre/rol/elemento se preservan solo mientras el agente sea
    el mismo (con fallback a la nueva captura si esa lo identifico mejor).
    """

    def __init__(self) -> None:
        self._best: AgentStatsParsed | None = None
        # Tracker de cuantas veces cada campo ha sido emitido (debug)
        self._field_hits: dict[str, int] = {}

    @property
    def has_any(self) -> bool:
        return self._best is not None

    @property
    def current_agent(self) -> str | None:
        return self._best.agente_nombre if self._best else None

    def reset(self) -> None:
        self._best = None
        self._field_hits.clear()

    def merge(self, new: AgentStatsParsed) -> AgentStatsParsed:
        """
        Mezcla `new` con el estado acumulado y devuelve el resultado.

        Reglas:
          1. Si el agente cambia (nuevo nombre OCR distinto y se identificó
             en DB), resetear y empezar fresh con `new`.
          2. Para cada campo aggregatable: si `new.field` no es None, usar ese
             valor. Si es None, conservar el del aggregator (si tenia).
          3. Si `new.agente_nombre` está poblado y el aggregator no tiene
             nombre todavia, adoptarlo (junto a rol/elemento).
        """
        if new is None:
            return self._best if self._best else AgentStatsParsed()

        # Detección de cambio de agente por DIVERGENCIA DE STATS (defensa en
        # profundidad, 2026-06-02). Aunque el OCR del nombre falle en un frame
        # (None), un salto grande de PV o Ataque implica que es OTRO agente: hay
        # que resetear para NO heredar la identidad del agente anterior (bug QA
        # 2026-06-02: Lucy se mostraba como "Anby" porque el aggregator conservó
        # el nombre viejo y solo actualizó los números). La pantalla S18 es
        # estática, así que entre frames del MISMO agente el PV es idéntico; un
        # salto >6% es inequívocamente otro personaje.
        if self._best is not None:
            for f in ("pv", "ataque"):
                a = getattr(self._best, f)
                b = getattr(new, f)
                if a and b and abs(b - a) / a > 0.06:
                    self.reset()
                    break

        # Detectar cambio de agente: si tanto el aggregator como new tienen
        # nombre identificado y son distintos -> reset.
        if (self._best is not None
                and self._best.agente_nombre
                and new.agente_nombre
                and self._best.agente_nombre != new.agente_nombre):
            self.reset()

        if self._best is None:
            # Primera captura — clonar new como punto de partida
            self._best = AgentStatsParsed(
                nivel=new.nivel, pv=new.pv, ataque=new.ataque,
                defensa=new.defensa, impacto=new.impacto,
                prob_crit=new.prob_crit, dano_crit=new.dano_crit,
                tasa_anomalia=new.tasa_anomalia,
                maestria_anomalia=new.maestria_anomalia,
                tasa_perforacion=new.tasa_perforacion,
                recuperacion_energia=new.recuperacion_energia,
                fuerza_bruta=new.fuerza_bruta,
                acumulacion_adrenalina=new.acumulacion_adrenalina,
                confianza_global=new.confianza_global,
                notas=list(new.notas),
                agente_nombre=new.agente_nombre,
                rol=new.rol,
                elemento=new.elemento,
            )
            for k in _AGGREGATABLE_FIELDS:
                if getattr(self._best, k) is not None:
                    self._field_hits[k] = 1
            return self._best

        # Merge: nuevo valor gana solo si no es None
        for k in _AGGREGATABLE_FIELDS:
            new_val = getattr(new, k)
            if new_val is not None:
                setattr(self._best, k, new_val)
                self._field_hits[k] = self._field_hits.get(k, 0) + 1

        # Si el aggregator no tenia nombre pero new lo extrajo, adoptarlo
        if not self._best.agente_nombre and new.agente_nombre:
            self._best.agente_nombre = new.agente_nombre
        if not self._best.rol and new.rol:
            self._best.rol = new.rol
        if not self._best.elemento and new.elemento:
            self._best.elemento = new.elemento

        # Siempre overwrite confianza/notas con la captura mas reciente
        self._best.confianza_global = new.confianza_global
        self._best.notas = list(new.notas)
        return self._best


# ---------------------------------------------------------------------------
# Parsers de valor
# ---------------------------------------------------------------------------

def _clean_number(raw: str) -> str:
    """Limpia texto numerico: quita espacios entre digitos, separador miles."""
    s = raw.strip()
    s = re.sub(r"(?<=\d)\s+(?=\d)", "", s)  # "10 797" -> "10797"
    return s


def _parse_int(raw: str | None) -> int | None:
    if not raw:
        return None
    cleaned = _clean_number(raw)
    m = _RE_NUMBER.search(cleaned)
    if not m:
        return None
    return int(m.group(1).replace(",", ".").split(".")[0])


def _parse_float(raw: str | None) -> float | None:
    if not raw:
        return None
    cleaned = _clean_number(raw)
    m = _RE_PERCENT.search(cleaned)
    if m:
        return float(m.group(1))
    m = _RE_NUMBER.search(cleaned)
    if m:
        return float(m.group(1).replace(",", "."))
    return None


def _normalize_percent(val: float | None) -> float | None:
    """
    Normaliza un valor de % a fracción 0-1+ (la fracción puede ser >1 para
    stats como Daño Crítico, que legítimamente supera 100%).

    Regla: si val > 1.0 viene expresado en % → dividir por 100.
      19.4 → 0.194 ✓   (Prob. Crítico)
      93.2 → 0.932 ✓   (Daño Crítico < 100%)
      162  → 1.62  ✓   (Daño Crítico > 100% — fracción válida >1)
      65   → 0.65  ✓
      0.5  → 0.5   ✓   (ya en fracción)

    NOTA (Hito 2.8, QA 2026-05-31): se eliminó el `/10` extra que intentaba
    "recuperar" un punto decimal perdido por OCR (194→19.4). Ese heurístico
    corrompía valores legítimos ≥100% (Daño Crítico 162% → 0.162). Con
    PaddleOCR los decimales se leen de forma confiable, así que el hack ya
    no aporta y violaba RNF-02 (inyectaba un valor concreto incorrecto). Si
    el OCR llegara a perder un decimal, el valor resultante queda visiblemente
    fuera de rango y se detecta, en vez de corromperse en silencio.
    """
    if val is None:
        return None
    if val > 1.0:
        val = val / 100.0
    return val


# ---------------------------------------------------------------------------
# Modo 1: PaddleOCR full-frame
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# DB lookup
# ---------------------------------------------------------------------------

# Fallback dev-only. La DB REAL se resuelve en runtime con connection._resolve_db_path()
# (honra DANIBOD_DB_PATH + la copia writable del .exe). Usar _DB_PATH directo desacopla
# el roster del identificador de la DB que usa el resto de la app: en el .exe frozen
# apunta a la copia bundleada/vieja → un PJ recién onboardeado no se identifica por stats.
_DB_PATH = Path(__file__).resolve().parent.parent.parent / "db" / "danibod_zzz_v2.db"


def _active_db_path() -> Path:
    """DB activa, alineada con el resto de la app (override DANIBOD_DB_PATH + .exe)."""
    try:
        from app.db.connection import _resolve_db_path
        return _resolve_db_path()
    except Exception:
        return _DB_PATH


def _normalizar_rol(ocr_text: str) -> str | None:
    """Normaliza texto OCR a rol canonico de DB."""
    t = ocr_text.lower().strip()
    if t in _ROLES_DB:
        return t
    for alias, canon in _ROL_OCR_MAP.items():
        if alias in t:
            return canon
    return None


# ---------------------------------------------------------------------------
# Matcher de agente (Capas 1+2+3, 2026-06-01)
#   Capa 1: matching NORMALIZADO (sin acentos / case-insensitive). El LIKE de
#           SQLite es sensible a acentos → "Lucia"!="Lucía", "Cesar"!="César".
#   Capa 2: matching DIFUSO (token-subset + ratio de edición) contra TODO el
#           roster → tolera misreads de OCR (Shunguang, Nekomata) y elimina los
#           falsos positivos del LIKE-substring (Nekomata->Manato).
#   Capa 3: DESAMBIGUACIÓN por rol+elemento de pantalla → resuelve homónimos
#           (Anby vs N.º 0: Anby, variantes de Billy) eligiendo el agente cuyo
#           rol/elemento coincide con lo leído de pantalla.
# ---------------------------------------------------------------------------

# Umbral mínimo de similitud de nombre para considerar un match (0..1).
_NAME_MIN_SIM = 0.55
# Pesos del bonus de desambiguación por rol/elemento.
_ROL_MATCH_BONUS = 0.30
_ROL_MISS_PENALTY = 0.20
_ELEM_MATCH_BONUS = 0.20
_ELEM_MISS_PENALTY = 0.15


def _norm_name(s: str) -> str:
    """Normaliza un nombre para matching: sin acentos, minúscula, alfanumérico."""
    s = _strip_accents(s or "").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()


_ROSTER_CACHE: list[dict] | None = None


def _get_roster() -> list[dict]:
    """
    Carga (y cachea) el roster de la DB: lista de dicts con nombre/rol/elemento
    + forma normalizada y tokens. Read-only. Si la DB no se puede abrir,
    devuelve lista vacía (el caller cae a OCR puro).
    """
    global _ROSTER_CACHE
    if _ROSTER_CACHE is None:
        roster: list[dict] = []
        try:
            conn = sqlite3.connect(f"file:{_active_db_path()}?mode=ro", uri=True)
            for (nombre, rol, elemento, pv, ataque, defensa,
                 prob_critico, dano_critico) in conn.execute(
                "SELECT nombre, rol, elemento, pv, ataque, defensa, "
                "prob_critico, dano_critico FROM agents"
            ):
                norm = _norm_name(nombre)
                roster.append({
                    "nombre": nombre, "rol": rol, "elemento": elemento,
                    "norm": norm, "tokens": set(norm.split()),
                    # Stats del build del usuario (autoritativo) para
                    # identificación por vector — ver _identify_by_stats.
                    # prob/dano_critico se guardan como FRACCIÓN (DB usa %)
                    # para comparar con los stats parseados (ya en fracción).
                    "pv": pv, "ataque": ataque, "defensa": defensa,
                    "prob_crit": (prob_critico / 100.0) if prob_critico is not None else None,
                    "dano_crit": (dano_critico / 100.0) if dano_critico is not None else None,
                })
            conn.close()
        except Exception:
            roster = []
        _ROSTER_CACHE = roster
    return _ROSTER_CACHE


def _name_similarity(ocr_tokens: set[str], ocr_norm: str,
                     db_tokens: set[str], db_norm: str) -> float:
    """
    Similitud de nombre 0..1. 1.0 si un conjunto de tokens contiene al otro
    (nombre DB ⊆ OCR, o OCR ⊆ nombre DB — cubre "Anby" vs "N.º 0: Anby" y
    nombres display con prefijo de facción). Si no, max(ratio de edición,
    jaccard de tokens).
    """
    if not db_tokens or not ocr_tokens:
        return 0.0
    if db_tokens <= ocr_tokens or ocr_tokens <= db_tokens:
        return 1.0
    ratio = SequenceMatcher(None, db_norm, ocr_norm).ratio()
    jaccard = len(db_tokens & ocr_tokens) / len(db_tokens | ocr_tokens)
    return max(ratio, jaccard)


def _match_agent(
    name_text: str,
    rol_screen: str | None = None,
    elem_screen: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    """
    Identifica al agente contra el roster (Capas 1+2+3).

    `name_text` es la región del nombre OCR (puede traer facción + nombre 2x).
    `rol_screen`/`elem_screen` son el rol/elemento leídos de pantalla (R1), que
    desambiguan homónimos. Retorna (nombre_canon, rol_db, elemento_db) del mejor
    match, o (None, None, None) si ninguno supera el umbral de similitud.
    """
    ocr_norm = _norm_name(name_text)
    if not ocr_norm:
        return (None, None, None)
    ocr_tokens = set(ocr_norm.split())

    rol_s = _strip_accents(rol_screen).lower() if rol_screen else None
    elem_s = _strip_accents(elem_screen).lower() if elem_screen else None

    best = None
    best_score = -1.0
    for ag in _get_roster():
        name_sim = _name_similarity(ocr_tokens, ocr_norm, ag["tokens"], ag["norm"])
        if name_sim < _NAME_MIN_SIM:
            continue
        # Capa 3: bonus/penalización por rol + elemento de pantalla.
        bonus = 0.0
        if rol_s and ag["rol"]:
            bonus += _ROL_MATCH_BONUS if _strip_accents(ag["rol"]).lower() == rol_s else -_ROL_MISS_PENALTY
        if elem_s and ag["elemento"]:
            bonus += _ELEM_MATCH_BONUS if _strip_accents(ag["elemento"]).lower() == elem_s else -_ELEM_MISS_PENALTY
        score = name_sim + bonus
        if score > best_score:
            best_score = score
            best = ag
    if best is None:
        return (None, None, None)
    return (best["nombre"], best["rol"], best["elemento"])


def _lookup_agent(nombre_ocr: str) -> tuple[str | None, str | None, str | None]:
    """Compat: match por nombre sin contexto de rol/elemento (Capas 1+2)."""
    return _match_agent(nombre_ocr)


# ---------------------------------------------------------------------------
# Capa 4 (2026-06-02) — Identificación por STATS (backbone determinista).
#
# Hallazgo QA 2026-06-02: el OCR del nombre estilizado falla para homónimos
# (N.º 0: Anby vs Anby) y nombres display largos (Lucy se muestra como
# "Luciana de Montefio"). PERO los stats en pantalla coinciden EXACTO con el
# build guardado en la DB del usuario (dato autoritativo, RNF-02). El vector
# (pv, ataque, prob_crit, dano_crit) identifica al agente con margen amplio
# incluso entre DPS de stats parecidos — verificado contra los 46 del roster:
# el 2do mejor candidato queda a >5% para Soldier 0 Anby y >14% para Lucy.
#
# Se usa como señal PRIMARIA cuando hay stats suficientes (pv+atk+algún crit).
# El matcher de nombre (Capas 1/2/3) queda de fallback para agentes no
# sincronizados (stats DB desactualizados) o fuera del roster.
# ---------------------------------------------------------------------------

# Error relativo medio máximo para aceptar un match por stats.
_STATS_ID_MAX_DIST = 0.045
# El 2do mejor candidato debe estar al menos esto más lejos (evita ambigüedad
# entre dos agentes de stats parecidos cuando el build difiere del de la DB).
_STATS_ID_MIN_GAP = 0.030


def _stat_rel_err(x: float | None, a: float | None) -> float | None:
    """Error relativo |x-a|/|a|, o None si falta algún operando."""
    if x is None or a is None or a == 0:
        return None
    return abs(x - a) / abs(a)


def _stats_distance(stats: dict, ag: dict) -> float | None:
    """
    Error relativo medio entre los stats de pantalla y los del agente (DB).

    Requiere PV + Ataque como ancla y al menos un crit (Prob/Daño) para
    discriminar entre DPS de PV/ATK parecidos. Devuelve None si no hay
    suficientes campos comparables (el agente cae al matcher de nombre).
    """
    if stats.get("pv") is None or stats.get("ataque") is None:
        return None
    if stats.get("prob_crit") is None and stats.get("dano_crit") is None:
        return None
    pairs = [
        (stats.get("pv"), ag.get("pv")),
        (stats.get("ataque"), ag.get("ataque")),
        (stats.get("defensa"), ag.get("defensa")),
        (stats.get("prob_crit"), ag.get("prob_crit")),
        (stats.get("dano_crit"), ag.get("dano_crit")),
    ]
    errs = [e for e in (_stat_rel_err(x, a) for x, a in pairs) if e is not None]
    if len(errs) < 3:
        return None
    return sum(errs) / len(errs)


def _identify_by_stats(stats: dict | None) -> dict | None:
    """
    Identifica al agente por su vector de stats contra el roster.

    Retorna el dict del agente (con nombre/rol/elemento canónicos de la DB)
    o None si: faltan stats, ningún agente del roster tiene stats comparables,
    el mejor match supera el umbral de error, o hay ambigüedad (2 agentes
    igual de cerca). Conservador por RNF-02: ante la duda, None → fallback.
    """
    if not stats:
        return None
    ranked: list[tuple[float, dict]] = []
    for ag in _get_roster():
        d = _stats_distance(stats, ag)
        if d is not None:
            ranked.append((d, ag))
    if not ranked:
        return None
    ranked.sort(key=lambda t: t[0])
    best_d, best_ag = ranked[0]
    if best_d > _STATS_ID_MAX_DIST:
        return None
    if len(ranked) > 1 and (ranked[1][0] - best_d) < _STATS_ID_MIN_GAP:
        return None  # ambiguo: dos agentes igual de cerca
    return best_ag


# ---------------------------------------------------------------------------
# Regex para full-frame OCR (Paddle o Tesseract)
# ---------------------------------------------------------------------------
# Todos los regex se aplican sobre texto NORMALIZADO por _normalize_ocr_text:
# minúsculas + accents stripped + caracteres OCR-basura comunes mapeados.
# Esto los hace robustos contra typos OCR ("pV", "Iimpacto", "Da�o", etc.)
# tanto en Paddle como en Tesseract.

_RE_NIVEL = re.compile(r"(?:nivel|nv\.?)\s*(\d{1,2})")
# PV: tolera "pv", "p v", concatenación "pv10797", separación "10 797"
_RE_PV = re.compile(r"\bp\s*v\s*(\d{1,2}(?:\s*\d{3})?)")
# Ataque: case-insensitive (ya normalizado)
_RE_ATAQUE = re.compile(r"\bataque\s*(\d+)")
_RE_DEFENSA = re.compile(r"\bdefensa\s*(\d+)")
# Impacto: tolera typos OCR como "iimpacto", "rmpacto", "ímpacto"
_RE_IMPACTO = re.compile(r"\b[il]+m\s*pacto\s*(\d+)")
# Prob CRIT: "probabilidad de 19.4%" — tolera "prob", "probabili", etc.
_RE_PROB_CRIT = re.compile(r"prob\w*\s*(?:de\s*)?(?:critico|crit)?\s*(\d+(?:\.\d+)?)\s*%")
# Daño Crítico: "dano critico 93.2 %" — accents ya stripped por normalizador
_RE_DANO_CRIT = re.compile(r"da\w{0,3}o\s*crit\w*\s*(\d+(?:\.\d+)?)\s*%")
# Tasa de Anomalía
_RE_TASA_ANOMALIA = re.compile(r"tasa\s*(?:de\s*)?anomal\w*\s*(\d+)")
# Maestría de Anomalía
_RE_MAESTRIA_ANOMALIA = re.compile(r"maestr\w*\s*(?:de\s*)?anomal\w*\s*(\d+)")
# Fuerza Bruta (disruptivos)
_RE_FUERZA_BRUTA = re.compile(r"fuerza\s*bruta\s*(\d+)")
# PEN: SOLO "Tasa de Perforacion" (excluye "Fuerza Bruta")
# El número debe estar dentro de ~10 chars del label y seguido por '%'
# para evitar capturar números de otras filas (e.g. el "20" del "X 20%" de
# Y Pistas de disco que aparece más abajo en el panel).
_RE_TASA_PERFORACION = re.compile(
    r"tasa\s*(?:de\s*)?perfor\w*[^\d%\n]{0,10}(\d+(?:\.\d+)?)\s*%"
)
# Recup Energía: "Recuperación de Energía" se renderiza en 2 LÍNEAS en el
# juego ("Recuperación de" / "Energía") y PaddleOCR las lee por filas, así que
# el VALOR (e.g. "1.2") suele quedar JUSTO ANTES del token "energia" en el
# texto concatenado: "...perforacion 0 % 1.2 energia...".
#
# Bug histórico (QA 2026-05-31): el patrón viejo `(?:recup|energ|adrenal)...(\d)`
# matcheaba "recuperacion" y luego agarraba el PRIMER dígito siguiente, que era
# el "0" de "Tasa de Perforación 0 %" de la fila de al lado → ER=0.0 (mal).
#
# Orden de alternativas (re.search devuelve el match más a la izquierda; el loop
# de extracción toma el primer grupo no-None):
#   (a) "<valor> energia"          — layout 2-líneas real (caso principal)
#   (b) "recup... <valor>"         — fallback si el valor va después del label
#                                     (ventana corta {0,12} para no cruzar filas)
#   (c) "adrenalina <N>"           — Disruptivos: el slot inferior-derecho es
#                                     "Acumulación Automática de Adrenalina"
_RE_RECUP_ENERGIA = re.compile(
    r"(\d+(?:\.\d+)?)[^\d\n]{0,4}?energ\w*"   # "<valor> [ruido] energia" ("2.5 v energia")
    r"|recup\w*[^\d\n]{0,12}?(\d+(?:\.\d+)?)"  # "recup... <valor>"
)
# Acumulación Automática de Adrenalina (slot inferior-derecho de Disruptivos).
# Es un campo SEPARADO de recuperacion_energia: aparece SOLO en Disruptivos y
# tiene escala distinta (entero pequeño, e.g. 2). El label se renderiza como
# "Acumulación Automática de / Adrenalina" → el valor suele quedar tras el token.
_RE_ADRENALINA = re.compile(r"adrenal\w*[^\d\n]{0,20}?(\d+)")
# Agente: nombre (1-2 palabras capitalizadas en texto original) antes de "Nivel".
# Se aplica sobre el texto ORIGINAL (no normalizado) para preservar mayúsculas.
# Tolera hasta 60 chars de basura OCR entre el nombre y "Nivel" — Tesseract
# suele intercalar garbage entre tokens en frames con animaciones (e.g.
# "Nangong YU �� ! '$ � Nivel 60"). Captura 1-2 palabras Capitalizadas y
# acepta variantes como "Nombre YU" (segunda palabra mayúscula completa).
_RE_AGENTE_NOMBRE = re.compile(
    r"([A-Z][a-z]+(?:\s+(?:[A-Z][a-z]+|[A-Z]{2,}))?)"
    r"(?:[^A-Za-z\n]{0,60}?Nivel\s+\d+|\s+Nivel\s+\d+)"
)
# Variante alternativa: nombre como palabra capitalizada cerca del comienzo,
# útil cuando "Nivel" se destruye en el OCR pero el nombre se preserva.
# Limitada a primeras 200 chars del texto para evitar capturar texto del UI.
_RE_AGENTE_FALLBACK = re.compile(
    r"\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]+)?)\b"
)
# Rol: texto entre "MAX" y "PV" en texto original
_RE_ROL_OCR = re.compile(r"MAX\s+(.+?)\s+[Pp][Vv]\b")


def _normalize_ocr_text(text: str) -> str:
    """
    Normaliza texto OCR para regex robustos contra ruido de Tesseract/Paddle:
      - Lower-case
      - Strip de acentos (á→a, é→e, etc.)
      - Mapeo de caracteres-basura comunes Tesseract (Ã, �) a espacio
    No modifica nombres de agente / facción que se extraen del texto original.
    """
    if not text:
        return ""
    repl = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n",
        "Á": "a", "É": "e", "Í": "i", "Ó": "o", "Ú": "u", "Ñ": "n",
        "ã": "a", "õ": "o", "ç": "c", "ü": "u",
        "Ã": " ", "Â": " ", "®": " ", "©": " ", "�": " ", "—": " ", "–": " ",
    }
    out = text.lower()
    for k, v in repl.items():
        out = out.replace(k, v)
    return out


def _extract_by_regex(text: str) -> dict[str, str | None]:
    """
    Extrae los 11 stats del texto OCR completo usando regex sobre texto
    NORMALIZADO (lower + accents stripped + basura OCR mapeada).
    Retorna dict {stat_key: raw_value_string_or_None}.
    """
    result: dict[str, str | None] = {k: None for k in _STAT_KEYS}
    norm = _normalize_ocr_text(text)

    m = _RE_NIVEL.search(norm)
    if m:
        result["nivel"] = m.group(1)

    m = _RE_PV.search(norm)
    if m:
        result["pv"] = _clean_number(m.group(1))

    for key, regex in [
        ("ataque", _RE_ATAQUE),
        ("defensa", _RE_DEFENSA),
        ("impacto", _RE_IMPACTO),
        ("prob_crit", _RE_PROB_CRIT),
        ("dano_crit", _RE_DANO_CRIT),
        ("tasa_anomalia", _RE_TASA_ANOMALIA),
        ("maestria_anomalia", _RE_MAESTRIA_ANOMALIA),
        ("tasa_perforacion", _RE_TASA_PERFORACION),
        ("recup_energia", _RE_RECUP_ENERGIA),
        ("fuerza_bruta", _RE_FUERZA_BRUTA),
        ("adrenalina", _RE_ADRENALINA),
    ]:
        m = regex.search(norm)
        if m:
            result[key] = next((g for g in m.groups() if g is not None), None)

    return result


def _extract_agent_info(
    full_text: str,
    stats: dict | None = None,
) -> tuple[str | None, str | None, str | None, list[str]]:
    """
    Extrae nombre, rol y elemento del texto OCR (+ stats parseados).

    Estrategia (2026-05-31 R1/R2 + 2026-06-01 Capas 1/2/3 + 2026-06-02 Capa 4):
      0. STATS: si se pasan stats suficientes (pv+atk+crit), identificar al
         agente por su vector contra el roster (`_identify_by_stats`). Es la
         señal MÁS confiable: los stats de pantalla == build de la DB del
         usuario, y resuelve homónimos (N.º 0: Anby) y nombres display largos
         (Lucy="Luciana de Montefio") que el OCR del nombre no capta. Se
         cross-checkea contra el rol/elemento de pantalla si éstos se leyeron.
      1. ROL + ELEMENTO desde PANTALLA (banner MAX..PV) → autoritativo (RNF-02).
      2. NOMBRE: matcher difuso (`_match_agent`) sobre TODO el roster (fallback
         si la identificación por stats no fue concluyente). Normalizado, con
         desambiguación por rol+elemento. Tolera misreads. Si no matchea pero
         el nombre está dual-validado (R2), se usa el OCR (PJ fuera del roster).
      3. La DB queda como RESPALDO de rol/elemento solo si el OCR no los leyó.

    Retorna (nombre_final, rol, elemento, notas_extra).
    """
    notas: list[str] = []

    # --- 1) Rol + elemento desde pantalla (autoritativo) ---
    banner = _banner_rol_elem_region(full_text)
    rol_screen = _canon_rol(banner)
    elem_screen = _canon_elemento(banner)

    name_reg = _name_region(full_text)

    # --- 0) Identificación por STATS (señal primaria si hay datos) ---
    stat_ag = _identify_by_stats(stats)
    if stat_ag is not None:
        # Cross-check: si el banner se leyó y contradice al agente identificado
        # por stats (rol o elemento), descartar la identificación por stats y
        # caer al matcher de nombre (conservador, RNF-02).
        sa_rol = _strip_accents(stat_ag.get("rol") or "").lower()
        sa_elem = _strip_accents(stat_ag.get("elemento") or "").lower()
        if rol_screen and sa_rol and _strip_accents(rol_screen).lower() != sa_rol:
            stat_ag = None
        elif elem_screen and sa_elem and _strip_accents(elem_screen).lower() != sa_elem:
            stat_ag = None

    if stat_ag is not None:
        nombre_db, rol_db, elemento_db = (
            stat_ag["nombre"], stat_ag["rol"], stat_ag["elemento"],
        )
        notas.append(f"identificado_por_stats_{nombre_db}")
    else:
        # --- 2) Nombre: matcher difuso sobre el roster, desambiguado por rol/elem ---
        nombre_db, rol_db, elemento_db = _match_agent(name_reg, rol_screen, elem_screen)

    # R2: candidatos dual-validados (blanco + gris). Sirven para confianza y para
    # mostrar el nombre de PJs fuera del roster (sin match en DB).
    candidates = re.findall(
        r"\b([A-Z][a-z]{2,}(?:\s+(?:[A-Z][a-z]+|[A-Z]{2,}))?)\b",
        name_reg,
    )
    candidates = [c for c in candidates if len(c) >= 3]
    dual = [c for c in candidates if _name_appears_twice(full_text, c)]
    name_validated = bool(dual)

    # Si no hubo match en DB, último recurso: regex legacy nombre-antes-de-Nivel.
    if nombre_db is None and not dual:
        m = _RE_AGENTE_NOMBRE.search(full_text)
        if m:
            cand = m.group(1).strip()
            if len(cand) > 2 and any(c.islower() for c in cand) and _name_appears_twice(full_text, cand):
                dual = [cand]
                name_validated = True

    # --- 3) Resolución autoritativa: PANTALLA gana sobre DB ---
    # (excepto rol/elem que vienen de la identificación por stats, que ya son
    # los canónicos correctos de la DB; el banner solo rellena si stats no IDó).
    rol = rol_screen or rol_db
    elemento = elem_screen or elemento_db
    nombre_final = nombre_db or (dual[0] if dual else None)

    # Notas de diagnóstico
    if rol_screen and rol_db and _norm_name(rol_screen) != _norm_name(rol_db):
        notas.append(f"rol_pantalla={rol_screen}_vs_db={rol_db}")
    if elem_screen and elemento_db and _norm_name(elem_screen) != _norm_name(elemento_db):
        notas.append(f"elem_pantalla={elem_screen}_vs_db={elemento_db}")
    if nombre_db is None and nombre_final is not None:
        notas.append("nombre_fuera_de_roster")
    if name_validated:
        notas.append("nombre_doble_validado")
    if nombre_final and rol:
        notas.append(f"agente_{nombre_final}_rol_{rol}")

    return (nombre_final, rol, elemento, notas)


def _parse_via_full_frame(
    frame: np.ndarray,
    ocr: OcrBackend,
) -> AgentStatsParsed:
    """
    OCR sobre frame completo, extrae stats por regex del texto concatenado.
    Valida rol contra DB para filtrar stats segun tipo de agente.
    """
    notas: list[str] = []

    full_text, ocr_conf = ocr.text(frame)
    if not full_text or ocr_conf == 0.0:
        notas.append("ocr_no_detecto_texto")
        return AgentStatsParsed(confianza_global=0.0, notas=notas)

    extracted = _extract_by_regex(full_text)

    nivel = _parse_int(extracted["nivel"])
    if nivel is None:
        notas.append("nivel_no_detectado")

    pv = _parse_int(extracted["pv"])
    ataque = _parse_int(extracted["ataque"])
    defensa = _parse_int(extracted["defensa"])
    impacto = _parse_int(extracted["impacto"])
    prob_crit = _normalize_percent(_parse_float(extracted["prob_crit"]))
    dano_crit = _normalize_percent(_parse_float(extracted["dano_crit"]))
    tasa_anomalia = _parse_int(extracted["tasa_anomalia"])
    maestria_anomalia = _parse_int(extracted["maestria_anomalia"])

    # Extraer agente: identificación por STATS (Capa 4, primaria) con fallback a
    # nombre/banner. Se hace DESPUÉS de parsear los stats para poder pasarle el
    # vector (pv/atk/crit) — los stats de pantalla == build de la DB del usuario,
    # lo que resuelve homónimos y nombres display largos que el OCR no capta.
    stats_para_id = {
        "pv": pv, "ataque": ataque, "defensa": defensa,
        "prob_crit": prob_crit, "dano_crit": dano_crit,
    }
    nombre_db, rol_db, elemento_db, info_notas = _extract_agent_info(
        full_text, stats_para_id,
    )
    notas.extend(info_notas)

    # Fuerza Bruta vs Tasa de Perforación: son mutuamente excluyentes por rol.
    # "Fuerza Bruta" es un label EXCLUSIVO de Disruptivos, así que su sola
    # presencia en el OCR identifica el caso — NO dependemos de que rol_db ya
    # esté resuelto (Bug C, QA 2026-05-31: el lookup de rol podía no haber
    # corrido en el frame del merge → fuerza_bruta quedaba None aunque el valor
    # estuviera en pantalla). Si aparece Fuerza Bruta, TP no aplica.
    fuerza_bruta = _parse_int(extracted["fuerza_bruta"])
    if fuerza_bruta is not None:
        tasa_perforacion = None
        if extracted["tasa_perforacion"] is not None:
            notas.append("tp_ignorada_disruptivo")
    else:
        tasa_perforacion = _normalize_percent(_parse_float(extracted["tasa_perforacion"]))

    # Recup. Energía vs Acumulación de Adrenalina: mutuamente excluyentes por
    # rol (igual que TP vs FB). "adrenalina" es label EXCLUSIVO de Disruptivos;
    # su presencia identifica el caso sin depender de rol_db. Si hay adrenalina,
    # recuperacion_energia NO aplica (y viceversa). Esto evita meter el valor de
    # adrenalina en el campo de energy regen (Bug D, QA 2026-05-31).
    acumulacion_adrenalina = _parse_int(extracted["adrenalina"])
    if acumulacion_adrenalina is not None:
        recuperacion_energia = None
        if extracted["recup_energia"] is not None:
            notas.append("er_ignorada_disruptivo")
    else:
        recuperacion_energia = _parse_float(extracted["recup_energia"])

    return AgentStatsParsed(
        nivel=nivel, pv=pv, ataque=ataque, defensa=defensa,
        impacto=impacto, prob_crit=prob_crit, dano_crit=dano_crit,
        tasa_anomalia=tasa_anomalia, maestria_anomalia=maestria_anomalia,
        tasa_perforacion=tasa_perforacion,
        recuperacion_energia=recuperacion_energia,
        fuerza_bruta=fuerza_bruta,
        acumulacion_adrenalina=acumulacion_adrenalina,
        confianza_global=round(ocr_conf, 3),
        notas=notas,
        agente_nombre=nombre_db,
        rol=rol_db,
        elemento=elemento_db,
    )


# ---------------------------------------------------------------------------
# Modo 2: OCR per-ROI (Tesseract / backends sin bboxes)
# ---------------------------------------------------------------------------

def _ocr_stat(roi: np.ndarray, ocr: OcrBackend) -> tuple[str, float]:
    if roi is None or roi.size < 100:
        return "", 0.0
    try:
        return ocr.text(roi, psm=7)
    except Exception:
        return "", 0.0


def _parse_via_rois(frame: np.ndarray, ocr: OcrBackend) -> AgentStatsParsed:
    section = "perfil_agente_atributos"
    notas: list[str] = []
    confianzas: list[float] = []

    nombre_raw, c_n = _ocr_stat(crop_named_roi(frame, section, "nivel_nombre"), ocr)
    valor_raw, c_v = _ocr_stat(crop_named_roi(frame, section, "nivel_valor"), ocr)
    confianzas.extend([c_n, c_v])
    nivel_text = _clean_number(f"{nombre_raw} {valor_raw}")
    nivel = _parse_int(nivel_text)
    if nivel is None:
        notas.append("nivel_no_detectado")

    def _parse_stat(key: str):
        n_raw, cn = _ocr_stat(crop_named_roi(frame, section, f"{key}_nombre"), ocr)
        v_raw, cv = _ocr_stat(crop_named_roi(frame, section, f"{key}_valor"), ocr)
        return _clean_number(f"{n_raw} {v_raw}"), cn, cv

    text, c1, c2 = _parse_stat("pv");           confianzas.extend([c1, c2]); pv = _parse_int(text)
    text, c1, c2 = _parse_stat("ataque");        confianzas.extend([c1, c2]); ataque = _parse_int(text)
    text, c1, c2 = _parse_stat("defensa");       confianzas.extend([c1, c2]); defensa = _parse_int(text)
    text, c1, c2 = _parse_stat("impacto");       confianzas.extend([c1, c2]); impacto = _parse_int(text)
    text, c1, c2 = _parse_stat("prob_crit");     confianzas.extend([c1, c2]); prob_crit = _normalize_percent(_parse_float(text))
    text, c1, c2 = _parse_stat("dano_crit");     confianzas.extend([c1, c2]); dano_crit = _normalize_percent(_parse_float(text))
    text, c1, c2 = _parse_stat("tasa_anomalia"); confianzas.extend([c1, c2]); tasa_anomalia = _parse_int(text)
    text, c1, c2 = _parse_stat("maestria_anomalia"); confianzas.extend([c1, c2]); maestria_anomalia = _parse_int(text)
    text, c1, c2 = _parse_stat("tasa_perforacion"); confianzas.extend([c1, c2]); tasa_perforacion = _normalize_percent(_parse_float(text))
    text, c1, c2 = _parse_stat("recup_energia"); confianzas.extend([c1, c2]); recuperacion_energia = _parse_float(text)

    # Fuerza Bruta / Adrenalina no aplican en per-ROI (path Tesseract fallback;
    # son stats role-specific de Disruptivos que el modo full-frame maneja).
    fuerza_bruta = None
    acumulacion_adrenalina = None

    confianza_global = (sum(confianzas) / len(confianzas)) if confianzas else 0.0
    return AgentStatsParsed(
        nivel=nivel, pv=pv, ataque=ataque, defensa=defensa,
        impacto=impacto, prob_crit=prob_crit, dano_crit=dano_crit,
        tasa_anomalia=tasa_anomalia, maestria_anomalia=maestria_anomalia,
        tasa_perforacion=tasa_perforacion,
        recuperacion_energia=recuperacion_energia,
        fuerza_bruta=fuerza_bruta,
        acumulacion_adrenalina=acumulacion_adrenalina,
        confianza_global=round(confianza_global, 3), notas=notas,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_agent_stats(
    frame: np.ndarray,
    ocr: OcrBackend,
) -> AgentStatsParsed:
    """
    Extrae los 11 atributos base desde la pantalla S18.

    Dos modos:
    - PaddleBackend: OCR sobre frame completo, mapeo por bbox + keywords.
    - Otros (Tesseract, mock): OCR per-ROI (22 crops individuales).

    Args:
        frame: screenshot completo (BGR numpy array)
        ocr: backend OCR

    Returns:
        AgentStatsParsed con valores extraidos y confianza global.
    """
    # Ambos backends (Paddle y Tesseract) tienen OCR full-frame robusto.
    # El path full-frame + regex es más resiliente que per-ROI porque no
    # depende de coordenadas exactas y captura el panel completo en una
    # sola llamada OCR.
    #
    # Latencia (2559×1439, Tesseract upscale 3x + Otsu): ~3s — aceptable
    # porque _process_agent_stats corre 1 vez por entrada a S18 (dedup).
    #
    # El path per-ROI (`_parse_via_rois`) queda como fallback explícito
    # si en el futuro queremos OCR sobre crops pequeños para velocidad.
    return _parse_via_full_frame(frame, ocr)
