"""El pase de templates de `classify`: coste acotado y salida IDÉNTICA.

Contexto (Dev_IA 2026-08-19): `_template_candidates` corría 31 `cv2.matchTemplate` sobre el
frame COMPLETO (3,7 Mpx). Medido: cada llamada cuesta ~106 ms **sin importar el tamaño del
template** (uno de 8×8 cuesta lo mismo que uno de 1022×431), porque el trabajo pesado es del lado
de la IMAGEN y OpenCV lo recomputa en cada llamada. Total ~3,1 s, el 83 % del ciclo del monitor.

Lo que fija este archivo son las dos mitades del arreglo:

1. **El coste** (`test_no_matchea_*`, `test_dedup_*`) — se mide CONTANDO LLAMADAS, no
   cronometrando. Un assert de tiempo en Windows es una fuente de flakes conocida (ver el
   docstring de `test_bench_censo_bajo_3ms`); el número de llamadas y el tamaño de la imagen que
   reciben son determinísticos.

2. **La salida** (`test_candidatos_identicos_al_baseline`) — la lista de candidatos y sus
   confianzas tienen que salir EXACTAMENTE iguales a como salían antes del refactor. El baseline
   está congelado en `fixtures/template_candidates_baseline.json`, generado con la implementación
   vieja. Es la red que permite tocar el pase de templates sin recalibrar `THRESHOLD_BY_STATE`:
   el score final se sigue calculando a resolución completa sobre el píxel original.

**Para regenerar el baseline** (solo si cambian los templates o sus umbrales, NUNCA para "arreglar"
un test que se puso rojo por un cambio de código):

    python app/tests/unit/test_detector_template_pipeline.py --regenerar
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.detector import _COARSE_PEAKS, ScreenDetector

REPO = Path(__file__).resolve().parents[3]
TRIGGERS = REPO / "Documentacion" / "Screenshots_Triggers"
BASELINE = Path(__file__).resolve().parents[1] / "fixtures" / "template_candidates_baseline.json"

# Un frame por familia de pantalla + falsos positivos. Rutas relativas a TRIGGERS.
FRAMES_BASELINE = [
    "Discos_Triggers/01_Pantalla_Resultado_Desafio/Ejemplo_1.png",
    "Discos_Triggers/02_Detalle_Disco_Desde_Resultado/Ejemplo_1.png",
    "Discos_Triggers/05_Upgrade_PRE_nivel0/Ejemplo_1.png",
    "Discos_Triggers/08_Pantallas_Menu_Transicion/Pantalla_patrulla_de_area(opcional).png",
    "Discos_Triggers/09_Inventario_discos_general/Ejemplo_9.png",
    "Discos_Triggers/12_Desmontaje/Ejemplo_1.png",
    "Discos_Triggers/13_Seleccion_set_farmeo/Ejemplo_1.png",
    "Discos_Triggers/14_Slots_equipamiento/Ejemplo_Slot1_1.png",
    "Triggers_Generales/Falsos_positivos/Menu_Pausa_1.png",
    "Triggers_Generales/Falsos_positivos/Guia_Rapida_2.png",
    "Triggers_Generales/Falsos_positivos/Modo_foto_1.png",
    "Triggers_Generales/Falsos_positivos/Eventos_3.png",
]

FRAME_S9 = TRIGGERS / "Discos_Triggers/09_Inventario_discos_general/Ejemplo_9.png"


def _load(path: Path):
    if not path.exists():
        return None
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


class _ContadorMatchTemplate:
    """Envuelve `cv2.matchTemplate` y anota, por llamada, el tamaño de la IMAGEN y el
    contenido del TEMPLATE. Con eso alcanza para probar las dos propiedades del arreglo
    sin cronometrar nada."""

    def __init__(self):
        self.llamadas: list[tuple[int, bytes]] = []
        self._real = cv2.matchTemplate

    def __enter__(self):
        def espia(imagen, plantilla, metodo, *a, **kw):
            self.llamadas.append((int(imagen.shape[0]) * int(imagen.shape[1]),
                                  plantilla.tobytes()))
            return self._real(imagen, plantilla, metodo, *a, **kw)

        cv2.matchTemplate = espia
        return self

    def __exit__(self, *exc):
        cv2.matchTemplate = self._real
        return False

    @property
    def sobre_frame_completo(self) -> int:
        """Llamadas cuya imagen es de 1 Mpx o más: las caras, las que hay que eliminar."""
        return sum(1 for px, _ in self.llamadas if px >= 1_000_000)

    def por_template(self) -> dict[bytes, int]:
        cuenta: dict[bytes, int] = {}
        for _, tmpl in self.llamadas:
            cuenta[tmpl] = cuenta.get(tmpl, 0) + 1
        return cuenta


@pytest.fixture(scope="module")
def frame_s9():
    f = _load(FRAME_S9)
    if f is None:
        pytest.skip(f"falta el fixture {FRAME_S9}")
    assert f.shape[0] * f.shape[1] >= 3_000_000, "el fixture tiene que ser full-res para este test"
    return f


def test_no_matchea_el_frame_completo_una_vez_por_template(frame_s9):
    """El pase de templates NO puede correr `matchTemplate` sobre el frame entero por cada
    template. Es la causa raíz de los 3,1 s: 31 llamadas × ~106 ms, y el coste lo pone el
    tamaño del frame, no el del template."""
    det = ScreenDetector()

    with _ContadorMatchTemplate() as espia:
        det._template_candidates(frame_s9)

    assert espia.sobre_frame_completo == 0, (
        f"{espia.sobre_frame_completo} llamadas a matchTemplate sobre una imagen de ≥1 Mpx "
        f"(de {len(espia.llamadas)} en total). El pase grueso tiene que LOCALIZAR sobre el frame "
        f"reducido y el full-res confirmar solo dentro de un ROI chico."
    )


def test_dedup_un_archivo_de_template_no_se_matchea_una_vez_por_estado(frame_s9):
    """`s23_sustitucion.png` lo declaran S23, S25 y S29; `s17_personalizacion_pistas.png`,
    S17 y S26; `s9_inventario_general.png`, S9 y S30. Son 31 entradas sobre 27 archivos: cuatro
    matcheos que recalculan un número ya calculado."""
    det = ScreenDetector()

    with _ContadorMatchTemplate() as espia:
        det._template_candidates(frame_s9)

    tope = 1 + _COARSE_PEAKS   # 1 pase grueso + una confirmación por pico
    repetidos = {t: n for t, n in espia.por_template().items() if n > tope}
    assert not repetidos, (
        f"{len(repetidos)} contenidos de template se matchearon más de {tope} veces "
        f"(1 pase grueso + {_COARSE_PEAKS} confirmaciones): {sorted(repetidos.values())}. "
        f"Sin dedup, el archivo que comparten S23/S25/S29 se matchea el triple."
    )


def test_candidatos_identicos_al_baseline():
    """La red de seguridad del refactor: mismos códigos, mismas confianzas, mismo orden.

    Esto es lo que MANDA — la lista de candidatos es lo único que gobierna qué detecta el
    monitor. Si se pone rojo, el pase de templates cambió de OPINIÓN, no solo de velocidad.
    No se regenera el baseline para taparlo.
    """
    if not BASELINE.exists():
        pytest.skip(f"falta el baseline {BASELINE} (generarlo con --regenerar)")
    esperado = json.loads(BASELINE.read_text(encoding="utf-8"))
    det = ScreenDetector()

    revisados = 0
    for rel, esperados in esperado.items():
        frame = _load(TRIGGERS / rel)
        if frame is None:
            continue
        passing, _ = det._template_candidates(frame)
        obtenido = [[c.code, c.confidence, c.template_name] for c in passing]
        assert obtenido == esperados["passing"], f"cambió la clasificación de {rel}"
        revisados += 1

    assert revisados >= 8, f"solo se pudieron revisar {revisados} frames del baseline"


def test_diagnostico_s12_solo_puede_subestimar_y_no_cambia_de_lado_del_umbral_del_latch():
    """El diagnóstico de S12 (mejor match global) NO se puede preservar exacto, y no es cosmético.

    Exacto es imposible: el máximo global sobre los 31 templates solo se conoce matcheándolos
    todos a resolución completa, que es justo lo que se eliminó. Y no es cosmético porque esa
    confianza decide en `monitor` si un frame no-detalle resetea la identidad latcheada
    (`_DETAIL_RESET_MIN_CONF = 0.50`) — moverla de lado del umbral es reabrir el latch sostenido.

    Lo que sí se garantiza, y es lo que fija este test:
      1. **Solo puede subestimar.** El ROI barre un subconjunto de las posiciones del match
         global ⇒ su máximo nunca es mayor. Un diagnóstico inflado sería el peligroso.
      2. **No cruza el 0.50.** Medido sobre 102 frames: con top-1 hubo 1 cruce; con
         `_COARSE_DIAG_TOP` = 3, ninguno.
    """
    if not BASELINE.exists():
        pytest.skip(f"falta el baseline {BASELINE} (generarlo con --regenerar)")
    esperado = json.loads(BASELINE.read_text(encoding="utf-8"))
    det = ScreenDetector()

    revisados = 0
    for rel, esperados in esperado.items():
        frame = _load(TRIGGERS / rel)
        if frame is None:
            continue
        _, s12 = det._template_candidates(frame)
        viejo = esperados["s12"][1]
        assert s12.confidence <= viejo + 2e-3, (
            f"{rel}: el diagnóstico SUBIÓ ({viejo} -> {s12.confidence}). El ROI es un máximo "
            f"sobre un subconjunto: no puede dar más que el global."
        )
        assert (s12.confidence >= 0.50) == (viejo >= 0.50), (
            f"{rel}: el diagnóstico cruzó el umbral del reset de latch "
            f"({viejo} -> {s12.confidence})"
        )
        revisados += 1

    assert revisados >= 8, f"solo se pudieron revisar {revisados} frames del baseline"


def test_no_subestima_cuando_el_pase_grueso_apunta_al_lugar_equivocado():
    """El único modo de falla conocido del arreglo, cerrado de entrada.

    El pase grueso LOCALIZA y el full-res confirma dentro de un ROI alrededor de ese punto. Si
    el máximo grueso cae en un lugar distinto del máximo real, el ROI mira donde no es y el score
    sale bajo. Medido sobre el corpus: la distancia entre un argmax y el otro es p50 = 1 px, pero
    **llegó a 167 px**.

    Este frame lo fuerza a propósito. En A hay un SEÑUELO: una copia del template más difuminada.
    El desenfoque es de baja frecuencia, así que **sobrevive intacto al reducir a 1/4** y el señuelo
    se lleva el máximo grueso (0.95); a resolución completa, en cambio, matchea peor (0.93). En B
    está el template exacto, corrido 1 px respecto de la grilla de submuestreo: eso le baja el
    score grueso (0.54, segundo pico) pero a resolución completa es 1.00, el máximo real.

    Con un solo pico se reporta el señuelo. Se exige el máximo global REAL, comparado contra
    `cv2.matchTemplate` sobre el frame entero, que es la definición.
    """
    rng = np.random.default_rng(11)
    base = rng.integers(0, 256, size=(64, 64, 3), dtype=np.uint8)
    tmpl = cv2.GaussianBlur(base, (9, 9), 3)
    senuelo = cv2.GaussianBlur(tmpl, (9, 9), 4)

    frame = np.zeros((900, 1400, 3), dtype=np.uint8)
    assert frame.shape[0] * frame.shape[1] >= 1_000_000, "tiene que tomar el camino rápido"
    frame[100:164, 100:164] = senuelo      # A — alineado a la grilla: gana el pase grueso
    frame[601:665, 901:965] = tmpl         # B — 1 px fuera de fase: el máximo real

    det = ScreenDetector()
    det._state_machine = None
    det._templates = [{"code": "S2", "name": "fake_peaks", "img": tmpl}]

    real = float(cv2.minMaxLoc(cv2.matchTemplate(
        cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY),
        cv2.cvtColor(tmpl, cv2.COLOR_BGR2GRAY),
        cv2.TM_CCOEFF_NORMED))[1])
    assert real > 0.95, f"el fixture no arma el caso: el máximo real es {real:.3f}"

    passing, s12 = det._template_candidates(frame)
    reportado = passing[0].confidence if passing else s12.confidence
    assert reportado == pytest.approx(real, abs=2e-3), (
        f"el pase de templates subestimó el match: reportó {reportado:.3f} contra un máximo real "
        f"de {real:.3f}. El ROI se quedó mirando el señuelo — hacen falta más picos del mapa grueso."
    )


def test_frame_chico_sigue_funcionando():
    """Frames por debajo del umbral de tamaño (los sintéticos de otros tests) no pasan por el
    camino rápido: el pase grueso no tiene nada que ahorrar ahí y reducirlos solo agregaría
    ruido. Tienen que seguir clasificando igual."""
    det = ScreenDetector()
    det._state_machine = None

    rng = np.random.default_rng(7)
    patron = rng.integers(0, 256, size=(40, 40, 3), dtype=np.uint8)
    frame = np.zeros((200, 400, 3), dtype=np.uint8)
    frame[20:60, 20:60] = patron
    det._templates = [{"code": "S2", "name": "fake_s2", "img": patron}]

    passing, s12 = det._template_candidates(frame)
    assert [c.code for c in passing] == ["S2"], f"got {[(c.code, c.confidence) for c in passing]}"
    assert passing[0].confidence == pytest.approx(1.0, abs=1e-3)


def test_templates_mas_grandes_que_el_frame_se_saltean():
    """Invariante viejo que hay que preservar: un template que no entra en el frame se saltea,
    no rompe."""
    det = ScreenDetector()
    det._state_machine = None
    frame = np.zeros((50, 50, 3), dtype=np.uint8)
    det._templates = [{"code": "S2", "name": "gigante",
                       "img": np.zeros((200, 200, 3), dtype=np.uint8)}]

    passing, s12 = det._template_candidates(frame)
    assert passing == []
    assert s12.code == "S12"


def _regenerar() -> None:
    """Congela la salida ACTUAL de `_template_candidates` como baseline."""
    det = ScreenDetector()
    salida = {}
    for rel in FRAMES_BASELINE:
        frame = _load(TRIGGERS / rel)
        if frame is None:
            print(f"  FALTA {rel}")
            continue
        passing, s12 = det._template_candidates(frame)
        salida[rel] = {
            "passing": [[c.code, c.confidence, c.template_name] for c in passing],
            "s12": [s12.code, s12.confidence, s12.template_name],
        }
        print(f"  {rel} -> {[(c.code, c.confidence) for c in passing]}")
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nbaseline: {len(salida)} frames -> {BASELINE}")


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(REPO))
    if "--regenerar" in sys.argv:
        _regenerar()
    else:
        print(__doc__)
