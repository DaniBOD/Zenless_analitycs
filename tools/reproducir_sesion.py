"""Reproduce una grabación contra la app real y mide cuánto se pierde a su ritmo.

La grabación (`tools/grabar_sesion.py`) hace de pantalla: `Monitor._get_frame` devuelve, en cada
vuelta del loop, el frame que estaba en pantalla en ese instante de la sesión, con el reloj de
pared corriendo a velocidad real. Todo lo demás es la app de verdad —controlador, monitor, OCR en
su proceso, persistencia— con su costo real, así que pierde lo mismo que perdería en vivo.

Aislado de todo lo de Daniel:
  - DB: una COPIA en `<grabación>/repro_<etiqueta>/dominio.db` (`DANIBOD_DB_PATH`); las métricas
    quedan al lado (`metrics.db`) y las bitácoras en `audit/` adentro (`DANIBOD_AUDIT_DIR`);
  - log: `<grabación>/repro_<etiqueta>/reproduccion.log`, no el `app.log`;
  - Qt sin ventana (`QT_QPA_PLATFORM=offscreen`).

Al terminar cruza el log con `verdad.json` (de `tools/verdad_de_sesion.py`) y deja el reporte en
`audit/ritmo/<grabación>_<etiqueta>.md`.

Uso:
    .venv\\Scripts\\python tools\\reproducir_sesion.py <carpeta_de_grabacion> [--etiqueta base]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# La cola del final: segundos que se deja correr la app después del último frame (lo que quedó
# en proceso tiene que terminar de loguearse).
_COLA_S = 4.0
# Cuánto por delante precarga el hilo de decodificación (un PNG de 2560×1440 tarda ~50 ms).
_PRECARGA_S = 1.0


def _etiqueta_git() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                                       text=True).strip()
    except Exception:
        return "sin_git"


class _Pantalla:
    """La grabación como pantalla virtual: el frame vigente según el reloj, con precarga."""

    def __init__(self, rec, frame_vigente):
        self._rec = rec
        self._vigente = frame_vigente
        self._base = rec.frames[0].t
        self._fin = rec.frames[-1].t
        self._t0: float | None = None
        self._cache: dict[int, object] = {}
        self._lock = threading.Lock()
        self.terminada = False
        threading.Thread(target=self._precargar, daemon=True).start()

    def t_grabacion(self) -> float:
        if self._t0 is None:
            self._t0 = time.monotonic()
        return self._base + (time.monotonic() - self._t0)

    def frame(self):
        t = self.t_grabacion()
        if t > self._fin + _COLA_S:
            self.terminada = True
        f = self._vigente(self._rec, t)
        if f is None:
            return None
        with self._lock:
            img = self._cache.get(f.n)
        if img is None:
            img = f.cargar()
            with self._lock:
                self._cache[f.n] = img
        return img

    def _precargar(self) -> None:
        while not self.terminada:
            if self._t0 is None:
                time.sleep(0.05)
                continue
            t = self.t_grabacion()
            proximos = [f for f in self._rec.frames if t - 0.5 <= f.t <= t + _PRECARGA_S]
            vivos = {f.n for f in proximos}
            for f in proximos:
                with self._lock:
                    ya = f.n in self._cache
                if not ya:
                    img = f.cargar()
                    with self._lock:
                        self._cache[f.n] = img
            with self._lock:
                for n in [n for n in self._cache if n not in vivos]:
                    del self._cache[n]
            time.sleep(0.02)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("carpeta")
    ap.add_argument("--etiqueta", default=None, help="por defecto, el commit actual")
    args = ap.parse_args()

    carpeta = Path(args.carpeta)
    etiqueta = args.etiqueta or _etiqueta_git()
    trabajo = carpeta / f"repro_{etiqueta}"
    if trabajo.exists():
        shutil.rmtree(trabajo)
    trabajo.mkdir(parents=True)
    shutil.copy2(REPO / "db" / "danibod_zzz_v2.db", trabajo / "dominio.db")

    os.environ["DANIBOD_DB_PATH"] = str(trabajo / "dominio.db")
    # Las bitácoras de desmontaje (y todo lo que va a `audit/`) también, o la reproducción le
    # escribe al repo real (pasó en la primera prueba, 2026-10-02).
    os.environ["DANIBOD_AUDIT_DIR"] = str(trabajo / "audit")
    os.environ["DANIBOD_METRICS"] = "1"
    os.environ["DANIBOD_NO_RAM_GUARD"] = "1"
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    log_file = trabajo / "reproduccion.log"
    logging.basicConfig(level=logging.INFO, handlers=[logging.FileHandler(log_file, encoding="utf-8")],
                        format="%(asctime)s %(levelname)-8s %(name)s :: %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S")
    # Como en `app/main.py`: `import paddleocr` sube el root a WARNING y callaría todo; el nivel
    # del logger "app" lo hace inmune.
    logging.getLogger("app").setLevel(logging.INFO)

    from app.core.grabacion import frame_vigente, leer_grabacion
    from app.core.monitor import Monitor
    from app.core.ritmo import Verdad, comparar, eventos_de_verdad, kpis_de_log, reporte_md, ObsFrame

    rec = leer_grabacion(carpeta)
    if not rec.frames:
        print("[repro] la grabación no tiene frames")
        return 1
    pantalla = _Pantalla(rec, frame_vigente)
    Monitor._get_frame = lambda self: pantalla.frame()          # la grabación es la pantalla

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from app.ui.controller import MonitorController
    app = QApplication([])
    ctrl = MonitorController()

    def _vigilar():
        if pantalla.terminada:
            ctrl.stop()
            app.quit()

    reloj = QTimer()
    reloj.timeout.connect(_vigilar)
    reloj.start(250)
    QTimer.singleShot(0, ctrl.start)
    dur = rec.frames[-1].t - rec.frames[0].t
    print(f"[repro] {len(rec.frames)} frames · {dur:.0f} s de sesión · etiqueta {etiqueta}")
    app.exec()

    lineas = log_file.read_text(encoding="utf-8").splitlines()
    k = kpis_de_log(lineas)
    verdad_json = carpeta / "verdad.json"
    if verdad_json.exists():
        datos = json.loads(verdad_json.read_text(encoding="utf-8"))
        v = eventos_de_verdad([ObsFrame(**o) for o in datos["frames"]])
    else:
        print("[repro] sin verdad.json — corré antes tools/verdad_de_sesion.py; reporto sólo la app")
        v = Verdad()

    extra = []
    try:
        import sqlite3
        con = sqlite3.connect(str(trabajo / "metrics.db"))
        for sup in ("loop_period", "detector", "capturer"):
            ms = sorted(r[0] for r in con.execute(
                "select duration_ms from metrics_latency where superficie=?", (sup,)))
            if ms:
                extra.append(f"- `{sup}`: n={len(ms)} · p50 {statistics.median(ms):.0f} ms · "
                             f"p90 {ms[int(len(ms) * 0.9)]:.0f} ms")
        con.close()
    except Exception as exc:
        extra.append(f"- métricas no disponibles ({exc})")
    extra.append(f"- S11 según la app: {k.s11_declarados} declarados · {k.s11_con_datos} con datos · "
                 f"{k.s11_sin_datos} sin")
    extra.append(f"- frames grabados {len(rec.frames)} · descartados al grabar {rec.descartados}")

    destino = REPO / "audit" / "ritmo" / f"{carpeta.name}_{etiqueta}.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(reporte_md(f"Ritmo · {carpeta.name} · {etiqueta}", comparar(v, k), extra),
                       encoding="utf-8")
    print(destino.read_text(encoding="utf-8"))
    print(f"[repro] → {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
