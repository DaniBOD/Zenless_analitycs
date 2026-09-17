"""El caché de la lectura del header del inventario: qué se cachea y CUÁNTO VIVE.

En un `classify` de S9 corren los dos verifies del par (S30 primero, falla; después S9) y los dos
mandan al OCR **el mismo recorte byte a byte** — verificado por sha256 antes de escribir una línea
de caché, no deducido del código. Eran ~330 ms pagados dos veces.

Lo que este archivo protege NO es el ahorro (eso es un detalle de velocidad) sino las dos formas
en que un caché así se rompe en silencio:

1. **Cachear el veredicto en vez de la lectura.** Los dos verifies sacan conclusiones OPUESTAS del
   mismo texto. Un caché del veredicto le daría a uno la respuesta del otro.
2. **Sobrevivir a su invocación.** Un caché que dura de más sigue siendo rápido: el bug no aparece
   en los tiempos, aparece en los DATOS, contestando sobre el frame anterior. Por eso el test que
   manda no es "no re-OCReó dentro del mismo classify", sino que **un classify posterior con otro
   frame vuelve a leer**.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core import detector as det_mod
from app.core.detector import ScreenDetector

REPO = Path(__file__).resolve().parents[3]
S9_DIR = REPO / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers" / "09_Inventario_discos_general"


def _load(path: Path):
    if not path.exists():
        return None
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None


def _sha_header(frame) -> str:
    """El recorte que `_read_inventory_header` le manda al OCR, hasheado."""
    h, w = frame.shape[:2]
    x, y, rw, rh = det_mod._S9_HEADER_ROI
    crop = frame[int(y * h):int((y + rh) * h), int(x * w):int((x + rw) * w)]
    return hashlib.sha256(np.ascontiguousarray(crop).tobytes()).hexdigest()


class _EspiaOCR:
    """Anota el sha256 de cada recorte que llega al backend de OCR del header."""

    def __init__(self):
        self.shas: list[str] = []
        self._ocr = None
        self._real = None

    def __enter__(self):
        self._ocr = det_mod._get_dialog_verify_ocr()
        if self._ocr is None:
            pytest.skip("sin Tesseract: el verify del header no corre")
        self._real = self._ocr.text

        def espia(crop, *a, **kw):
            self.shas.append(hashlib.sha256(np.ascontiguousarray(crop).tobytes()).hexdigest())
            return self._real(crop, *a, **kw)

        self._ocr.text = espia
        return self

    def __exit__(self, *exc):
        self._ocr.text = self._real
        return False

    def reset(self):
        self.shas.clear()


@pytest.fixture(scope="module")
def dos_frames_s9():
    a, b = _load(S9_DIR / "Ejemplo_9.png"), _load(S9_DIR / "Ejemplo_1.png")
    if a is None or b is None:
        pytest.skip("faltan los fixtures del inventario de discos")
    if _sha_header(a) == _sha_header(b):
        pytest.skip("los dos fixtures tienen el mismo header: no separan el caso")
    return a, b


def test_la_lectura_no_sobrevive_a_la_invocacion_de_classify(dos_frames_s9):
    """EL test del paso 3. Un `classify` posterior, con otro frame, tiene que volver a leer.

    Si el caché durara de más, la segunda clasificación no llamaría al OCR y decidiría con el
    texto del frame ANTERIOR — rápido y equivocado.
    """
    a, b = dos_frames_s9
    det = ScreenDetector()

    with _EspiaOCR() as espia:
        det.classify(a)
        vistos_a = list(espia.shas)
        cerro = det_mod._lectura_header.get()
        espia.reset()
        det.state_machine_reset()
        det.classify(b)
        vistos_b = list(espia.shas)

    assert cerro is None, (
        "el caché quedó ABIERTO al volver de classify. Además de contestar sobre el frame viejo, "
        "se queda con una referencia al frame (~11 MB) — justo lo que costó la fuga de RNF-06."
    )
    assert vistos_a, "el primer classify no leyó el header (¿cambió el pipeline de S9?)"
    assert vistos_b, (
        "el segundo classify NO volvió a leer el header: el caché sobrevivió a su invocación y "
        "el frame nuevo se está decidiendo con el texto del anterior."
    )
    assert set(vistos_b) == {_sha_header(b)}, (
        f"el segundo classify leyó un recorte que no es el suyo: {set(vistos_b)}"
    )


def test_dentro_de_una_invocacion_el_header_se_lee_una_sola_vez(dos_frames_s9):
    """La mitad barata: los dos verifies del par S9/S30 comparten la lectura.

    Se mide CONTANDO llamadas, no cronometrando (misma razón que en el pase de templates).
    """
    a, _ = dos_frames_s9
    det = ScreenDetector()

    with _EspiaOCR() as espia:
        det.classify(a)

    assert len(espia.shas) == 1, (
        f"el header se leyó {len(espia.shas)} veces en un solo classify; los verifies de S9 y S30 "
        f"mandan el MISMO recorte y tienen que compartir la lectura"
    )


def test_los_dos_recortes_son_byte_identicos(dos_frames_s9):
    """La premisa que habilita el caché, verificada y no supuesta: si los recortes difirieran
    aunque sea en un píxel, compartir la lectura devolvería un resultado que no corresponde."""
    a, _ = dos_frames_s9
    det = ScreenDetector()

    # Sin caché activo, cada verify lee por su cuenta: así se ven los DOS recortes reales.
    with _EspiaOCR() as espia:
        det._clasificar(a)          # el pipeline sin el `with` que abre el caché

    assert len(espia.shas) >= 2, f"esperaba las dos lecturas del par S9/S30, hubo {len(espia.shas)}"
    assert len(set(espia.shas)) == 1, (
        f"los verifies mandan recortes DISTINTOS al OCR ({len(set(espia.shas))} distintos): "
        f"compartir la lectura entre ellos sería incorrecto"
    )


def test_fuera_de_una_clasificacion_no_hay_cache(dos_frames_s9):
    """Llamar al verify suelto (lo hacen varios tests y `tools/`) no debe usar ni dejar caché."""
    a, _ = dos_frames_s9
    assert det_mod._lectura_header.get() is None

    with _EspiaOCR() as espia:
        det_mod._verify_s9(a)
        det_mod._verify_s9(a)

    assert len(espia.shas) == 2, "fuera de un classify cada llamada lee de nuevo"
    assert det_mod._lectura_header.get() is None


def test_el_cache_se_cierra_aunque_la_clasificacion_reviente(dos_frames_s9, monkeypatch):
    """El `reset` va en un `finally`. Si una excepción dejara el caché abierto, contaminaría la
    clasificación siguiente."""
    a, _ = dos_frames_s9
    det = ScreenDetector()

    def explota(*a, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(ScreenDetector, "_clasificar", explota)
    with pytest.raises(RuntimeError):
        det.classify(a)

    assert det_mod._lectura_header.get() is None, "el caché quedó abierto después de una excepción"


# --- ENTRE clasificaciones, por contenido (2026-09-16) --------------------------------------------
#
# Los tests de arriba siguen valiendo tal cual: la caché POR FRAME muere con cada `classify`, y un
# classify con OTRO header vuelve a leer. Lo nuevo es una segunda caché cuya clave no es el frame
# sino los BYTES del recorte: el monitor releía el header en cada pasada del loop rápido (315 de los
# 505 ms del classify en S9) para un título que no cambia mientras se recorren discos.

class _OcrFalso:
    """OCR de mentira para el header: devuelve lo que se le indique y cuenta las lecturas."""

    def __init__(self, respuestas=None):
        self.lecturas = 0
        self._respuestas = list(respuestas or ["Pistas de disco [339/3000]"])

    def text(self, crop, *a, **kw):
        self.lecturas += 1
        r = self._respuestas[min(self.lecturas - 1, len(self._respuestas) - 1)]
        return r, 0.9


def _frame_header(valor: int) -> np.ndarray:
    """Frame sintético: el contenido del recorte del header depende de `valor`."""
    return np.full((1440, 2560, 3), valor, dtype=np.uint8)


def _leer_en_classify(det: ScreenDetector, frame) -> str | None:
    """Lo que hace `classify` con el header, sin correr el pipeline entero."""
    with det_mod._lecturas_de_una_clasificacion(det._header_por_contenido):
        return det_mod._read_inventory_header(frame)


@pytest.fixture
def ocr_falso(monkeypatch):
    ocr = _OcrFalso()
    monkeypatch.setattr(det_mod, "_get_dialog_verify_ocr", lambda: ocr)
    monkeypatch.delenv("DANIBOD_HEADER_CACHE", raising=False)
    return ocr


def test_entre_clasificaciones_el_mismo_contenido_se_lee_una_vez(ocr_falso):
    """Frames DISTINTOS (otro objeto) con el mismo header: una sola lectura. Es el caso del loop
    rápido recorriendo discos en S9."""
    det = ScreenDetector()
    a, b = _frame_header(40), _frame_header(40)
    assert a is not b
    assert _leer_en_classify(det, a) == _leer_en_classify(det, b) == "Pistas de disco [339/3000]"
    assert ocr_falso.lecturas == 1
    assert det.estadisticas_cache_header() == (1, 1)


def test_otro_contenido_se_vuelve_a_leer(ocr_falso):
    """Otro contador u otro título (S9↔S30) son otros bytes: se relee. Es lo que impide que la
    caché conteste sobre un header que ya no está en pantalla."""
    det = ScreenDetector()
    _leer_en_classify(det, _frame_header(40))
    _leer_en_classify(det, _frame_header(41))
    assert ocr_falso.lecturas == 2


def test_un_texto_vacio_no_se_guarda(monkeypatch):
    """Vacío es lo que devuelve el OCR caído. Guardarlo dejaría a `_verify_s30` —que falla cerrado
    sin texto— sin reconocer el inventario de armas mientras el header no cambie de píxeles."""
    ocr = _OcrFalso(["", "Amplificadores [57/2000]"])
    monkeypatch.setattr(det_mod, "_get_dialog_verify_ocr", lambda: ocr)
    monkeypatch.delenv("DANIBOD_HEADER_CACHE", raising=False)
    det = ScreenDetector()
    assert _leer_en_classify(det, _frame_header(40)) == ""
    assert _leer_en_classify(det, _frame_header(40)) == "Amplificadores [57/2000]"
    assert ocr.lecturas == 2, "el vacío quedó fijado y tapó la lectura buena"


def test_fuera_de_classify_la_cache_por_contenido_no_se_usa(ocr_falso):
    """La decisión de `test_fuera_de_una_clasificacion_no_hay_cache` se respeta: un verify suelto
    (tests, `tools/`) lee siempre, aunque el detector tenga una lectura guardada."""
    det = ScreenDetector()
    _leer_en_classify(det, _frame_header(40))
    det_mod._read_inventory_header(_frame_header(40))
    det_mod._read_inventory_header(_frame_header(40))
    assert ocr_falso.lecturas == 3


def test_el_interruptor_la_apaga(ocr_falso, monkeypatch):
    monkeypatch.setenv("DANIBOD_HEADER_CACHE", "0")
    det = ScreenDetector()
    _leer_en_classify(det, _frame_header(40))
    _leer_en_classify(det, _frame_header(40))
    assert ocr_falso.lecturas == 2


def test_la_cache_es_de_cada_detector(ocr_falso):
    """Un detector nuevo (un test, una herramienta) no hereda lecturas de otro."""
    _leer_en_classify(ScreenDetector(), _frame_header(40))
    _leer_en_classify(ScreenDetector(), _frame_header(40))
    assert ocr_falso.lecturas == 2


def test_con_las_capturas_reales_classify_decide_lo_mismo_y_no_relee(dos_frames_s9, monkeypatch):
    """**Contra A2**, con el `classify` REAL y Tesseract real: un segundo classify sobre una copia
    del frame (otro objeto, mismos bytes) no vuelve a leer el header Y decide exactamente lo mismo.
    Lo segundo es lo que importa: la caché tiene que ser invisible en los datos."""
    a, _ = dos_frames_s9
    monkeypatch.delenv("DANIBOD_HEADER_CACHE", raising=False)
    det = ScreenDetector()
    with _EspiaOCR() as espia:
        primero = det.classify(a)
        espia.reset()
        det.state_machine_reset()
        segundo = det.classify(a.copy())
        lecturas_segundo = len(espia.shas)
    assert lecturas_segundo == 0, f"el segundo classify releyó el header {lecturas_segundo} veces"
    assert (segundo.code, segundo.method) == (primero.code, primero.method)
    assert det.estadisticas_cache_header()[0] >= 1
