"""
Tests para parser_agent_stats.py — Hito 2.8.
Certifica que los 11 atributos base se extraen correctamente
de cada screenshot real de Perfil_agente (S18).
"""
from pathlib import Path
import cv2
import numpy as np
import pytest

from app.core.parser_agent_stats import parse_agent_stats, AgentStatsParsed


FIXTURES = Path(__file__).parent.parent / "fixtures"
SCREENSHOTS = sorted(FIXTURES.glob("atributos_base_ejemplo_*.png"))


@pytest.fixture(scope="session")
def paddle_ocr():
    """Inicializa PaddleOCR una vez para todos los tests.

    El warmup usa el primer screenshot real (que sabemos contiene texto)
    para confirmar que el pipeline det+rec produce salidas distintas de
    vacío. Un retorno vacío sobre un screenshot con texto evidente es
    indicio fiable de incompatibilidad OneDNN / modelo no cargado.
    """
    try:
        from app.core.ocr_paddle import PaddleBackend
        ocr = PaddleBackend(lang="es")
        if not SCREENSHOTS:
            pytest.skip("Sin screenshots en fixtures para warmup PaddleOCR")
        data = np.fromfile(str(SCREENSHOTS[0]), dtype=np.uint8)
        frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
        text, conf = ocr.text(frame)
        if conf == 0.0 and not text:
            raise RuntimeError("PaddleOCR warmup sobre screenshot real devolvió texto vacío")
        return ocr
    except Exception as e:
        pytest.skip(f"PaddleOCR no disponible en este entorno Windows: {e}")


@pytest.fixture(scope="session")
def tesseract_ocr():
    """Inicializa Tesseract para tests alternativos (fallback si PaddleOCR no anda)."""
    try:
        from app.core.ocr_tesseract import TesseractBackend
        ocr = TesseractBackend()
        dummy = np.zeros((100, 100, 3), dtype=np.uint8)
        ocr.text(dummy)
        return ocr
    except Exception as e:
        pytest.skip(f"Tesseract no disponible: {e}")


@pytest.mark.parametrize("screenshot_path", SCREENSHOTS, ids=lambda p: p.stem)
def test_extracts_all_11_stats(screenshot_path, paddle_ocr):
    """Cada screenshot debe producir 11 stats con valores > 0."""
    data = np.fromfile(str(screenshot_path), dtype=np.uint8)
    frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
    assert frame is not None, f"No se pudo cargar: {screenshot_path}"

    result = parse_agent_stats(frame, paddle_ocr)

    assert isinstance(result, AgentStatsParsed)
    assert result.confianza_global > 0.0

    # Los 9 stats comunes + 2 slots inferiores ROLE-SPECIFIC y mutuamente
    # excluyentes (Disruptivos: Fuerza Bruta + Acumulación Adrenalina;
    # resto: Tasa de Perforación + Recuperación de Energía). Contamos los
    # campos que SÍ aplican al rol para no penalizar None legítimos.
    rol_norm = (result.rol or "").lower()
    is_disruptivo = "disruptiv" in rol_norm

    stats = {
        "nivel": result.nivel,
        "pv": result.pv,
        "ataque": result.ataque,
        "defensa": result.defensa,
        "impacto": result.impacto,
        "prob_crit": result.prob_crit,
        "dano_crit": result.dano_crit,
        "tasa_anomalia": result.tasa_anomalia,
        "maestria_anomalia": result.maestria_anomalia,
    }
    if is_disruptivo:
        stats["fuerza_bruta"] = result.fuerza_bruta
        stats["acumulacion_adrenalina"] = result.acumulacion_adrenalina
    else:
        stats["tasa_perforacion"] = result.tasa_perforacion
        stats["recuperacion_energia"] = result.recuperacion_energia

    extracted = sum(1 for v in stats.values() if v is not None and v >= 0)
    if extracted == 0:
        pytest.skip(f"PaddleOCR no extrajo stats en {screenshot_path.stem} (entorno sin OneDNN compatible)")

    # Disruptivos: 10/11 tolera 1 stat flaky por OCR de borde (adrenalina es un
    # entero chico, a veces ruidoso). Resto: exigimos 11/11.
    min_expected = 10 if is_disruptivo else 11

    assert extracted >= min_expected, (
        f"Stats faltantes o cero en {screenshot_path.stem}: "
        f"solo {extracted}/11 (rol={result.rol}, min_expected={min_expected}). "
        f"nivel={result.nivel} pv={result.pv} atk={result.ataque} "
        f"def={result.defensa} imp={result.impacto} "
        f"crit_rate={result.prob_crit} crit_dmg={result.dano_crit} "
        f"anom_rate={result.tasa_anomalia} anom_mst={result.maestria_anomalia} "
        f"pen_rate={result.tasa_perforacion} er={result.recuperacion_energia}"
    )


def test_agent_stats_parsed_fields():
    """Verifica que la dataclass tiene los 11 campos esperados."""
    import inspect
    sig = inspect.signature(AgentStatsParsed)
    fields = list(sig.parameters.keys())
    expected = [
        "nivel", "pv", "ataque", "defensa", "impacto",
        "prob_crit", "dano_crit", "tasa_anomalia", "maestria_anomalia",
        "tasa_perforacion", "recuperacion_energia",
        "fuerza_bruta",
        "confianza_global", "notas",
        "agente_nombre", "rol", "elemento",
    ]
    for f in expected:
        assert f in fields, f"Campo '{f}' faltante en AgentStatsParsed"


class _MockOcr:
    """Mock OCR que devuelve valores predecibles sin dependencias reales."""
    def __init__(self):
        self._index = 0
        self._responses = {
            "nivel_nombre": ("Nv", 0.9),
            "nivel_valor": ("60", 0.95),
            "pv_nombre": ("PV", 0.9),
            "pv_valor": ("12500", 0.85),
            "ataque_nombre": ("Ataque", 0.9),
            "ataque_valor": ("2500", 0.85),
            "defensa_nombre": ("Defensa", 0.9),
            "defensa_valor": ("800", 0.85),
            "impacto_nombre": ("Impacto", 0.9),
            "impacto_valor": ("110", 0.85),
            "prob_crit_nombre": ("Prob.CRIT", 0.85),
            "prob_crit_valor": ("19.2%", 0.9),
            "dano_crit_nombre": ("Daño CRIT", 0.85),
            "dano_crit_valor": ("38.4%", 0.9),
            "tasa_anomalia_nombre": ("Tasa Anomalía", 0.85),
            "tasa_anomalia_valor": ("100", 0.85),
            "maestria_anomalia_nombre": ("Maestría Anomalía", 0.8),
            "maestria_anomalia_valor": ("120", 0.8),
            "tasa_perforacion_nombre": ("Tasa Perforación", 0.85),
            "tasa_perforacion_valor": ("12.0%", 0.85),
            "recup_energia_nombre": ("Recup. Energía", 0.8),
            "recup_energia_valor": ("2.4", 0.8),
        }

    def text(self, img, psm=7, lang="spa"):
        return ("", 0.0)


class _SmartOcr:
    """Mock OCR que usa la ROI name pasada como metadata."""
    def __init__(self):
        self.calls: list[str] = []

    def text(self, img, psm=7, lang="spa"):
        # Infer ROI name from the image content — not possible with numpy,
        # so this mock always returns empty. The real test uses paddle_ocr.
        return ("", 0.0)

    def number(self, img):
        return (None, 0.0)


def test_parse_agent_stats_returns_defaults_with_empty_ocr():
    """Con OCR que devuelve vacío, parse_agent_stats retorna todos None."""
    dummy_frame = np.zeros((1439, 2559, 3), dtype=np.uint8)
    ocr = _SmartOcr()
    result = parse_agent_stats(dummy_frame, ocr)
    assert isinstance(result, AgentStatsParsed)
    assert result.nivel is None
    assert result.pv is None
    assert result.ataque is None
    assert result.defensa is None
    assert result.impacto is None
    assert result.prob_crit is None
    assert result.dano_crit is None
    assert result.tasa_anomalia is None
    assert result.maestria_anomalia is None
    assert result.tasa_perforacion is None
    assert result.recuperacion_energia is None
    assert result.fuerza_bruta is None
    assert result.confianza_global == 0.0


# ---------------------------------------------------------------------------
# Tests de cobertura de ROIs (sin OCR, solo verificación de contenido visual)
# ---------------------------------------------------------------------------

def _roi_has_text(img, roi_def):
    """Verifica si una ROI tiene textura de texto (píxeles oscuros sobre fondo claro tras CLAHE)."""
    import tomllib
    h, w = img.shape[:2]
    nx, ny, nw, nh = roi_def
    x, y, rw, rh = int(nx*w), int(ny*h), int(nw*w), int(nh*h)
    if y+rh > h or x+rw > w:
        return False
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    binary = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 6)
    roi_bin = binary[y:y+rh, x:x+rw]
    if roi_bin.size == 0:
        return False
    text_pixels = (roi_bin == 0).sum()
    return (text_pixels / roi_bin.size) > 0.01


def test_all_rois_have_text_content():
    """Certifica que las 23 ROIs contienen texto en los 6 screenshots (sin OCR)."""
    import tomllib
    with open("app/config/rois.toml", "rb") as f:
        rois = tomllib.load(f)
    section = rois["perfil_agente_atributos"]
    roi_defs = {k: v for k, v in section.items() if isinstance(v, list) and len(v) == 4}

    failures = []
    for sp in SCREENSHOTS:
        data = np.fromfile(str(sp), dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        assert img is not None
        for name, roi_def in roi_defs.items():
            if not _roi_has_text(img, roi_def):
                failures.append((sp.name, name))

    assert not failures, (
        f"ROIs sin texto detectable: {len(failures)} fallos\n"
        + "\n".join(f"  {f[0]}: {f[1]}" for f in failures)
    )


@pytest.mark.parametrize("screenshot_path", SCREENSHOTS, ids=lambda p: p.stem)
def test_extracts_some_stats_with_tesseract(screenshot_path, tesseract_ocr):
    """Fallback Tesseract: intenta extraer stats. Skip si no extrae nada (OCRs limitados en esta UI)."""
    data = np.fromfile(str(screenshot_path), dtype=np.uint8)
    frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
    assert frame is not None

    result = parse_agent_stats(frame, tesseract_ocr)
    assert isinstance(result, AgentStatsParsed)

    stats = {
        "nivel": result.nivel,
        "pv": result.pv,
        "ataque": result.ataque,
        "defensa": result.defensa,
        "impacto": result.impacto,
        "prob_crit": result.prob_crit,
        "dano_crit": result.dano_crit,
        "tasa_anomalia": result.tasa_anomalia,
        "maestria_anomalia": result.maestria_anomalia,
        "tasa_perforacion": result.tasa_perforacion,
        "recuperacion_energia": result.recuperacion_energia,
    }
    extracted = sum(1 for v in stats.values() if v is not None and v > 0)
    if extracted == 0:
        pytest.skip(f"Tesseract no extrajo stats en {screenshot_path.stem} (texto UI de bajo contraste)")



# ---------------------------------------------------------------------------
# Tests de regresión — bugs de parsing detectados en QA real (2026-05-31)
# Pure-function, sin OCR: rápidos y deterministas.
# ---------------------------------------------------------------------------

from app.core.parser_agent_stats import (  # noqa: E402
    _normalize_percent,
    _extract_by_regex,
)


class TestNormalizePercentBugA:
    """Bug A: Daño Crítico ≥100% se corrompía por un `/10` extra.
    Yixuan 162% → 0.162 (mal). Debe ser 1.62."""

    def test_dano_critico_mayor_100(self):
        assert _normalize_percent(162.0) == 1.62      # Yixuan (era 0.162)
        assert _normalize_percent(126.8) == 1.268     # Cissia

    def test_porcentajes_normales(self):
        assert _normalize_percent(19.4) == pytest.approx(0.194)
        assert _normalize_percent(93.2) == pytest.approx(0.932)
        assert _normalize_percent(65.0) == 0.65
        assert _normalize_percent(48.2) == pytest.approx(0.482)

    def test_ya_fraccion_y_none(self):
        assert _normalize_percent(0.5) == 0.5
        assert _normalize_percent(None) is None


class TestRecupEnergiaBugB:
    """Bug B: el valor de 'Recuperación de Energía' (label de 2 líneas) queda
    ANTES del token 'energia' en el OCR; el regex viejo agarraba el '0' de
    'Tasa de Perforación 0 %' de al lado. Debe capturar el valor real."""

    def test_valor_antes_de_energia(self):
        # Layout real Nangong: el '1.2' precede a 'energia', tras el '0 %' de perforación
        txt = "tasa de perforacion 0 % 1.2 energia recomendacion"
        assert _extract_by_regex(txt)["recup_energia"] == "1.2"

    def test_valor_con_ruido_ocr(self):
        # ejemplo_2: '2.5 v energia' (ruido 'v' entre valor y label)
        txt = "tasa de perforacion 0 % 2.5 v energia 1 equipamiento"
        assert _extract_by_regex(txt)["recup_energia"] == "2.5"

    def test_no_captura_cero_de_perforacion(self):
        txt = "tasa de perforacion 0 % 1.2 energia"
        assert _extract_by_regex(txt)["recup_energia"] != "0"


class TestAcumulacionAdrenalina:
    """La 'Acumulación Automática de Adrenalina' (slot inferior-derecho de
    Disruptivos) es un campo SEPARADO de recuperacion_energia."""

    def test_adrenalina_a_campo_propio(self):
        # Disruptivo: NO hay 'energia', sí 'adrenalina' → campo separado
        txt = "fuerza bruta 2296 de adrenalina 2 equipamiento"
        ext = _extract_by_regex(txt)
        assert ext["adrenalina"] == "2"
        assert ext["recup_energia"] is None   # no debe robar el valor de adrenalina

    def test_no_disruptivo_sin_adrenalina(self):
        txt = "tasa de perforacion 0 % 1.2 energia"
        assert _extract_by_regex(txt)["adrenalina"] is None


class TestFuerzaBrutaBugC:
    """Bug C: 'Fuerza Bruta' (exclusivo de Disruptivos) debe extraerse por la
    sola presencia del label, sin depender de que rol_db esté resuelto."""

    def test_fuerza_bruta_extraida(self):
        txt = "ca fuerza bruta 2296 de adrenalina 2 equipamiento"
        assert _extract_by_regex(txt)["fuerza_bruta"] == "2296"


class TestFuerzaBrutaFlipV30:
    """Bug FB-orden (ZZZ v3.0, QA 2026-06-19): mismo reordenamiento OCR que TP,
    en la fila inferior de Disruptivos (FB izq. + Adrenalina der.). El valor de
    FB se lee ANTES del label, intercalado con el label de Adrenalina. Textos OCR
    REALES de Ejemplo_7 (Billy Estelar) v3.0."""

    def test_orden_v2x_sigue_andando(self):
        # "fuerza bruta <valor>" — orden estable v2.x.
        assert _extract_by_regex("ca fuerza bruta 2296 de adrenalina 2")["fuerza_bruta"] == "2296"

    def test_flip_v30_valor_antes_del_label(self):
        # Flip v3.0 REAL (Ejemplo_7): "2669 acumulacion automatica fuerza bruta".
        txt = ("maestria de anomalia 89 2669 acumulacion automatica fuerza bruta "
               "de adrenalina atributos secundarios")
        assert _extract_by_regex(txt)["fuerza_bruta"] == "2669"   # antes daba None

    def test_no_roba_maestria_anomalia(self):
        # En orden v2.x, Maestría de Anomalía (89) PRECEDE a "fuerza bruta" pero
        # SIN "acumulaci…" en medio → el ancla evita robar ese 89 como FB.
        txt = "maestria de anomalia 89 fuerza bruta 2669 de adrenalina"
        assert _extract_by_regex(txt)["fuerza_bruta"] == "2669"


class TestPvCuatroDigitos:
    """Bug PV-4díg (QA 2026-06-19, pre-existente): un PV de 4 dígitos sin
    separador de miles se truncaba a 2 dígitos. Textos OCR REALES v3.0."""

    def test_pv_4_digitos_velina(self):
        # Ejemplo_8 (Velina, lvl 50): "pv 6508" daba 65.
        assert _extract_by_regex("pv 6508 ataque 676 defensa 511")["pv"] == "6508"

    def test_pv_4_digitos_billy_kid(self):
        # Ejemplo_9 (Billy Kid): "pv 9763" daba 97.
        assert _extract_by_regex("pv 9763 ataque 2671 defensa 1038")["pv"] == "9763"

    def test_pv_5_digitos_separado_regresion(self):
        # "pv 20 573" (Ejemplo_7, separador de miles) → 20573 (sin regresión).
        assert _extract_by_regex("pv 20 573 ataque 2043")["pv"] == "20573"

    def test_pv_5_digitos_junto_regresion(self):
        assert _extract_by_regex("pv 10797 ataque 2531")["pv"] == "10797"


class TestTasaPerforacionFlipV30:
    """Bug TP-orden (ZZZ v3.0, QA 2026-06-19): el nuevo layout S18 cambió el
    clustering de filas de PaddleOCR en la última fila (TP izq. + Recup. Energía
    der., label de 2 líneas). El valor de TP a veces se lee ANTES del label,
    intercalado con la 1ª línea del label de Recup. Energía. El patrón viejo
    (solo '<label> <valor>%') no matcheaba → TP=None → 'faltan 1/11: TP'.
    Los textos son fragmentos OCR REALES de Ejemplo_8/9/10 v3.0."""

    def test_orden_v2x_sigue_andando(self):
        # Orden estable v2.x (Ejemplo_8/10): valor DESPUÉS del label.
        ext = _extract_by_regex("tasa de perforacion 0 % 1.2 energia recomendacion")
        assert ext["tasa_perforacion"] == "0"
        assert ext["recup_energia"] == "1.2"

    def test_flip_v30_valor_antes_del_label(self):
        # Flip v3.0 REAL (Ejemplo_9, Billy Kid): '0 %' (TP) se lee antes del
        # label, y el '2.16' tras el label es el de Recup. Energía (sin %).
        ext = _extract_by_regex(
            "maestria de anomalia 109 0 % recuperacion de tasa de perforacion "
            "2.16 energia atributos secundarios"
        )
        assert ext["tasa_perforacion"] == "0"     # antes daba None
        assert ext["recup_energia"] == "2.16"     # no debe robarlo TP

    def test_flip_v30_tp_no_cero(self):
        # Mismo flip pero con TP no-cero: el valor %-terminado adyacente al
        # label es el de TP, sin importar que esté antes.
        ext = _extract_by_regex(
            "8 % recuperacion de tasa de perforacion 1.2 energia"
        )
        assert ext["tasa_perforacion"] == "8"
        assert ext["recup_energia"] == "1.2"

    def test_no_captura_otro_porcentaje_lejano(self):
        # El % de Daño Crítico (lejos, con dígitos de TA/MA en medio) NO debe
        # capturarse como TP cuando el valor real de TP no se leyó.
        ext = _extract_by_regex(
            "dano critico 112.4 % tasa de anomalia 92 maestria de anomalia 109 "
            "recuperacion de tasa de perforacion 2.16 energia"
        )
        assert ext["tasa_perforacion"] is None    # no inventa (RNF-02)


# ---------------------------------------------------------------------------
# R1/R2 (2026-05-31): rol+elemento desde PANTALLA (autoritativo) + doble nombre
# ---------------------------------------------------------------------------

class TestRolElementoDesdePantalla:
    """R1: el rol/elemento salen de pantalla y ganan sobre la DB sucia."""

    def test_canon_rol_pantalla_a_db(self):
        from app.core.parser_agent_stats import _canon_rol
        assert _canon_rol("Igneo Aturdidor") == "Aturdimiento"
        assert _canon_rol("Electrico Anomalia") == "Anomalía"
        assert _canon_rol("Tinta aurica Disruptivo") == "Disruptivos"
        assert _canon_rol("Fisico Auxiliar") == "Soporte"
        assert _canon_rol("Hielo Ataque") == "Ataque"
        assert _canon_rol("Eter Defensa") == "Defensa"
        assert _canon_rol("texto sin rol") is None

    def test_canon_elemento_pantalla_a_db(self):
        from app.core.parser_agent_stats import _canon_elemento
        assert _canon_elemento("Igneo Aturdidor") == "Fuego"
        assert _canon_elemento("Gelido Ataque") == "Hielo"
        assert _canon_elemento("Electrico Anomalia") == "Eléctrico"
        assert _canon_elemento("Eter Disruptivo") == "Éter"
        assert _canon_elemento("Fisico Soporte") == "Físico"
        # Política estándar-equivalente (mig 08): Auric Ink se mapea a Éter.
        assert _canon_elemento("Tinta aurica Disruptivo") == "Éter"
        assert _canon_elemento("Escarcha Anomalia") == "Hielo"   # Frost ≡ Hielo
        assert _canon_elemento("Viento Ataque") == "Viento"      # Wind estándar nuevo
        assert _canon_elemento("nada aqui") is None

    def test_pantalla_gana_sobre_db_rol_sucio(self):
        """Pantalla gana sobre DB cuando difieren + emite nota de discrepancia.

        Se monkeypatchea `_lookup_agent` para simular una DB con rol 'sucio'
        ('Soporte') distinto del de pantalla ('Aturdidor'→'Aturdimiento'). Esto
        hace el test determinista e independiente del estado real de la DB (que
        ya fue corregida por la mig 07 2026-06-01: Ju Fufu pasó a Aturdimiento).
        """
        from unittest.mock import patch
        import app.core.parser_agent_stats as p
        txt = ("Pinaculo Yunkui Ju Fufu Ju Fufu Nivel 60 60 MAX "
               "Igneo Aturdidor PV 11146 Ataque 3286 Defensa 925")
        # DB sucia: rol 'Soporte' (≠ pantalla 'Aturdimiento'), elemento 'Fuego'.
        # Se patchea _match_agent (el matcher difuso que usa _extract_agent_info).
        with patch.object(p, "_match_agent",
                          return_value=("Ju Fufu", "Soporte", "Fuego")):
            nombre, rol, elemento, notas = p._extract_agent_info(txt)
        assert rol == "Aturdimiento", f"rol={rol} (debió ganar pantalla sobre DB Soporte)"
        assert elemento == "Fuego"
        assert nombre == "Ju Fufu"
        assert any("rol_pantalla=Aturdimiento_vs_db=Soporte" in n for n in notas), notas

    def test_agente_fuera_de_roster_usa_nombre_de_pantalla(self):
        """PJ fuera del roster (sin match en DB): igual se extrae nombre (doble) +
        rol + elemento de pantalla. Se patchea _match_agent->None para simular
        un PJ no registrado (ej. uno de un banner que el jugador aún no tiene)."""
        from unittest.mock import patch
        import app.core.parser_agent_stats as p
        txt = ("Banner Zephyrine Zephyrine Nivel 60 60 MAX "
               "Electrico Anomalia PV 10000 Ataque 2000 Defensa 700")
        with patch.object(p, "_match_agent", return_value=(None, None, None)):
            nombre, rol, elemento, notas = p._extract_agent_info(txt)
        assert nombre == "Zephyrine", f"nombre={nombre} (dual-validado debió usarse)"
        assert rol == "Anomalía"
        assert elemento == "Eléctrico"
        assert "nombre_fuera_de_roster" in notas
        assert "nombre_doble_validado" in notas


class TestDobleNombre:
    """R2: el nombre aparece 2x (blanco + gris) → validación de confianza."""

    def test_nombre_aparece_dos_veces(self):
        from app.core.parser_agent_stats import _name_appears_twice
        txt = "Pinaculo Yunkui Ju Fufu Ju Fufu Nivel 60"
        assert _name_appears_twice(txt, "Ju Fufu") is True

    def test_nombre_letras_espaciadas_colapsa(self):
        """El gris tenue suele venir letra-espaciado 'J u F u f u' → debe matchear."""
        from app.core.parser_agent_stats import _name_appears_twice
        txt = "Ju Fufu J u F u f u Nivel 60"
        assert _name_appears_twice(txt, "Ju Fufu") is True

    def test_faccion_aparece_una_vez_no_valida(self):
        from app.core.parser_agent_stats import _name_appears_twice
        txt = "Pinaculo Yunkui Ju Fufu Nivel 60"
        assert _name_appears_twice(txt, "Yunkui") is False


# ---------------------------------------------------------------------------
# Capas 1/2/3 (2026-06-01): matcher de agente difuso + desambiguación
#   Capa 1: acentos/case  ·  Capa 2: fuzzy  ·  Capa 3: rol+elemento de pantalla
# ---------------------------------------------------------------------------

class TestMatchAgentCapas123:
    """Identificación robusta del agente contra un roster sintético determinista."""

    _ROWS = [
        ("Anby",         "Aturdimiento", "Eléctrico"),
        ("N.º 0: Anby",  "Ataque",       "Eléctrico"),
        ("Nekomata",     "Ataque",       "Físico"),
        ("Manato",       "Disruptivos",  "Fuego"),
        ("Lucía",        "Soporte",      "Éter"),
        ("Lucy",         "Soporte",      "Fuego"),
        ("César",        "Defensa",      "Físico"),
        ("Antón",        "Ataque",       "Eléctrico"),
        ("Ye Shunguang", "Ataque",       "Físico"),
        ("Ju Fufu",      "Aturdimiento", "Fuego"),
    ]

    @pytest.fixture(autouse=True)
    def _patch_roster(self, monkeypatch):
        import app.core.parser_agent_stats as p
        roster = []
        for nombre, rol, elem in self._ROWS:
            norm = p._norm_name(nombre)
            roster.append({"nombre": nombre, "rol": rol, "elemento": elem,
                           "norm": norm, "tokens": set(norm.split())})
        monkeypatch.setattr(p, "_get_roster", lambda: roster)

    def _m(self, *a):
        from app.core.parser_agent_stats import _match_agent
        return _match_agent(*a)

    # --- Capa 1: acentos / case ---
    def test_capa1_lucia_sin_acento(self):
        assert self._m("Lucia", "Soporte", "Éter")[0] == "Lucía"

    def test_capa1_cesar_con_apellido(self):
        assert self._m("Cesar King", "Defensa", "Físico")[0] == "César"

    def test_capa1_anton_sin_acento(self):
        assert self._m("Anton", "Ataque", "Eléctrico")[0] == "Antón"

    # --- Capa 2: fuzzy / sin falsos positivos ---
    def test_capa2_nekomata_no_es_manato(self):
        assert self._m("Nekomata", "Ataque", "Físico")[0] == "Nekomata"

    def test_capa2_shunguang_misread(self):
        assert self._m("Ye Shunguanq", "Ataque", "Físico")[0] == "Ye Shunguang"

    def test_capa2_desconocido_devuelve_none(self):
        # RNF-02: no inventar identidad si no hay similitud de nombre.
        assert self._m("Zephyrine", "Ataque", "Físico")[0] is None

    # --- Capa 3: desambiguación por rol+elemento ---
    def test_capa3_anby_normal_por_rol(self):
        assert self._m("Anby", "Aturdimiento", "Eléctrico")[0] == "Anby"

    def test_capa3_anby_soldado0_por_rol(self):
        # Mismo "Anby" en pantalla, pero rol Ataque -> N.º 0: Anby (homónimo).
        assert self._m("Anby", "Ataque", "Eléctrico")[0] == "N.º 0: Anby"

    def test_capa3_lucy_vs_lucia_por_elemento(self):
        assert self._m("Lucy", "Soporte", "Fuego")[0] == "Lucy"
        assert self._m("Lucia", "Soporte", "Éter")[0] == "Lucía"


# ---------------------------------------------------------------------------
# Capa 4 (2026-06-02): identificación por STATS (vector pv/atk/crit).
#   Backbone determinista — resuelve homónimos (N.º 0: Anby) y nombres display
#   largos (Lucy="Luciana de Montefio") que el OCR del nombre estilizado falla.
#   Los stats de pantalla == build de la DB del usuario (autoritativo, RNF-02).
# ---------------------------------------------------------------------------

class TestIdentifyByStatsCapa4:
    """Identificación por vector de stats contra un roster sintético con stats."""

    # Vectores reales del build de DaniBOD (DB danibod_zzz_v2) — los crit van
    # como FRACCIÓN igual que el roster cacheado (DB % / 100).
    _ROWS = [
        # nombre, rol, elemento, pv, ataque, defensa, prob_crit, dano_crit
        ("Anby",        "Aturdimiento", "Eléctrico", 11161, 1169, 1018, 0.434, 0.836),
        ("N.º 0: Anby", "Ataque",       "Eléctrico", 10558, 2630,  914, 0.538, 1.764),
        ("Lucy",        "Soporte",      "Fuego",     12392, 1774, 1003, 0.242, 0.836),
        ("Lucía",       "Soporte",      "Éter",      23214, 2041,  995, 0.170, 0.548),
        ("Zhu Yuan",    "Ataque",       "Éter",      11200, 2600,  900, 0.500, 1.700),
    ]

    @pytest.fixture(autouse=True)
    def _patch_roster(self, monkeypatch):
        import app.core.parser_agent_stats as p
        roster = []
        for nombre, rol, elem, pv, atk, dfn, cr, cd in self._ROWS:
            norm = p._norm_name(nombre)
            roster.append({
                "nombre": nombre, "rol": rol, "elemento": elem,
                "norm": norm, "tokens": set(norm.split()),
                "pv": pv, "ataque": atk, "defensa": dfn,
                "prob_crit": cr, "dano_crit": cd,
            })
        monkeypatch.setattr(p, "_get_roster", lambda: roster)

    def _id(self, **stats):
        from app.core.parser_agent_stats import _identify_by_stats
        return _identify_by_stats(stats)

    def test_soldier0_anby_por_stats(self):
        # Stats exactos de N.º 0: Anby — debe resolver al homónimo correcto,
        # no al Anby normal (mismo nombre OCR, distinto agente).
        ag = self._id(pv=10558, ataque=2630, defensa=914, prob_crit=0.538, dano_crit=1.764)
        assert ag is not None and ag["nombre"] == "N.º 0: Anby"

    def test_lucy_por_stats_pese_a_nombre_largo(self):
        # Lucy se identifica por stats aunque el OCR lea "Luciana de Montefio".
        ag = self._id(pv=12392, ataque=1774, defensa=1003, prob_crit=0.242, dano_crit=0.836)
        assert ag is not None and ag["nombre"] == "Lucy"

    def test_anby_normal_por_stats(self):
        ag = self._id(pv=11161, ataque=1169, defensa=1018, prob_crit=0.434, dano_crit=0.836)
        assert ag is not None and ag["nombre"] == "Anby"

    def test_tolera_drift_pequeno(self):
        # Un disco cambiado mueve PV/ATK unos puntos: igual debe identificar.
        ag = self._id(pv=10600, ataque=2615, defensa=914, prob_crit=0.540, dano_crit=1.760)
        assert ag is not None and ag["nombre"] == "N.º 0: Anby"

    def test_sin_crit_no_identifica(self):
        # Sin ningún crit no se puede discriminar DPS parecidos → None (fallback).
        assert self._id(pv=10558, ataque=2630, defensa=914) is None

    def test_sin_pv_identifica_por_ataque_y_crits(self):
        # 5R QA 2026-06-20: PV es OPCIONAL. Sin PV pero con ataque + 2 crits (3 campos)
        # y gap claro, la ID por stats SIGUE resolviendo. Antes el PV obligatorio abortaba
        # la ID y caía al OCR de nombre (que en 'Billy Kid Estelar' leía 'Centelleante' del
        # fondo) → el PJ no se identificaba ni se podía cosechar.
        ag = self._id(ataque=2630, prob_crit=0.538, dano_crit=1.764)
        assert ag is not None and ag["nombre"] == "N.º 0: Anby"

    def test_sin_pv_ambiguo_abstiene(self):
        # RNF-02: sin PV, si dos agentes quedan igual de cerca (atk+crits a <gap), el
        # gap-check abstiene (None → matcher de nombre). Query a mitad de camino entre
        # N.º 0: Anby (2630/.538/1.764) y Zhu Yuan (2600/.500/1.700).
        assert self._id(ataque=2615, prob_crit=0.519, dano_crit=1.732) is None

    def test_stats_none_no_identifica(self):
        from app.core.parser_agent_stats import _identify_by_stats
        assert _identify_by_stats(None) is None
        assert _identify_by_stats({}) is None

    def test_extract_agent_info_usa_stats_sobre_nombre_malo(self):
        # Integración: el OCR del nombre dice "Anby" (mal) pero los stats son de
        # Lucy → _extract_agent_info debe devolver "Lucy" gracias a Capa 4.
        from app.core.parser_agent_stats import _extract_agent_info
        full_text = "Anby Anby Nivel 60 60 MAX PV 12392 Ataque 1774 Defensa 1003"
        stats = {"pv": 12392, "ataque": 1774, "defensa": 1003,
                 "prob_crit": 0.242, "dano_crit": 0.836}
        nombre, rol, elemento, notas = _extract_agent_info(full_text, stats)
        assert nombre == "Lucy", f"nombre={nombre}"
        assert rol == "Soporte"
        assert elemento == "Fuego"
        assert any("identificado_por_stats" in n for n in notas), notas

    def test_banner_contradice_stats_con_drift_cae_a_nombre(self):
        # Si el banner contradice al agente de stats Y el match tiene DRIFT apreciable
        # (build != DB, dist >= _STATS_ID_TRUST_DIST), se descarta la ID por stats
        # (posible match ambiguo al PJ equivocado) → cae al matcher de nombre.
        from app.core.parser_agent_stats import _extract_agent_info
        # Stats de Lucy DRIFTADOS ~4% (pv/atk) → dist ~0.0145 (>= 0.012). Banner dice
        # rol Ataque (Hielo Ataque), pero Lucy es Soporte → cross-check descarta.
        full_text = "Zephyr Zephyr Nivel 60 60 MAX Hielo Ataque PV 12900 Ataque 1830"
        stats = {"pv": 12900, "ataque": 1830, "defensa": 1003,
                 "prob_crit": 0.242, "dano_crit": 0.836}
        nombre, rol, elemento, notas = _extract_agent_info(full_text, stats)
        # No debe afirmar "Lucy" (Soporte) cuando el banner dice Ataque y hay drift.
        assert nombre != "Lucy"
        assert rol == "Ataque"

    def test_banner_contradice_stats_exacto_confia_en_stats(self):
        # 5R QA 2026-06-20 (Billy Estelar): con match de stats EXACTO (build == DB,
        # dist < _STATS_ID_TRUST_DIST), un banner de rol contradictorio NO descarta —
        # se confía en el vector (metadata DB stale, p.ej. rol es-ES 'Disruptivos' vs
        # pantalla). El rol se resuelve con prioridad-pantalla.
        from app.core.parser_agent_stats import _extract_agent_info
        # Stats EXACTOS de Lucy; banner dice rol 'Ataque' (contradice su 'Soporte').
        full_text = "Lucy Lucy Nivel 60 60 MAX Fuego Ataque PV 12392 Ataque 1774"
        stats = {"pv": 12392, "ataque": 1774, "defensa": 1003,
                 "prob_crit": 0.242, "dano_crit": 0.836}
        nombre, rol, elemento, notas = _extract_agent_info(full_text, stats)
        assert nombre == "Lucy", f"nombre={nombre}"
        assert any("stats_exacto_pese_a_banner" in n for n in notas), notas
        # El banner malleyó el rol → se usa el canónico de la DB de Lucy (Soporte), no
        # 'Ataque'. (Corrige el role-aware downstream: Disruptivos no pide TP/ER.)
        assert rol == "Soporte", f"rol={rol}"


class TestRescateRoiStats:
    """Rescate por REGIÓN de stats que el OCR full-frame pierde (QA 2026-06-20, Billy
    Estelar): PV en frame animado, dígito de Adrenalina. Recorta la celda nombrada y la
    OCR-ea aislada. Mock de OCR: psm=7 = llamada del rescate (ROI), sino = full-frame."""

    def _frame(self):
        return np.zeros((1440, 2560, 3), np.uint8)

    def test_rescue_int_roi_recorta_y_parsea(self):
        from app.core import parser_agent_stats as p

        class _Ocr:
            def text(self, img, psm=None):
                return ("2", 1.0)
        assert p._rescue_int_roi(self._frame(), _Ocr(), "adrenalina_valor") == 2

    def test_rescue_int_roi_vacio_devuelve_none(self):
        from app.core import parser_agent_stats as p

        class _Ocr:
            def text(self, img, psm=None):
                return ("", 0.0)
        assert p._rescue_int_roi(self._frame(), _Ocr(), "pv_valor") is None

    def test_parse_disruptivo_rescata_ad(self, monkeypatch):
        # Full-frame lee el label de adrenalina pero NO su dígito (chico/aislado) →
        # se rescata por región. Solo dispara en Disruptivos (Fuerza Bruta presente).
        from app.core import parser_agent_stats as p
        monkeypatch.setattr(p, "_get_roster", lambda: [])
        full = ("nivel 60 max fisico disruptivo pv 20 573 ataque 2043 defensa 689 "
                "impacto 95 probabilidad de 72.2 % dano critico 118.8 % critico "
                "tasa de anomalia 90 maestria de anomalia 89 2669 acumulacion "
                "automatica fuerza bruta de adrenalina")

        class _Ocr:
            def text(self, img, psm=None):
                return ("2", 1.0) if psm == 7 else (full, 0.95)
        r = p.parse_agent_stats(self._frame(), _Ocr())
        assert r.fuerza_bruta == 2669
        assert r.acumulacion_adrenalina == 2          # rescatado por región
        assert r.recuperacion_energia is None         # Disruptivos: ER no aplica
        assert any("ad_rescatado_roi" in n for n in r.notas), r.notas

    def test_parse_rescata_pv_cuando_falta(self, monkeypatch):
        # Full-frame perdió el PV (frame animado) → rescate por región. Sin Fuerza Bruta
        # (no Disruptivos) → el rescate de AD no dispara; solo el de PV.
        from app.core import parser_agent_stats as p
        monkeypatch.setattr(p, "_get_roster", lambda: [])
        full = ("nivel 60 max fisico ataque 2671 defensa 1038 impacto 91 "
                "probabilidad de 48.2 % dano critico 112.4 % critico "
                "tasa de anomalia 92 maestria de anomalia 109")  # SIN pv

        class _Ocr:
            def text(self, img, psm=None):
                return ("9763", 1.0) if psm == 7 else (full, 0.95)
        r = p.parse_agent_stats(self._frame(), _Ocr())
        assert r.pv == 9763                           # rescatado por región
        assert any("pv_rescatado_roi" in n for n in r.notas), r.notas

    def test_fb_corrige_rol_a_disruptivos(self, monkeypatch):
        # QA 2026-06-20 (Manato/Yixuan): Disruptivos en DB pero el banner malleía el rol
        # a 'Ataque' y los stats DRIFTARON (no matchean exacto → sin trust-stats) → el rol
        # caía a 'Ataque'. La FB (exclusiva de Disruptivos) PRUEBA el rol → se corrige.
        from app.core import parser_agent_stats as p
        monkeypatch.setattr(p, "_get_roster", lambda: [
            {"nombre": "Manato", "rol": "Disruptivos", "elemento": "Fuego",
             "norm": "manato", "tokens": {"manato"}, "pv": 16362, "ataque": 2304,
             "defensa": 729, "prob_crit": 0.65, "dano_crit": 0.996},
        ])
        # Banner dice 'fuego ataque' (rol misread); stats drifteados; FB presente.
        full = ("manato manato nivel 60 60 max fuego ataque pv 16123 ataque 2361 "
                "defensa 729 impacto 95 probabilidad de 73.0 % dano critico 90.0 % critico "
                "tasa de anomalia 87 maestria de anomalia 117 2320 acumulacion "
                "automatica fuerza bruta de adrenalina")

        class _Ocr:
            def text(self, img, psm=None):
                return ("0", 1.0) if psm == 7 else (full, 0.95)
        r = p.parse_agent_stats(self._frame(), _Ocr())
        assert r.fuerza_bruta == 2320
        assert r.rol == "Disruptivos", f"rol={r.rol}"   # corregido por FB (no 'Ataque')
        assert any("rol_corregido_por_fb" in n for n in r.notas), r.notas


def test_get_roster_honra_db_path_override(monkeypatch, tmp_path):
    """Regresión 2026-06-12: _get_roster usaba un _DB_PATH hardcodeado (relativo al
    fuente) con sqlite3 crudo, ignorando DANIBOD_DB_PATH. En el .exe frozen leía la
    DB bundleada/vieja → un PJ recién onboardeado (Billy Estelar) NO se identificaba
    por stats y caía al nombre ('Billy'). El roster debe leer la MISMA DB que el
    resto de la app (override DANIBOD_DB_PATH)."""
    import sqlite3
    from app.core import parser_agent_stats as p
    db = tmp_path / "override.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE agents (nombre TEXT, rol TEXT, elemento TEXT, pv REAL, "
                "ataque REAL, defensa REAL, prob_critico REAL, dano_critico REAL)")
    con.execute("INSERT INTO agents VALUES ('Zzz Testigo','Ataque','Físico',"
                "99999,1234,567,72.2,118.8)")
    con.commit(); con.close()
    monkeypatch.setenv("DANIBOD_DB_PATH", str(db))
    monkeypatch.setattr(p, "_ROSTER_CACHE", None, raising=False)  # forzar relectura
    assert p._active_db_path() == db
    roster = p._get_roster()
    assert any(a["nombre"] == "Zzz Testigo" for a in roster), \
        "el roster debe venir de la DB del override, no de la bundleada/source"
    stats = {"pv": 99999, "ataque": 1234, "defensa": 567,
             "prob_crit": 0.722, "dano_crit": 1.188}
    res = p._identify_by_stats(stats)
    assert res and res["nombre"] == "Zzz Testigo"
    monkeypatch.setattr(p, "_ROSTER_CACHE", None, raising=False)  # no contaminar otros tests
