"""El proceso hijo que hace el OCR. Se lo termina y se lo reemplaza; esa es toda su gracia.

Existe porque PaddleOCR pierde **12,46 MB de commit por inferencia**, lineal y sin plateau
(medición del 2026-08-29, `Dev_IA/2026-08-29_DIAG_La_fuga_es_del_OCR_12MB_por_inferencia.md`). El
censo completo proyecta ~11,7 GB, y el watchdog de RNF-06 reiniciaba la app entera dos veces por
pasada.

Soltar y recrear el **objeto** OCR se probó y no alcanza: devuelve el 60 % y el motor nuevo cuesta
casi lo mismo que se liberó — 108 MB netos de 1264, a 2,2 s el reciclado. Lo único que devuelve
todo es terminar el **proceso**. De ahí este módulo: la app deja de crecer porque lo que crece es
otro proceso, desechable.

## Por qué no escribe al log

`app.log` lo maneja un `RotatingFileHandler` del proceso padre. Dos procesos rotando el mismo
archivo se pisan, y el resultado —un log truncado -- es peor que no tener las líneas del worker.
Así que el worker **no loguea**: devuelve el error como dato y el padre lo escribe. Una sola
autoridad sobre el archivo.

## Por qué desactiva las métricas

`DANIBOD_METRICS` se hereda del padre. Si el worker también registrara, `ocr_text` quedaría contado
dos veces y encima con dos procesos escribiendo `metrics.db`. La medición que importa para RNF-06
es la de punta a punta —incluido el ida y vuelta por el socket— y ésa la toma el proxy en el padre.
"""
from __future__ import annotations

import os
import socket
import sys

from app.core import ocr_ipc

#: Cuánto espera el hijo a que el padre lo acepte antes de rendirse. Generoso: el padre puede estar
#: ocupado terminando el worker anterior.
_TIMEOUT_CONEXION_S = 30.0


#: Ubicaciones comunes del binario de Tesseract en Windows.
_TESSERACT_CANDIDATES = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
]


def _buscar_tesseract() -> str | None:
    return next((c for c in _TESSERACT_CANDIDATES if os.path.isfile(c)), None)


def construir_backend():
    """El backend OCR real, con la misma preferencia que la app: Paddle primero, Tesseract si no.

    Es la **única** autoridad sobre esa elección — la usan el worker, el camino degradado del proxy
    y el chequeo de arranque del controller. Vivía en `ui/controller.py`; se mudó acá cuando el OCR
    pasó a correr en otro proceso, porque el hijo no puede importar la UI (regla B1: si quedaba en
    los dos lados, se separaban).

    Construir el backend es barato: los dos cargan sus modelos de forma perezosa, en la primera
    inferencia. Por eso sirve también como chequeo de disponibilidad al arrancar.

    Levanta `RuntimeError` si no hay ninguno de los dos, con el mismo texto accionable de siempre.
    """
    try:
        import paddleocr  # noqa: F401  — verifica disponibilidad antes de elegir

        from app.core.ocr_paddle import PaddleBackend
        return PaddleBackend(lang="es"), "paddle"
    except Exception:
        pass
    tess = _buscar_tesseract()
    if tess is None:
        raise RuntimeError(
            "Ni PaddleOCR ni Tesseract estan disponibles.\n"
            "PaddleOCR es el backend esperado. Reinstalar con:\n"
            "    pip install paddlepaddle==2.6.2 paddleocr==2.8.1\n"
            "O instalar Tesseract: winget install UB-Mannheim.TesseractOCR"
        )
    from app.core.ocr_tesseract import TesseractBackend
    return TesseractBackend(tesseract_cmd=tess), "tesseract"


def _calentar(backend) -> None:
    """Fuerza la carga de los modelos con una inferencia de juguete.

    Sin esto el hijo diría "listo" antes de tiempo y los 2,2 s de carga se los comería la primera
    llamada real — justo lo que el pre-calentado existe para evitar. El resultado se descarta; sólo
    interesa el efecto de haber cargado.
    """
    import numpy as np
    try:
        backend.text(np.zeros((32, 96, 3), dtype=np.uint8), psm=7)
    except Exception:
        pass          # que el calentamiento falle no invalida al worker: lo dirá la primera real


def _memoria_mb() -> float:
    """Commit del proceso, que es la métrica sobre la que el padre decide reciclar.

    Commit y no working set a propósito: la fuga es de memoria reservada, y el working set la
    subestima —el 2026-08-29 el watchdog vio 6608 MB de commit mientras el working set marcaba
    2,2 GB—. Medir el working set fue mi error ese día.
    """
    try:
        from app.core.mem_diag import mem_counters
        return mem_counters()[1]
    except Exception:
        return 0.0


def _atender(sock: socket.socket, backend) -> None:
    """Bucle de servicio: un pedido, una respuesta, hasta que el padre cierre."""
    while True:
        try:
            pedido = ocr_ipc.recibir(sock)
        except (ocr_ipc.ErrorProtocolo, OSError):
            return                                  # el padre cerró: fin normal del worker
        metodo, args = pedido
        try:
            valor = getattr(backend, metodo)(*args)
            respuesta = ("ok", valor, _memoria_mb())
        except Exception as exc:
            # El error viaja como DATO. Que una llamada falle no justifica matar al worker: la
            # siguiente puede andar, y el padre ya distingue "el worker se murió" de "esta
            # llamada dio error".
            respuesta = ("err", f"{type(exc).__name__}: {exc}", _memoria_mb())
        try:
            ocr_ipc.enviar(sock, respuesta)
        except OSError:
            return


def ejecutar() -> int:
    """Punto de entrada del hijo. Devuelve el código de salida del proceso."""
    # Antes que nada: que este proceso no toque `metrics.db` (ver docstring del módulo).
    os.environ.pop("DANIBOD_METRICS", None)

    puerto = os.environ.get(ocr_ipc.ENV_PUERTO, "")
    token = os.environ.get(ocr_ipc.ENV_TOKEN, "")
    if not puerto.isdigit() or not token:
        return 2                                    # lanzado mal; el padre lo ve como no-arranque

    sock = socket.create_connection(("127.0.0.1", int(puerto)), timeout=_TIMEOUT_CONEXION_S)
    sock.settimeout(None)                           # a partir de acá el bucle bloquea a propósito
    try:
        ocr_ipc.enviar(sock, {"hola": token})
        try:
            backend, cual = construir_backend()
            _calentar(backend)
        except Exception as exc:
            ocr_ipc.enviar(sock, {"listo": False, "error": f"{type(exc).__name__}: {exc}"})
            return 3
        ocr_ipc.enviar(sock, {"listo": True, "backend": cual, "mem_mb": _memoria_mb()})
        _atender(sock, backend)
        return 0
    finally:
        try:
            sock.close()
        except OSError:
            pass


if __name__ == "__main__":                          # `python -m app.core.ocr_worker` en dev
    sys.exit(ejecutar())
