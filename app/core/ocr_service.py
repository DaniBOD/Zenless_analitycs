"""El OCR visto desde la app: un `OcrBackend` normal que por dentro habla con otro proceso.

La frontera cae exactamente en `OcrBackend` —tres métodos— así que ni el parser ni el monitor se
enteran de que el OCR dejó de correr acá.

## Por qué

PaddleOCR pierde **12,46 MB de commit por inferencia**, lineal y sin plateau. El censo completo
proyecta ~11,7 GB y el watchdog de RNF-06 reiniciaba la app entera dos veces por pasada. Reciclar
el *objeto* OCR se midió y da 108 MB netos de 1264 (~9 %) a 2,2 s el reciclado; lo único que
devuelve todo es terminar el *proceso*. Detalle en
`Dev_IA/2026-08-29_DIAG_La_fuga_es_del_OCR_12MB_por_inferencia.md`.

## Pre-calentado: por qué hay dos workers por un rato

Reciclar cuesta 2,2 s de carga de modelos. Si se hiciera en el momento, esos segundos los pagaría
una llamada real y se verían como un tirón. En vez de eso se levanta el reemplazo **en paralelo**,
sin dejar de atender con el viejo, y el turno se pasa cuando el nuevo ya está caliente. El costo es
~1,3 GB durante unos segundos con los dos vivos — por eso el techo de reciclado se elige dejando
lugar para ese pico bajo el watchdog de 6 GB.

## Qué pasa si el worker se cae

Se relanza y se reintenta una vez. Si vuelve a fallar se cae al backend **en proceso**, que es la
conducta de siempre: peor memoria, pero la app sigue sirviendo y el watchdog sigue detrás. Esa red
se puede ejercer desde un test (`DANIBOD_OCR_INPROC`, y matando el worker a propósito): una red que
en dev nunca se ejerce, nunca se testea (regla D2).
"""
from __future__ import annotations

import logging
import os
import secrets
import socket
import subprocess
import sys
import threading
from pathlib import Path

import numpy as np

from app.core import ocr_ipc
from app.core.metrics import measure_latency
from app.core.ocr_backend import OcrBackend

log = logging.getLogger(__name__)

#: Techo de commit del worker (MB) que dispara el pre-calentado del reemplazo.
#:
#: Es el control REAL del consumo del sistema, y conviene tenerlo presente: el watchdog de RNF-06
#: (`monitor._ram_watchdog`) lee el commit de **su propio proceso**, así que con el OCR afuera deja
#: de ver la memoria que importa. Ya no es la red que contiene esto — es este techo.
#:
#: El disparo no es instantáneo: entre que se pasa del techo y el reemplazo está caliente siguen
#: entrando llamadas. **Medido con techo 1200: el worker llegaba a 1700-1975 MB**, o sea ~750 MB de
#: sobrepaso (el tiempo de levantar y calentar el repuesto, estirado por la contención de CPU entre
#: los dos procesos). El sobrepaso es acotado en el tiempo, no proporcional al techo.
#:
#: Con 2500: pico ≈ 2500 + 750 de sobrepaso + ~650 del repuesto calentando = **~3,9 GB** entre los
#: dos procesos. A 12,46 MB por inferencia son ~200 inferencias ≈ 85 discos entre reciclados, o sea
#: ~5 en un censo completo — todos invisibles, porque el relevo ocurre con el repuesto ya listo.
TECHO_RECICLADO_MB = 2500.0

#: Cuánto se espera una respuesta antes de dar el worker por colgado. Generoso contra una
#: inferencia lenta (las medidas van de 124 a 235 ms), corto contra un cuelgue de verdad.
TIMEOUT_LLAMADA_S = 60.0
_TIMEOUT_ACEPTAR_S = 30.0
#: La primera carga de modelos puede ser lenta en frío (disco, antivirus). No es un cuelgue.
_TIMEOUT_LISTO_S = 180.0

_ENV_INPROC = "DANIBOD_OCR_INPROC"


def en_proceso_forzado() -> bool:
    """¿Está pedido correr el OCR acá mismo, sin worker? (`DANIBOD_OCR_INPROC=1`)

    Es el escape para QA y para diagnosticar: deja el sistema exactamente como estaba antes de este
    módulo, fuga incluida.
    """
    return os.environ.get(_ENV_INPROC, "").strip() not in ("", "0", "false", "no")


def _comando_worker() -> list[str]:
    """Cómo lanzar al hijo, según estemos empaquetados o corriendo desde fuente.

    Empaquetado el hijo es **el mismo `.exe`** con un centinela de argv; `app/main.py` lo desvía
    antes de importar Qt. Desde fuente es el módulo del worker con el intérprete del venv.
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, ocr_ipc.FLAG_WORKER]
    return [sys.executable, "-m", "app.core.ocr_worker"]


def _entorno_hijo(puerto: int, token: str) -> dict:
    env = dict(os.environ)
    env[ocr_ipc.ENV_PUERTO] = str(puerto)
    env[ocr_ipc.ENV_TOKEN] = token
    if not getattr(sys, "frozen", False):
        # Desde fuente el hijo necesita encontrar el paquete `app`. Se deriva de la ubicación de
        # ESTE archivo y no del cwd, que es de quien haya lanzado el acceso directo.
        # `parents[2]` sale de `app/` a propósito y sólo vale acá: empaquetado no se usa (regla D1).
        raiz = str(Path(__file__).resolve().parents[2])
        previo = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = raiz + (os.pathsep + previo if previo else "")
    return env


class _Worker:
    """Un proceso hijo vivo y su socket. No sabe nada de reciclado ni de reintentos."""

    def __init__(self, proc: subprocess.Popen, sock: socket.socket, backend: str):
        self.proc = proc
        self.sock = sock
        self.backend = backend
        self.mem_mb = 0.0

    def vivo(self) -> bool:
        return self.proc.poll() is None

    def llamar(self, metodo: str, args: tuple):
        """Un pedido, una respuesta. Levanta si el worker murió, se colgó o se desencuadró."""
        ocr_ipc.enviar(self.sock, (metodo, args))
        estado, carga, mem = ocr_ipc.recibir(self.sock)
        self.mem_mb = mem
        if estado == "err":
            # Error de la llamada, no del worker: el proceso sigue sano y la próxima puede andar.
            raise _ErrorDeLlamada(carga)
        return carga

    def terminar(self) -> None:
        """Cierra y termina. **No levanta nunca**: se llama desde caminos de limpieza y desde el
        relevo, y un fallo acá no puede tumbar la llamada que está en curso."""
        for cerrar in (self.sock.close, self.proc.terminate):
            try:
                cerrar()
            except Exception as exc:            # noqa: BLE001 — limpieza: se anota y se sigue
                log.debug("OCR: al cerrar el worker pid=%s: %r", self.proc.pid, exc)
        try:
            self.proc.wait(timeout=5)
        except Exception:                       # noqa: BLE001
            log.debug("OCR: el worker pid=%s no terminó solo; se lo mata", self.proc.pid)
            try:
                self.proc.kill()
            except Exception as exc:            # noqa: BLE001
                log.debug("OCR: tampoco se pudo matar pid=%s: %r", self.proc.pid, exc)


class _ErrorDeLlamada(RuntimeError):
    """El worker atendió y devolvió error. No es motivo para reciclarlo."""


def _levantar_worker() -> _Worker:
    """Lanza un hijo y espera a que esté **caliente**. Bloquea hasta 3 minutos.

    El padre escucha y el hijo conecta —y no al revés— porque así el puerto lo elige el sistema
    (`:0`) y no hay que inventar un mecanismo para que el hijo lo comunique de vuelta.
    """
    token = secrets.token_hex(16)
    lis = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lis.bind(("127.0.0.1", 0))          # loopback explícito: nada escuchando fuera de la máquina
        lis.listen(1)
        lis.settimeout(_TIMEOUT_ACEPTAR_S)
        puerto = lis.getsockname()[1]
        proc = subprocess.Popen(
            _comando_worker(), env=_entorno_hijo(puerto, token),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            sock, _ = lis.accept()
        except TimeoutError as exc:
            proc.kill()
            raise RuntimeError("el worker de OCR no conectó a tiempo") from exc
    finally:
        lis.close()

    sock.settimeout(_TIMEOUT_LISTO_S)
    try:
        hola = ocr_ipc.recibir(sock)
        if not isinstance(hola, dict) or not secrets.compare_digest(hola.get("hola", ""), token):
            raise RuntimeError("saludo inválido en el socket del OCR")
        listo = ocr_ipc.recibir(sock)
        if not listo.get("listo"):
            raise RuntimeError(f"el worker no pudo levantar el OCR: {listo.get('error')}")
    except Exception:
        sock.close()
        proc.kill()
        raise
    sock.settimeout(TIMEOUT_LLAMADA_S)
    w = _Worker(proc, sock, listo.get("backend", "?"))
    w.mem_mb = float(listo.get("mem_mb") or 0.0)
    log.info("OCR en proceso aparte: worker pid=%s backend=%s", proc.pid, w.backend)
    return w


class OcrProxy(OcrBackend):
    """`OcrBackend` que delega en un worker reciclable. Seguro para usar desde varios hilos."""

    def __init__(self, techo_mb: float = TECHO_RECICLADO_MB):
        self._techo = techo_mb
        self._lock = threading.RLock()
        self._activo: _Worker | None = None
        self._repuesto: _Worker | None = None
        self._precalentando = False
        self._local = None                  # backend en-proceso: sólo si el worker no se puede usar
        self._degradado = False

    # ---- ciclo de vida ------------------------------------------------------------------

    def _backend_local(self):
        if self._local is None:
            from app.core.ocr_worker import construir_backend
            self._local, _ = construir_backend()
        return self._local

    def _asegurar_activo(self) -> _Worker | None:
        """El worker con el que hay que atender ahora, o None si estamos degradados."""
        if self._degradado:
            return None
        if self._repuesto is not None:                # el reemplazo ya está caliente: cambio de turno
            viejo, self._activo = self._activo, self._repuesto
            self._repuesto = None
            if viejo is not None:
                log.info("OCR: relevo del worker (el viejo llegó a %.0f MB)", viejo.mem_mb)
                viejo.terminar()
        if self._activo is None or not self._activo.vivo():
            if self._activo is not None:
                self._activo.terminar()
            self._activo = _levantar_worker()
        return self._activo

    def _precalentar_si_toca(self, w: _Worker) -> None:
        """Arranca el reemplazo en segundo plano cuando el worker actual se pasó del techo."""
        if self._precalentando or self._repuesto is not None or w.mem_mb < self._techo:
            return
        self._precalentando = True
        log.info("OCR: el worker va en %.0f MB (techo %.0f) — precalentando el reemplazo",
                 w.mem_mb, self._techo)

        def _tarea():
            try:
                nuevo = _levantar_worker()
            except Exception:
                log.exception("OCR: falló el precalentado del reemplazo; se sigue con el actual")
                nuevo = None
            with self._lock:
                self._repuesto = nuevo
                self._precalentando = False

        threading.Thread(target=_tarea, name="ocr-precalentado", daemon=True).start()

    def _degradar(self, motivo: str) -> None:
        if not self._degradado:
            log.critical("OCR: no se pudo usar el proceso aparte (%s) — se sigue EN PROCESO. "
                         "La memoria vuelve a crecer; el watchdog de RNF-06 queda como red.", motivo)
        self._degradado = True
        if self._activo is not None:
            self._activo.terminar()
            self._activo = None

    # ---- despacho ------------------------------------------------------------------------

    def _despachar(self, metodo: str, args: tuple, por_defecto):
        if en_proceso_forzado():
            return getattr(self._backend_local(), metodo)(*args)
        with self._lock:
            for intento in (1, 2):
                w = self._asegurar_activo()
                if w is None:
                    break
                try:
                    valor = w.llamar(metodo, args)
                except _ErrorDeLlamada as exc:
                    # El worker está sano; la llamada falló. Misma respuesta que daba el backend
                    # directo ante una excepción: el valor neutro, no una excepción hacia arriba.
                    log.debug("OCR: %s falló en el worker (%s)", metodo, exc)
                    return por_defecto
                except Exception as exc:
                    log.warning("OCR: el worker se cayó en %s (%s) — intento %d de 2",
                                metodo, exc, intento)
                    self._activo.terminar() if self._activo else None
                    self._activo = None
                    continue
                self._precalentar_si_toca(w)
                return valor
            self._degradar(f"dos fallos seguidos en {metodo}")
        return getattr(self._backend_local(), metodo)(*args)

    def cerrar(self) -> None:
        """Termina los workers. Idempotente."""
        with self._lock:
            for w in (self._activo, self._repuesto):
                if w is not None:
                    w.terminar()
            self._activo = self._repuesto = None

    # ---- la interfaz OcrBackend ----------------------------------------------------------

    @measure_latency("ocr_text")
    def text(self, img: np.ndarray, psm: int = 6, lang: str = "spa") -> tuple[str, float]:
        # La latencia se mide ACÁ y no en el worker: lo que RNF-06 presupuesta es lo que tarda
        # desde el punto de vista del llamador, ida y vuelta por el socket incluida.
        return self._despachar("text", (img, psm, lang), ("", 0.0))

    def number(self, img: np.ndarray) -> tuple[float, float]:
        return self._despachar("number", (img,), (0.0, 0.0))

    def text_with_bboxes(self, img: np.ndarray):
        return self._despachar("text_with_bboxes", (img,), [])


# --------------------------------------------------------------------------------------- #
# Registro del OCR compartido.
#
# Existe porque había DOS instancias de Paddle vivas en el proceso: la que arma el controller y la
# global `_s26_verify_ocr` del detector — que corre sobre toda pantalla que matchee el template de
# S17, o sea muchas más inferencias que el parser. Mudar sólo la primera dejaba la fuga casi
# intacta. Con el registro hay una sola autoridad sobre "cuál es el OCR de esta app" (regla B1).
# --------------------------------------------------------------------------------------- #

_compartido: OcrBackend | None = None


def set_shared_ocr(backend: OcrBackend | None) -> None:
    global _compartido
    _compartido = backend


def get_shared_ocr() -> OcrBackend | None:
    """El OCR de la app, o None si todavía no se inicializó (tests, scripts sueltos)."""
    return _compartido
