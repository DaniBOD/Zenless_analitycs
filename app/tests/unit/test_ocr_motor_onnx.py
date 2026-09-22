"""El OCR corre sobre ONNX Runtime, con los modelos adentro de `app/` (Fase 2E, 2026-09-21).

**Por qué se cambió el motor.** El panel de S9 es el 75 % de la espera click→log, y no bajaba por
código: filtrar cajas, MKL-DNN, menos hilos y el envoltorio de PaddleOCR dieron entre −5 % y peor.
Lo que sí lo explicaba era la CPU: en el banco costaba 526-800 ms y en vivo 1784, porque el juego
ocupa la máquina. Medido con las ramas intercaladas y el orden sorteado, 19 capturas:

| máquina | paddle inference | onnxruntime | |
|---|---|---|---|
| quieta | 881 ms | 781 ms | −11 % |
| con los 6 núcleos llenos | 2767 ms | 1669 ms | **−40 %** |

O sea que la ventaja **crece justo en la condición real**. Paddle pide 10 hilos sobre 6 núcleos.

**Lo que NO cambia es la lectura**: el pipeline (pre-proceso, post-proceso, pesos) sigue siendo el
de PaddleOCR; sólo cambia quién multiplica. Verificado sobre el corpus entero de S9 comparando lo
que sale del PARSER —set, slot, nivel, main, los 4 substats con sus rolls—: **0 diferencias en
19 capturas**. Eso lo cuidan los tests de `test_parser_disc_s9.py`, que ahora corren por acá.

Lo que cuidan ESTOS tests es lo otro: que el motor elegido sea el que se cree, que los modelos
viajen adentro de la app, y que cuando no se pueda usar ONNX **se diga** en vez de degradarse en
silencio (D2) — un 40 % de latencia extra no se nota mirando, se nota midiendo, y para entonces
nadie se acuerda de este cambio.
"""
from __future__ import annotations

import logging

import pytest

import app.core.ocr_paddle as mod


# --- los modelos viajan adentro de app/ (D1) ---------------------------------------------

def test_los_modelos_viven_adentro_de_app():
    """Regla D1: todo lo que la app lee vive dentro de `app/`. Y acá hay un arreglo de deuda:
    con `use_onnx=True` PaddleOCR **no descarga nada**, así que los pesos dejan de vivir en
    `~/.paddleocr` (fuera de la app, bajados en el primer arranque)."""
    app_dir = mod.Path(mod.__file__).resolve().parents[1]
    for p in (mod._DET_ONNX, mod._REC_ONNX):
        assert p.is_file(), f"falta el modelo {p}"
        assert app_dir in p.parents, f"{p} está fuera de app/ — muere empaquetado"
        assert p.stat().st_size > 1_000_000, f"{p.name} pesa {p.stat().st_size} B: no es el modelo"


# --- la decisión del motor ----------------------------------------------------------------

def test_con_todo_en_su_lugar_el_motor_es_onnx():
    pytest.importorskip("onnxruntime")
    assert mod.motivo_sin_onnx() is None


def test_el_interruptor_devuelve_al_motor_viejo(monkeypatch):
    """La salida sin recompilar: si ONNX diera problemas en vivo, esto vuelve atrás."""
    monkeypatch.setenv(mod._ENV_MOTOR, "paddle")
    motivo = mod.motivo_sin_onnx()
    assert motivo and "paddle" in motivo


def test_si_falta_un_modelo_el_motivo_lo_NOMBRA(monkeypatch, tmp_path):
    """No alcanza con devolver 'no se puede': el motivo tiene que ser accionable."""
    monkeypatch.delenv(mod._ENV_MOTOR, raising=False)
    monkeypatch.setattr(mod, "_DET_ONNX", tmp_path / "no_existe_det.onnx")
    motivo = mod.motivo_sin_onnx()
    assert motivo and "no_existe_det.onnx" in motivo, motivo


def test_si_onnxruntime_no_importa_el_motivo_lo_dice(monkeypatch):
    import builtins
    real = builtins.__import__

    def sin_ort(nombre, *a, **kw):
        if nombre == "onnxruntime":
            raise ImportError("simulado: no está instalado")
        return real(nombre, *a, **kw)

    monkeypatch.delenv(mod._ENV_MOTOR, raising=False)
    monkeypatch.setattr(builtins, "__import__", sin_ort)
    motivo = mod.motivo_sin_onnx()
    assert motivo and "onnxruntime" in motivo, motivo


# --- el EFECTO: qué recibe PaddleOCR ------------------------------------------------------

class _PaddleOCRFalso:
    """Se queda con los kwargs en vez de cargar 600 MB de modelos."""
    ultimo: dict = {}

    def __init__(self, **kwargs):
        _PaddleOCRFalso.ultimo = dict(kwargs)


@pytest.fixture
def paddleocr_falso(monkeypatch):
    paddleocr = pytest.importorskip("paddleocr")
    monkeypatch.setattr(paddleocr, "PaddleOCR", _PaddleOCRFalso)
    _PaddleOCRFalso.ultimo = {}
    return _PaddleOCRFalso


def test_el_backend_le_PASA_el_motor_onnx_a_paddleocr(paddleocr_falso, monkeypatch):
    """Elegir el motor no sirve si el kwarg no llega: esto mira lo que recibió PaddleOCR."""
    pytest.importorskip("onnxruntime")
    monkeypatch.delenv(mod._ENV_MOTOR, raising=False)
    mod.PaddleBackend()._get_ocr()
    kw = paddleocr_falso.ultimo
    assert kw.get("use_onnx") is True, kw
    assert kw.get("det_model_dir") == str(mod._DET_ONNX), kw
    assert kw.get("rec_model_dir") == str(mod._REC_ONNX), kw


def test_sin_onnx_no_le_pasa_rutas_de_modelos(paddleocr_falso, monkeypatch):
    """El camino viejo tiene que quedar EXACTAMENTE como estaba: sin `use_onnx` y sin rutas,
    para que PaddleOCR resuelva sus modelos como siempre."""
    monkeypatch.setenv(mod._ENV_MOTOR, "paddle")
    mod.PaddleBackend()._get_ocr()
    kw = paddleocr_falso.ultimo
    assert "use_onnx" not in kw and "det_model_dir" not in kw and "rec_model_dir" not in kw, kw


def test_caer_al_motor_lento_se_AVISA(paddleocr_falso, monkeypatch, caplog):
    """D2: degradar en silencio es peor que fallar fuerte. Un 40 % de latencia extra no se ve
    mirando la app — si nadie lo escribe, se descubre midiendo tres semanas después."""
    monkeypatch.setenv(mod._ENV_MOTOR, "paddle")
    with caplog.at_level(logging.WARNING, logger=mod.__name__):
        mod.PaddleBackend()._get_ocr()
    avisos = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert avisos, "se cayó al motor lento sin decir nada"
    assert "paddle" in avisos[0].lower()


def test_el_backend_RECUERDA_el_motor_que_uso(paddleocr_falso, monkeypatch):
    """Lo que se reporta es lo que pasó, no lo que se iba a hacer (A3). Antes de cargar no hay
    respuesta: `None` significa "no sé", no "onnx"."""
    monkeypatch.setenv(mod._ENV_MOTOR, "paddle")
    back = mod.PaddleBackend()
    assert back.motor_en_uso() is None, "dice un motor sin haber cargado nada"
    back._get_ocr()
    motor, motivo = back.motor_en_uso()
    assert motor == "paddle inference", motor
    assert motivo and "paddle" in motivo, motivo


# --- el aviso tiene que cruzar del worker al padre (2026-09-22) ---------------------------
#
# El WARNING de la Fase 2E se emitía dentro del worker, que a propósito NO escribe en `app.log`
# (dos procesos rotando el mismo archivo lo truncan). O sea que la red de D2 avisaba en un proceso
# cuyo logging va a DEVNULL: existía y no servía. El motor viaja ahora como dato en el saludo.

class _BackendFalso:
    def __init__(self, motor):
        self._motor = motor

    def motor_en_uso(self):
        return self._motor


def test_el_worker_MANDA_el_motor_en_el_saludo(monkeypatch):
    import app.core.ocr_worker as worker
    monkeypatch.setattr(worker, "_memoria_mb", lambda: 123.0)
    saludo = worker._saludo_listo(_BackendFalso(("paddle inference", "porque sí")), "paddle")
    assert saludo["motor"] == ("paddle inference", "porque sí"), saludo
    assert saludo["listo"] is True and saludo["backend"] == "paddle"


def test_el_saludo_aguanta_un_backend_que_no_elige_motor(monkeypatch):
    """Tesseract no tiene motor que elegir: el saludo no puede reventar por eso."""
    import app.core.ocr_worker as worker
    monkeypatch.setattr(worker, "_memoria_mb", lambda: 0.0)

    class _SinMotor:
        pass

    assert worker._saludo_listo(_SinMotor(), "tesseract")["motor"] is None


def test_el_PADRE_escribe_el_aviso_del_worker(caplog):
    """El corazón del arreglo: el motivo tiene que terminar en el log del padre, con su texto
    accionable intacto."""
    import app.core.ocr_service as svc
    with caplog.at_level(logging.WARNING, logger=svc.__name__):
        svc._anotar_motor_del_worker(
            {"backend": "paddle", "motor": ("paddle inference", "no están los modelos X.onnx")})
    avisos = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert avisos, "el worker cayó al motor lento y el padre no escribió nada"
    assert "no están los modelos X.onnx" in avisos[0], avisos


def test_el_padre_no_grita_cuando_el_worker_quedo_en_onnx(caplog):
    import app.core.ocr_service as svc
    with caplog.at_level(logging.INFO, logger=svc.__name__):
        svc._anotar_motor_del_worker({"backend": "paddle", "motor": ("onnxruntime", None)})
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("onnxruntime" in r.getMessage() for r in caplog.records), caplog.records


def test_si_el_worker_NO_dice_el_motor_el_padre_avisa(caplog):
    """Ausencia no es "todo bien": un saludo sin motor con backend paddle puede ser el motor lento
    corriendo sin que nadie se entere, que es el bug que este arreglo viene a cerrar."""
    import app.core.ocr_service as svc
    with caplog.at_level(logging.WARNING, logger=svc.__name__):
        svc._anotar_motor_del_worker({"backend": "paddle", "mem_mb": 1.0})
    assert [r for r in caplog.records if r.levelno >= logging.WARNING], "se lo tragó en silencio"
