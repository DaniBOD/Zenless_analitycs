"""El proxy del OCR: reciclado con pre-calentado, reintento, y la caída a en-proceso.

Con workers de mentira (sin Paddle) para que corra rápido. Lo que se verifica es la POLÍTICA:
cuándo se recicla, qué pasa cuando el worker se cae, y que ninguna llamada se pierda en el relevo.
"""
from __future__ import annotations

import time

import numpy as np
import pytest

from app.core import ocr_service
from app.core.ocr_service import OcrProxy, _ErrorDeLlamada

IMG = np.zeros((8, 8, 3), dtype=np.uint8)


class _WorkerFalso:
    """Imita a `_Worker` sin proceso ni socket. `mem_mb` sube sola en cada llamada, como la de
    verdad, para poder ejercer el reciclado sin esperar a que fugue un GB."""

    def __init__(self, nombre="w", por_llamada_mb=100.0, muere_en=None):
        self.nombre = nombre
        self.mem_mb = 0.0
        self._por_llamada = por_llamada_mb
        self._muere_en = muere_en
        self.llamadas: list[tuple] = []
        self.terminado = False
        self._vivo = True

    def vivo(self):
        return self._vivo

    def llamar(self, metodo, args):
        self.llamadas.append((metodo, args))
        if self._muere_en is not None and len(self.llamadas) >= self._muere_en:
            self._vivo = False
            raise OSError("el worker se murió")
        self.mem_mb += self._por_llamada
        return (self.nombre, len(self.llamadas))

    def terminar(self):
        self.terminado = True
        self._vivo = False


@pytest.fixture(autouse=True)
def _sin_inproc(monkeypatch):
    """El escape `DANIBOD_OCR_INPROC` puede estar seteado en la shell de quien corre los tests;
    si lo estuviera, TODOS estos tests pasarían sin ejercer nada."""
    monkeypatch.delenv("DANIBOD_OCR_INPROC", raising=False)


def _fabrica(monkeypatch, workers):
    """Hace que `_levantar_worker` entregue los workers de la lista, en orden."""
    it = iter(workers)
    monkeypatch.setattr(ocr_service, "_levantar_worker", lambda: next(it))


# --- reenvío -------------------------------------------------------------------------------

def test_los_tres_metodos_llegan_al_worker(monkeypatch):
    w = _WorkerFalso()
    _fabrica(monkeypatch, [w])
    p = OcrProxy(techo_mb=10 ** 9)
    p.text(IMG, psm=7, lang="spa")
    p.number(IMG)
    p.text_with_bboxes(IMG)
    assert [m for m, _ in w.llamadas] == ["text", "number", "text_with_bboxes"]
    assert w.llamadas[0][1] == (IMG, 7, "spa"), "los argumentos tienen que viajar tal cual"


def test_un_error_de_la_llamada_no_mata_al_worker(monkeypatch):
    """El backend directo devuelve el valor neutro cuando el OCR falla; el proxy tiene que hacer lo
    mismo, y sobre todo NO reciclar por eso: el worker está sano."""
    class _Enojado(_WorkerFalso):
        def llamar(self, metodo, args):
            self.llamadas.append((metodo, args))
            raise _ErrorDeLlamada("ValueError: qué sé yo")
    w = _Enojado()
    _fabrica(monkeypatch, [w])
    p = OcrProxy(techo_mb=10 ** 9)
    assert p.text(IMG) == ("", 0.0)
    assert p.number(IMG) == (0.0, 0.0)
    assert p.text_with_bboxes(IMG) == []
    assert not w.terminado, "un error de la llamada NO es motivo para tirar el worker"


# --- el worker se cae ----------------------------------------------------------------------

def test_si_el_worker_se_cae_se_relanza_y_la_llamada_SE_RESPONDE(monkeypatch):
    """Lo que el usuario tiene que ver es un resultado, no un hueco. El worker muerto se
    reemplaza y la MISMA llamada se reintenta."""
    muerto = _WorkerFalso("muerto", muere_en=1)
    sano = _WorkerFalso("sano")
    _fabrica(monkeypatch, [muerto, sano])
    p = OcrProxy(techo_mb=10 ** 9)
    assert p.text(IMG) == ("sano", 1)
    assert sano.llamadas, "la llamada tiene que haberse reintentado en el worker nuevo"


def test_dos_caidas_seguidas_caen_a_EN_PROCESO_y_siguen_respondiendo(monkeypatch):
    """La red de seguridad. Peor memoria, pero la app sigue sirviendo — y se ejerce desde un test,
    porque una red que en dev nunca se ejerce nunca se testea (regla D2)."""
    _fabrica(monkeypatch, [_WorkerFalso("a", muere_en=1), _WorkerFalso("b", muere_en=1)])

    class _Local:
        def text(self, img, psm=6, lang="spa"):
            return ("desde el proceso principal", 0.5)
    p = OcrProxy(techo_mb=10 ** 9)
    monkeypatch.setattr(p, "_backend_local", lambda: _Local())

    assert p.text(IMG) == ("desde el proceso principal", 0.5)
    assert p._degradado is True


# --- reciclado con pre-calentado -----------------------------------------------------------

def test_no_recicla_mientras_esta_por_debajo_del_techo(monkeypatch):
    w = _WorkerFalso(por_llamada_mb=1.0)
    _fabrica(monkeypatch, [w])
    p = OcrProxy(techo_mb=1000)
    for _ in range(20):
        p.text(IMG)
    assert not w.terminado
    assert p._repuesto is None and not p._precalentando


def test_al_pasarse_del_techo_precalienta_y_RECIEN_DESPUES_releva(monkeypatch):
    """El punto del pre-calentado: el worker viejo sigue atendiendo mientras el nuevo carga. Si se
    terminara al viejo primero, esos 2,2 s los pagaría una llamada real."""
    viejo = _WorkerFalso("viejo", por_llamada_mb=60.0)
    nuevo = _WorkerFalso("nuevo", por_llamada_mb=60.0)
    _fabrica(monkeypatch, [viejo, nuevo])
    p = OcrProxy(techo_mb=100)

    assert p.text(IMG) == ("viejo", 1)
    assert p.text(IMG) == ("viejo", 2)           # cruza el techo (120 MB) y dispara el precalentado
    for _ in range(50):                          # esperar a que el hilo de precalentado termine
        if p._repuesto is not None or not p._precalentando:
            break
        time.sleep(0.02)
    assert not viejo.terminado, "el viejo NO se puede terminar antes de que el nuevo esté listo"

    assert p.text(IMG) == ("nuevo", 1), "la llamada siguiente ya la atiende el reemplazo"
    assert viejo.terminado, "recién ahí se termina el viejo"


def test_en_el_relevo_no_se_pierde_ni_se_duplica_ninguna_llamada(monkeypatch):
    """El invariante del cambio de turno. Cada llamada tiene que ser atendida exactamente una vez,
    por el worker que sea."""
    viejo = _WorkerFalso("viejo", por_llamada_mb=60.0)
    nuevo = _WorkerFalso("nuevo", por_llamada_mb=0.0)
    _fabrica(monkeypatch, [viejo, nuevo])
    p = OcrProxy(techo_mb=100)

    N = 30
    for _ in range(N):
        p.text(IMG)
        time.sleep(0.005)                        # darle aire al hilo de precalentado
    atendidas = len(viejo.llamadas) + len(nuevo.llamadas)
    assert atendidas == N, f"se atendieron {atendidas} de {N} llamadas"


# --- el escape en-proceso -------------------------------------------------------------------

def test_DANIBOD_OCR_INPROC_no_levanta_ningun_worker(monkeypatch):
    """El escape para QA: deja el sistema como estaba antes de este módulo, fuga incluida."""
    def _explota():
        raise AssertionError("no se debería haber levantado un worker")
    monkeypatch.setattr(ocr_service, "_levantar_worker", _explota)
    monkeypatch.setenv("DANIBOD_OCR_INPROC", "1")

    class _Local:
        def text(self, img, psm=6, lang="spa"):
            return ("local", 1.0)
    p = OcrProxy()
    monkeypatch.setattr(p, "_backend_local", lambda: _Local())
    assert p.text(IMG) == ("local", 1.0)


# --- el registro compartido -----------------------------------------------------------------

def test_el_detector_usa_el_OCR_COMPARTIDO_en_vez_de_armarse_otro(monkeypatch):
    """La mitad del problema que este trabajo vino a resolver: hasta 2026-08-29 el detector se
    construía su propio PaddleBackend, así que había dos motores fugando en el mismo proceso."""
    from app.core import detector
    centinela = object()
    monkeypatch.setattr(ocr_service, "_compartido", centinela)
    try:
        assert detector._get_panel_verify_ocr() is centinela
    finally:
        ocr_service.set_shared_ocr(None)


# --- el proceso de verdad -------------------------------------------------------------------

def test_el_comando_del_hijo_cambia_segun_este_empaquetado(monkeypatch):
    """Empaquetado el hijo es el MISMO `.exe` con un centinela de argv; desde fuente es el módulo.
    Equivocarse acá es el bug que sólo se ve empaquetado (regla D1), así que se fija de los dos
    lados en vez de confiar en probarlo a mano."""
    from app.core import ocr_ipc

    monkeypatch.setattr(ocr_service.sys, "frozen", True, raising=False)
    assert ocr_service._comando_worker()[1:] == [ocr_ipc.FLAG_WORKER]

    monkeypatch.delattr(ocr_service.sys, "frozen", raising=False)
    assert ocr_service._comando_worker()[1:] == ["-m", "app.core.ocr_worker"]


def test_INTEGRACION_un_worker_de_verdad_arranca_y_contesta():
    """El único test que ejerce el camino completo: subprocess real, socket real, Paddle real.

    Los de arriba usan workers de mentira y por eso corren rápido — pero ninguno probaría que el
    hijo arranca. Un camino que en dev nunca se ejerce, nunca se testea (regla D2).
    """
    pytest.importorskip("paddleocr")
    p = OcrProxy(techo_mb=10 ** 9)
    try:
        img = np.full((40, 160, 3), 30, dtype=np.uint8)
        texto, conf = p.text(img)
        assert isinstance(texto, str) and isinstance(conf, float)
        assert p._activo is not None and p._activo.vivo(), "el worker tiene que quedar vivo"
        assert p._activo.mem_mb > 0, "el worker tiene que reportar su memoria: es lo que decide el reciclado"
        assert not p._degradado, "no debería haber caído a en-proceso"
    finally:
        p.cerrar()
