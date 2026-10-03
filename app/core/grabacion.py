"""Grabación de una sesión de juego: frames + clicks con su hora (hito "El ritmo de Daniel").

Para medir cada cambio del loop contra la MISMA sesión, sin que Daniel tenga que volver a jugar
(DIAG 2026-10-02, plan aprobado). Una sesión grabada "a su ritmo" es el banco de pruebas: la
verdad de tierra sale de recorrerla sin apuro (`tools/verdad_de_sesion.py`) y lo que la app
alcanza a ver, de reproducirla en tiempo real contra el monitor (`tools/reproducir_sesion.py`).

Formato de una carpeta de grabación:
  - `NNNNNN.png`   frames completos (PNG nivel 3: ~2,1 MB y ~275 ms por frame, medido);
  - `eventos.jsonl` una línea por evento, en orden de llegada:
      {"tipo": "inicio", "t": …, "wall": "…", "ventana": [w, h], "fps": …}
      {"tipo": "frame",  "t": …, "n": N, "motivo": "cambio" | "click" | "latido"}
      {"tipo": "click",  "t": …, "x": 0-1, "y": 0-1, "boton": "left"}
      {"tipo": "descartados", "t": …, "n": K}   (el escritor no dio abasto)
      {"tipo": "fin", "t": …}
    `t` es `time.monotonic()`: el mismo reloj del loop del monitor y de los clicks.

Las grabaciones son de pantalla completa → quedan LOCALES (`%LOCALAPPDATA%`), nunca en el repo
(feedback "capturas full-res: locales"). Read-only: no toca la DB ni envía inputs (RNF-03).
"""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np

log = logging.getLogger(__name__)

# Diferencia media (0-255) de la huella 96×54 a partir de la cual un frame es "otro". Un click en
# S11 cambia el panel DETAIL entero; una tilde sola casi no mueve la huella, por eso además están
# los frames por click y el latido.
UMBRAL_CAMBIO = 1.5
# Espera entre el click y su frame: lo que tarda el juego en mostrar la respuesta (a medir con la
# propia grabación; arranca en 150 ms).
TRAS_CLICK_S = 0.15
# Un frame cada tanto aunque no cambie nada: la verdad de tierra necesita saber que la pantalla
# SIGUIÓ igual (p. ej. cuánto duró un modal).
LATIDO_S = 1.0


def huella(frame: np.ndarray) -> np.ndarray:
    """Miniatura gris 96×54 para comparar frames sin costo (la de `grab_desmontaje_frames`)."""
    import cv2
    chico = cv2.resize(frame, (96, 54), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(chico, cv2.COLOR_BGR2GRAY).astype(np.float32)


@dataclass
class Grabador:
    """Decide qué frames guardar y los escribe en hilos aparte.

    `capturar()` devuelve un frame BGR o None (juego sin foco / sin ventana). `clicks` es un
    `ClickListener` (o algo con `desde(t)`). Todo inyectable: los tests no tocan pantalla ni mouse."""
    destino: Path
    capturar: Callable[[], np.ndarray | None]
    clicks: object | None = None
    reloj: Callable[[], float] = time.monotonic
    umbral: float = UMBRAL_CAMBIO
    tras_click: float = TRAS_CLICK_S
    latido: float = LATIDO_S
    escritores: int = 4
    max_cola: int = 24
    codificar: Callable[[Path, np.ndarray], None] | None = None

    _n: int = field(default=0, init=False)
    _previa: np.ndarray | None = field(default=None, init=False)
    _t_guardado: float = field(default=float("-inf"), init=False)
    _t_click_visto: float = field(default=float("-inf"), init=False)
    _clicks_pendientes: list = field(default_factory=list, init=False)
    _descartados: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.destino = Path(self.destino)
        self.destino.mkdir(parents=True, exist_ok=True)
        self._cola: queue.Queue = queue.Queue(maxsize=self.max_cola)
        self._jsonl = open(self.destino / "eventos.jsonl", "a", encoding="utf-8")
        self._lock_jsonl = threading.Lock()
        self._hilos = [threading.Thread(target=self._escribir, daemon=True)
                       for _ in range(max(1, self.escritores))]
        for h in self._hilos:
            h.start()

    # --- eventos ----------------------------------------------------------------------------
    def evento(self, **datos) -> None:
        with self._lock_jsonl:
            self._jsonl.write(json.dumps(datos, ensure_ascii=False) + "\n")
            self._jsonl.flush()

    def iniciar(self, ventana: tuple[int, int] | None = None, fps: float | None = None) -> None:
        self.evento(tipo="inicio", t=self.reloj(), wall=datetime.now().isoformat(timespec="seconds"),
                    ventana=list(ventana) if ventana else None, fps=fps)

    # --- un paso del loop de captura -----------------------------------------------------------
    def paso(self) -> str | None:
        """Captura una vez y decide. Devuelve el motivo si el frame se guardó, o None."""
        ahora = self.reloj()
        if self.clicks is not None:
            for c in self.clicks.desde(self._t_click_visto):
                self._t_click_visto = c.t
                self.evento(tipo="click", t=c.t, x=c.x, y=c.y, boton=c.boton)
                self._clicks_pendientes.append(c.t)
        frame = self.capturar()
        if frame is None:
            return None
        motivo = None
        vencidos = [t for t in self._clicks_pendientes if ahora >= t + self.tras_click]
        if vencidos:
            self._clicks_pendientes = [t for t in self._clicks_pendientes if t not in vencidos]
            motivo = "click"
        h = huella(frame)
        if motivo is None and (self._previa is None
                               or float(np.abs(h - self._previa).mean()) > self.umbral):
            motivo = "cambio"
        if motivo is None and ahora - self._t_guardado >= self.latido:
            motivo = "latido"
        if motivo is None:
            return None
        self._previa = h
        self._t_guardado = ahora
        self._n += 1
        try:
            self._cola.put_nowait((self._n, ahora, motivo, frame))
        except queue.Full:
            self._descartados += 1
            self.evento(tipo="descartados", t=ahora, n=self._descartados)
            return None
        return motivo

    def correr(self, segundos: float, fps: float = 8.0, dormir=time.sleep,
               seguir: Callable[[], bool] = lambda: True) -> None:
        """`seguir()` False corta antes (el CLI lo ata a un archivo: un proceso elevado no se puede
        cortar con Ctrl-C desde otra consola)."""
        fin = self.reloj() + segundos
        periodo = 1.0 / fps
        while self.reloj() < fin and seguir():
            t0 = self.reloj()
            self.paso()
            espera = periodo - (self.reloj() - t0)
            if espera > 0:
                dormir(espera)

    def cerrar(self) -> int:
        """Espera a que se escriba todo. Devuelve los frames descartados."""
        for _ in self._hilos:
            self._cola.put(None)
        for h in self._hilos:
            h.join()
        self.evento(tipo="fin", t=self.reloj())
        self._jsonl.close()
        return self._descartados

    # --- escritura (hilos) ---------------------------------------------------------------------
    def _escribir(self) -> None:
        while True:
            item = self._cola.get()
            if item is None:
                return
            n, t, motivo, frame = item
            ruta = self.destino / f"{n:06d}.png"
            try:
                (self.codificar or _png)(ruta, frame)
                self.evento(tipo="frame", t=t, n=n, motivo=motivo)
            except Exception:
                log.exception("[grabación] no se pudo escribir el frame %d", n)


def _png(ruta: Path, frame: np.ndarray) -> None:
    import cv2
    ok, buf = cv2.imencode(".png", frame, [cv2.IMWRITE_PNG_COMPRESSION, 3])
    if not ok:
        raise OSError(f"imencode falló para {ruta}")
    buf.tofile(str(ruta))


# --- lectura ------------------------------------------------------------------------------------
@dataclass
class FrameGrabado:
    t: float
    n: int
    motivo: str
    ruta: Path

    def cargar(self) -> np.ndarray:
        import cv2
        return cv2.imdecode(np.fromfile(str(self.ruta), np.uint8), cv2.IMREAD_COLOR)


@dataclass
class Grabacion:
    carpeta: Path
    inicio: dict
    frames: list[FrameGrabado]          # ordenados por t
    clicks: list[dict]                  # ordenados por t
    descartados: int

    def __post_init__(self) -> None:
        self.ts = [f.t for f in self.frames]   # para `frame_vigente` (bisect), sin recalcular


def leer_grabacion(carpeta: Path | str) -> Grabacion:
    carpeta = Path(carpeta)
    inicio: dict = {}
    frames: list[FrameGrabado] = []
    clicks: list[dict] = []
    descartados = 0
    for linea in (carpeta / "eventos.jsonl").read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        ev = json.loads(linea)
        tipo = ev.get("tipo")
        if tipo == "inicio":
            inicio = ev
        elif tipo == "frame":
            frames.append(FrameGrabado(ev["t"], ev["n"], ev["motivo"], carpeta / f"{ev['n']:06d}.png"))
        elif tipo == "click":
            clicks.append(ev)
        elif tipo == "descartados":
            descartados = max(descartados, ev["n"])
    # Los clicks también pueden venir del ayudante elevado (`tools/clicks_elevado.py`), en su
    # propio archivo: ZZZ corre como administrador y un proceso sin elevar no ve su mouse.
    aparte = carpeta / "clicks.jsonl"
    if aparte.exists():
        vistos = {(c["t"], c["x"], c["y"]) for c in clicks}
        for linea in aparte.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                ev = json.loads(linea)
                if ev.get("tipo") == "click" and (ev["t"], ev["x"], ev["y"]) not in vistos:
                    clicks.append(ev)
    frames.sort(key=lambda f: f.t)
    clicks.sort(key=lambda c: c["t"])
    return Grabacion(carpeta, inicio, frames, clicks, descartados)


def frame_vigente(grabacion: Grabacion, t: float) -> FrameGrabado | None:
    """El último frame grabado con `t` ≤ al instante pedido: lo que estaba en pantalla entonces."""
    import bisect
    i = bisect.bisect_right(grabacion.ts, t) - 1
    return grabacion.frames[i] if i >= 0 else None
