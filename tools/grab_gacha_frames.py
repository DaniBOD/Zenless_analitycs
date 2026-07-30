"""Cosecha de frames del flujo de gacha, ARMADA POR DETECCIÓN (sin hotkey).

Por qué existe: las tiradas son limitadas y no se pueden repetir QAs contra esta pantalla. Si
el parser falla en vivo, sin los frames crudos la tirada se perdió. Con ellos, se arregla
offline y no cuesta nada.

Cómo funciona:
  - El loop de captura SOLO captura. Mete el frame crudo en una cola y sigue.
  - 2-3 threads escritores drenan la cola a PNG. Medido sobre un frame real de 2559×1439:
    `cv2.imwrite` PNG nivel 3 (default) tarda 252 ms y nivel 1 tarda 203 ms — o sea que
    encodear EN LÍNEA es más lento que el propio intervalo de captura y abre huecos. Como
    `imencode` suelta el GIL, los threads escalan de verdad.
  - Un hilo aparte MUESTREA la cola (1 de cada N frames) y clasifica para armar/desarmar. Nunca
    dentro del loop de captura: si la clasificación se demora, se pierde un muestreo, no un
    frame.
  - Arranca al ver S27 (el banner) y corta después de salir de S28 (la grilla). Entre medio
    pasa la animación, que el detector reporta como S12 — eso es esperado y NO desarma.

Sin dedupe a propósito: el dedupe decide TIRAR frames, que es justo lo que no queremos en un
evento irrepetible. ~10 fps × 2,5 MB ≈ 1,5 GB por pasada de un minuto. Es barato.

Solo lee píxeles: `mss` para capturar, `win32` para ubicar la ventana. No envía inputs, no lee
memoria, no escucha el teclado (RNF-03). NO toca la DB.

Uso:
    .venv\\Scripts\\python tools\\grab_gacha_frames.py
    .venv\\Scripts\\python tools\\grab_gacha_frames.py --seconds 600 --always
"""
from __future__ import annotations

import argparse
import queue
import sys
import threading
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.capturer import capture_window, find_zzz_window  # noqa: E402
from app.core.detector import ScreenDetector  # noqa: E402

# Estados que arman y que sostienen la cosecha. S12 sostiene porque la animación de recolección
# cae ahí: desarmar en S12 cortaría justo en el medio de la tirada.
_ARM_STATES = {"S27"}
_HOLD_STATES = {"S27", "S28", "S12"}

# Frames consecutivos fuera de `_HOLD_STATES` antes de desarmar. Con margen: se prefiere grabar
# de más antes que cortar antes de tiempo.
_DISARM_AFTER = 8

_STOP = object()


def _writer(q: "queue.Queue", destino: Path, compress: int, stats: dict, lock: threading.Lock):
    while True:
        item = q.get()
        if item is _STOP:
            q.task_done()
            return
        n, ts, frame = item
        nombre = f"{n:05d}_{ts}.png"
        try:
            cv2.imwrite(str(destino / nombre), frame, [cv2.IMWRITE_PNG_COMPRESSION, compress])
            with lock:
                stats["escritos"] += 1
        except Exception as exc:                                # pragma: no cover
            with lock:
                stats["errores"] += 1
            print(f"  !! error escribiendo {nombre}: {exc}")
        finally:
            q.task_done()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=900.0,
                    help="tope duro de la sesión de vigilancia")
    ap.add_argument("--interval", type=float, default=0.10, help="período de captura")
    ap.add_argument("--out", default="audit/frames_gacha")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--compress", type=int, default=1,
                    help="nivel PNG 0-9 (1 = rápido, 2,5 MB/frame)")
    ap.add_argument("--sample-every", type=int, default=8,
                    help="clasificar 1 de cada N frames para armar/desarmar")
    ap.add_argument("--max-frames", type=int, default=4000, help="tope duro de frames")
    ap.add_argument("--always", action="store_true",
                    help="grabar sin esperar el armado por S27")
    args = ap.parse_args()

    destino = Path(args.out)
    destino.mkdir(parents=True, exist_ok=True)

    ventana = find_zzz_window()
    if ventana is None:
        print("[gacha] no encuentro la ventana de ZZZ — abrí el juego primero")
        return 1
    print(f"[gacha] ventana: '{ventana.title}' ({ventana.width}x{ventana.height})")

    det = ScreenDetector(use_state_machine=False)
    print(f"[gacha] {det.loaded_count} templates cargados")
    print(f"[gacha] destino: {destino.resolve()}")
    print("[gacha] esperando el banner (S27)…" if not args.always else "[gacha] modo --always")
    print("[gacha] Ctrl-C para cortar\n")

    q: "queue.Queue" = queue.Queue(maxsize=240)
    stats = {"escritos": 0, "errores": 0, "descartados": 0}
    lock = threading.Lock()
    hilos = [threading.Thread(target=_writer, args=(q, destino, args.compress, stats, lock),
                              daemon=True) for _ in range(max(1, args.workers))]
    for h in hilos:
        h.start()

    armado = bool(args.always)
    fuera = 0
    n = 0
    i = 0
    fin = time.time() + args.seconds
    t0 = time.time()

    try:
        while time.time() < fin and n < args.max_frames:
            frame = capture_window(ventana)
            if frame is None:
                time.sleep(args.interval)
                continue
            i += 1

            # Clasificación de armado: muestreada, y fuera del camino de escritura.
            if i % max(1, args.sample_every) == 0:
                st = det.classify(frame)
                if not args.always:
                    if st.code in _ARM_STATES and not armado:
                        armado = True
                        fuera = 0
                        print(f"  ARMADO por {st.code} (conf={st.confidence:.3f})")
                    elif armado:
                        if st.code in _HOLD_STATES:
                            fuera = 0
                        else:
                            fuera += 1
                            if fuera >= _DISARM_AFTER:
                                armado = False
                                print(f"  desarmado tras {fuera} muestras fuera del flujo "
                                      f"(último: {st.code})")
                if armado and i % (max(1, args.sample_every) * 10) == 0:
                    print(f"  [{n:05d}] {st.code} conf={st.confidence:.3f} "
                          f"cola={q.qsize()} escritos={stats['escritos']}")

            if armado:
                n += 1
                try:
                    q.put_nowait((n, time.strftime("%H%M%S") + f"_{int(time.time()*1000)%1000:03d}",
                                  frame))
                except queue.Full:
                    with lock:
                        stats["descartados"] += 1
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[gacha] cortado a mano")

    print("\n[gacha] vaciando la cola…")
    q.join()
    for _ in hilos:
        q.put(_STOP)
    q.join()

    dur = time.time() - t0
    print(f"[gacha] {stats['escritos']} frames escritos en {dur:.0f}s "
          f"({stats['escritos']/max(1e-6, dur):.1f} fps) · "
          f"descartados por cola llena: {stats['descartados']} · errores: {stats['errores']}")
    print(f"[gacha] {destino.resolve()}")
    if stats["descartados"]:
        print("  ⚠️  hubo descartes: subí --workers o bajá --compress")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
