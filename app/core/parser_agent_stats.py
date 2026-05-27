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
from dataclasses import dataclass, field
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
}
# Mapping OCR noise -> roles canonicales
_ROL_OCR_MAP: dict[str, str] = {
    "auxiliar": "soporte",
    "aturdidor": "aturdimiento",
    "anomalo": "anomalia",
    "disruptivo": "disruptivos",
}

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
    "tasa_perforacion", "recup_energia", "fuerza_bruta",
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
    Normaliza un valor de % a fracción 0-1.

    Si val > 1.0: viene en % (e.g. 19.4 → 0.194).
    Si val > 1.0 tras /100: el OCR perdió un punto decimal
    (e.g. "194" → 1.94 → 0.194). Aplicamos /10 extra.

    Casos cubiertos:
      19.4 → 0.194 ✓        (lectura limpia)
      194  → 0.194 ✓        (OCR perdió "." entre "9" y "4")
      1716 → 0.1716 → 0.01716 / 0.1716 — borde, aceptamos
      100  → 1.0    ✓       (100% real, queda)
      0.5  → 0.5    ✓       (ya en fracción)
    """
    if val is None:
        return None
    if val > 1.0:
        val = val / 100.0
    if val > 1.0:
        val = val / 10.0
    return val


# ---------------------------------------------------------------------------
# Modo 1: PaddleOCR full-frame
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# DB lookup
# ---------------------------------------------------------------------------

_DB_PATH = Path(__file__).resolve().parent.parent.parent / "db" / "danibod_zzz_v2.db"


def _normalizar_rol(ocr_text: str) -> str | None:
    """Normaliza texto OCR a rol canonico de DB."""
    t = ocr_text.lower().strip()
    if t in _ROLES_DB:
        return t
    for alias, canon in _ROL_OCR_MAP.items():
        if alias in t:
            return canon
    return None


def _lookup_agent(nombre_ocr: str) -> tuple[str | None, str | None, str | None]:
    """
    Busca un agente en la DB por nombre aproximado.

    Estrategia: la DB usa "Yuzuha", "Yanagi", "Cissia" — pero el juego
    muestra "Ukinami Yuzuha", "Tsukishiro Yanagi". El OCR captura la
    versión del juego (2 palabras). Probamos:
      1. Nombre completo (raw, sin espacios, camelCase).
      2. Cada PALABRA individual del nombre (si tiene 2+).
      3. Cada palabra split por camelCase.

    El primer LIKE que matchea gana.
    Retorna (nombre_canon, rol, elemento) o (None, None, None).
    """
    if not nombre_ocr:
        return (None, None, None)
    try:
        conn = sqlite3.connect(f"file:{_DB_PATH}?mode=ro", uri=True)
        raw = nombre_ocr.strip()
        base = raw.lower()

        # Set ordenado de candidatos: primero los más específicos, luego
        # palabras individuales. Usamos list para preservar orden.
        candidates: list[str] = []

        def _add(c: str) -> None:
            c = c.strip()
            if c and len(c) >= 3 and c not in candidates:
                candidates.append(c)

        _add(base)
        _add(base.replace(" ", ""))

        # Split camelCase: "NangongYu" -> "Nangong Yu"
        split_camel = re.sub(r"([a-z])([A-Z])", r"\1 \2", raw).lower()
        _add(split_camel)
        _add(split_camel.replace(" ", ""))

        # Cada palabra individual del nombre completo
        for word in re.split(r"\s+", base):
            _add(word)
        # Cada palabra del camelCase split
        for word in re.split(r"\s+", split_camel):
            _add(word)

        for c in candidates:
            cursor = conn.execute(
                "SELECT nombre, rol, elemento FROM agents WHERE LOWER(nombre) LIKE ?",
                (f"%{c}%",),
            )
            row = cursor.fetchone()
            if row:
                conn.close()
                return (row[0], row[1], row[2])
        conn.close()
    except Exception:
        pass
    return (None, None, None)


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
# Recup Energía: la palabra "Recuperación de Energía" se renderiza en 2
# líneas en el juego y Tesseract a menudo destruye una o ambas palabras.
# Aceptamos múltiples patrones:
#   (a) "recup..." cualquier sufijo + número
#   (b) "...energ..." cualquier prefijo + número
#   (c) "adrenalina <número>" (variante histórica de algunas builds)
_RE_RECUP_ENERGIA = re.compile(
    r"(?:recup\w*|energ\w*|adrenal\w*)[^\d\n]{0,30}?(\d+(?:\.\d+)?)"
)
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
    ]:
        m = regex.search(norm)
        if m:
            result[key] = next((g for g in m.groups() if g is not None), None)

    return result


def _extract_agent_info(full_text: str) -> tuple[str | None, str | None, str | None, str | None]:
    """
    Extrae nombre, rol y elemento del texto OCR.

    Estrategia robusta:
      1. Busca TODOS los nombres capitalizados (1-2 palabras) en el texto.
      2. Cada candidato se valida contra la DB de agentes (LIKE).
      3. El primero que matchea gana. Esto descarta automáticamente nombres
         de facciones, bangboos (Tinta), texto random del UI, etc.

    Retorna (nombre_ocr, nombre_db, rol_db, elemento_db).
    """
    nombre_ocr = None
    nombre_db = None
    rol_db = None
    elemento_db = None

    # Candidatos: nombres capitalizados 1-2 palabras en las primeras 500 chars
    # (donde está el banner del agente). Soporta "Nombre Apellido", "Nombre YU"
    # (segundo palabra en mayúsculas) y "Nombre".
    candidates = re.findall(
        r"\b([A-Z][a-z]{2,}(?:\s+(?:[A-Z][a-z]+|[A-Z]{2,}))?)\b",
        full_text[:500],
    )

    # Probar cada candidato contra la DB hasta encontrar match
    for candidate in candidates:
        if len(candidate) < 3:
            continue
        n_db, r_db, e_db = _lookup_agent(candidate)
        if n_db:
            nombre_ocr = candidate
            nombre_db = n_db
            rol_db = r_db
            elemento_db = e_db
            break

    # Fallback al regex viejo si no hubo match en DB
    if nombre_db is None:
        m = _RE_AGENTE_NOMBRE.search(full_text)
        if m:
            candidate = m.group(1).strip()
            if len(candidate) > 2 and any(c.islower() for c in candidate):
                nombre_ocr = candidate
                nombre_db, rol_db, elemento_db = _lookup_agent(candidate)

    # Rol/Elemento desde regex MAX..PV (si no vinieron de DB)
    if rol_db is None or elemento_db is None:
        m = _RE_ROL_OCR.search(full_text)
        if m:
            rol_ocr_raw = m.group(1).strip()
            if rol_db is None:
                rol_db = _normalizar_rol(rol_ocr_raw)
            if elemento_db is None:
                t = rol_ocr_raw.lower()
                for elem in _ELEMENTOS_DB:
                    if elem in t:
                        elemento_db = elem.capitalize()
                        break

    return (nombre_ocr, nombre_db, rol_db, elemento_db)


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

    # Extraer agente + rol
    nombre_ocr, nombre_db, rol_db, elemento_db = _extract_agent_info(full_text)

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

    # Fuerza Bruta: stat exclusivo de Disruptivos en el slot bottom-left.
    # Reemplaza a Tasa de Perforacion solo para ese rol.
    tasa_perforacion = None
    fuerza_bruta = None
    if rol_db == "disruptivos":
        fuerza_bruta = _parse_int(extracted["fuerza_bruta"])
        if extracted["tasa_perforacion"] is not None:
            notas.append(f"tp_ignorada_rol_{rol_db}")
    else:
        tasa_perforacion = _normalize_percent(_parse_float(extracted["tasa_perforacion"]))
    recuperacion_energia = _parse_float(extracted["recup_energia"])

    if nombre_db is not None and rol_db is not None:
        notas.append(f"agente_{nombre_db}_rol_{rol_db}")

    return AgentStatsParsed(
        nivel=nivel, pv=pv, ataque=ataque, defensa=defensa,
        impacto=impacto, prob_crit=prob_crit, dano_crit=dano_crit,
        tasa_anomalia=tasa_anomalia, maestria_anomalia=maestria_anomalia,
        tasa_perforacion=tasa_perforacion,
        recuperacion_energia=recuperacion_energia,
        fuerza_bruta=fuerza_bruta,
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

    # Fuerza Bruta no aplica en per-ROI (Tesseract no puede extraerlo de crops)
    fuerza_bruta = None

    confianza_global = (sum(confianzas) / len(confianzas)) if confianzas else 0.0
    return AgentStatsParsed(
        nivel=nivel, pv=pv, ataque=ataque, defensa=defensa,
        impacto=impacto, prob_crit=prob_crit, dano_crit=dano_crit,
        tasa_anomalia=tasa_anomalia, maestria_anomalia=maestria_anomalia,
        tasa_perforacion=tasa_perforacion,
        recuperacion_energia=recuperacion_energia,
        fuerza_bruta=fuerza_bruta,
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
