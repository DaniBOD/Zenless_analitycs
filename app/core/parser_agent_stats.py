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
    """Si el valor es > 1.0 asumimos que viene en % y lo normalizamos a 0-1."""
    if val is not None and val > 1.0:
        return val / 100.0
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
    Prueba multiples variantes: raw, sin espacios, con split camelCase
    (para OCR que pega palabras: "NangongYu" -> "nangong yu").
    Retorna (nombre_canon, rol, elemento) o (None, None, None).
    """
    if not nombre_ocr:
        return (None, None, None)
    try:
        conn = sqlite3.connect(f"file:{_DB_PATH}?mode=ro", uri=True)
        raw = nombre_ocr.strip()
        base = raw.lower()

        candidates = {base, base.replace(" ", "")}

        # Split camelCase: "NangongYu" -> "Nangong Yu" (preserving case first)
        # Luego lowercased: "nangong yu"
        split_camel = re.sub(r"([a-z])([A-Z])", r"\1 \2", raw).lower()
        candidates.add(split_camel)
        # split_camel without spaces too
        candidates.add(split_camel.replace(" ", ""))

        for c in candidates:
            if not c:
                continue
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
# Regex para PaddleOCR full-frame
# ---------------------------------------------------------------------------

_RE_NIVEL = re.compile(r"(?:Nivel|Nv\.?)\s*(\d{1,2})")
_RE_PV = re.compile(r"PV\s+(\d+(?:\s+\d+)?)")
_RE_ATAQUE = re.compile(r"Ataque\s+(\d+)")
_RE_DEFENSA = re.compile(r"Defensa\s+(\d+)")
_RE_IMPACTO = re.compile(r"Impacto\s+(\d+)")
# Probabilidad/Crit rate: "Probabilidad de 19.4 %" or "19.4 %"
_RE_PROB_CRIT = re.compile(r"(?:Probabilidad|Prob\.?)\s*(?:de\s*)?(\d+(?:\.\d+)?)\s*%")
# Dano critico: "Dano Critico 93.2 %" or "Critico 93.2 %"
_RE_DANO_CRIT = re.compile(r"(?:Dano|Danio)\s*Critico\s+(\d+(?:\.\d+)?)\s*%")
_RE_TASA_ANOMALIA = re.compile(r"Tasa\s+de\s+Anomalia\s+(\d+)")
_RE_MAESTRIA_ANOMALIA = re.compile(r"Maestria\s+de\s+Anomalia\s+(\d+)")
# Fuerza Bruta: stat de Anomalia/Disruptivos en reemplazo de Tasa de Perforacion
_RE_FUERZA_BRUTA = re.compile(r"Fuerza\s+Bruta\s+(\d+)")
# Agente: ultimo nombre/palabra antes de "Nivel" (captura multi-word)
_RE_AGENTE_NOMBRE = re.compile(
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+Nivel\s+\d+"
)
# Rol: texto entre "MAX" y "PV"
_RE_ROL_OCR = re.compile(r"MAX\s+(.+?)\s+PV\b")
# PEN rate: SOLO "Tasa de Perforacion" (excluye "Fuerza Bruta" que es de Disruptivos)
_RE_TASA_PERFORACION = re.compile(
    r"Tasa\s+de\s+Perforacion\s*(\d+(?:\.\d+)?)\s*%?"
)
_RE_RECUP_ENERGIA = re.compile(
    r"(?:\b(\d+(?:\.\d+)?)\s*(?:V\s+)?(?:Energia|Adrenalina)"
    r"|Adrenalina\s+(\d+(?:\.\d+)?))"
)


def _extract_by_regex(text: str) -> dict[str, str | None]:
    """
    Extrae los 11 stats del texto OCR completo usando regex.
    Retorna dict {stat_key: raw_value_string_or_None}.
    """
    result: dict[str, str | None] = {k: None for k in _STAT_KEYS}

    m = _RE_NIVEL.search(text)
    if m:
        result["nivel"] = m.group(1)

    m = _RE_PV.search(text)
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
        m = regex.search(text)
        if m:
            # Use the first non-None group (regex with alternatives may have
            # different group indices: group 1 or group 2)
            result[key] = next((g for g in m.groups() if g is not None), None)

    return result


def _extract_agent_info(full_text: str) -> tuple[str | None, str | None, str | None, str | None]:
    """
    Extrae nombre, rol y elemento del texto OCR.
    Retorna (nombre_ocr, nombre_db, rol_db, elemento_db).
    """
    nombre_ocr = None
    m = _RE_AGENTE_NOMBRE.search(full_text)
    if m:
        nombre_ocr = m.group(1).strip()
        # Ignorar capturas demasiado cortas (el OCR suele fragmentar nombres
        # tipo "Yu" del camelCase "NangongYu", o "Tinta" que no es agente)
        if len(nombre_ocr) <= 2 or not any(c.islower() for c in nombre_ocr):
            nombre_ocr = None

    rol_ocr_raw = None
    m = _RE_ROL_OCR.search(full_text)
    if m:
        rol_ocr_raw = m.group(1).strip()

    # Buscar en DB por nombre OCR
    nombre_db, rol_db, elemento_db = _lookup_agent(nombre_ocr or "")

    # Si no hay match en DB, intentar extraer rol del texto OCR
    if rol_db is None and rol_ocr_raw:
        rol_db = _normalizar_rol(rol_ocr_raw)

    # Extraer elemento del texto OCR si no vino de DB
    if elemento_db is None and rol_ocr_raw:
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
    try:
        from app.core.ocr_paddle import PaddleBackend
        is_paddle = isinstance(ocr, PaddleBackend)
    except ImportError:
        is_paddle = False

    if is_paddle:
        return _parse_via_full_frame(frame, ocr)
    else:
        return _parse_via_rois(frame, ocr)
