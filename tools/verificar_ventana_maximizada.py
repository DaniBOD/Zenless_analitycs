"""Verificación MANUAL de la ventana frameless maximizada (Windows). No es un test de pytest.

La lógica nativa de `app/ui/shell/window.py` (WM_NCCALCSIZE) no se puede ejercitar offscreen, así que
esto es lo que la ejercita: abre una ventana de prueba, la maximiza por los dos caminos (botón de Qt y
maximizado nativo de Windows) y compara el área cliente contra el área de trabajo del monitor.

Correr después de tocar el marco nativo, con la app cerrada y sin nada importante en pantalla:

    set PYTHONIOENCODING=utf-8
    .venv\Scripts\python.exe tools\verificar_ventana_maximizada.py

Existe por el bug del 2026-09-13: el recorte se condicionaba al estado de Qt y no al de Windows.
Con esa condición FALLA en los dos caminos; con `IsZoomed` pasa. Salida esperada: "TODO PASA".
"""
import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
ctypes.windll.shcore.SetProcessDpiAwareness(2)

from PySide6.QtCore import QTimer                    # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel   # noqa: E402

from app.ui.shell.window import ShellWindow          # noqa: E402

app = QApplication(sys.argv)
w = ShellWindow("verif", install_native_frame=True)
w.add_view("live", QLabel("verificación"))
w.resize(1320, 820)
w.move(200, 150)
w.show()
u = ctypes.windll.user32
resultados = []


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


def medir():
    hwnd = int(w.winId())
    cr = wintypes.RECT()
    u.GetClientRect(hwnd, ctypes.byref(cr))
    p = wintypes.POINT(0, 0)
    u.ClientToScreen(hwnd, ctypes.byref(p))
    mi = MONITORINFO(); mi.cbSize = ctypes.sizeof(MONITORINFO)
    u.GetMonitorInfoW(u.MonitorFromWindow(hwnd, 2), ctypes.byref(mi))
    wk = mi.rcWork
    return {
        "zoomed": bool(u.IsZoomed(hwnd)),
        "cliente": (p.x, p.y, cr.right, cr.bottom),
        "trabajo": (wk.left, wk.top, wk.right - wk.left, wk.bottom - wk.top),
        "qt": (w.width(), w.height()),
    }


def chequear(nombre, m, maximizada):
    cx, cy, cw, ch = m["cliente"]
    if maximizada:
        ok = m["cliente"] == m["trabajo"] and (cw, ch) == m["qt"]
    else:
        ok = (cw, ch) == m["qt"] == (1320, 820)
    resultados.append(ok)
    print(f"{'PASA ' if ok else 'FALLA'} · {nombre:34} zoomed={m['zoomed']!s:5} cliente={m['cliente']} "
          f"trabajo={m['trabajo']} qt={m['qt']}")


pasos = []


def encolar(accion, espera, verificacion=None):
    pasos.append((accion, espera, verificacion))


encolar(lambda: None, 800, lambda: chequear("inicial (normal)", medir(), False))
encolar(w.showMaximized, 1200, lambda: chequear("A · botón □ (Qt showMaximized)", medir(), True))
encolar(w.showNormal, 1000, lambda: chequear("A · restaurada", medir(), False))
encolar(lambda: u.ShowWindow(int(w.winId()), 3), 1200,
        lambda: chequear("B · nativo (SW_MAXIMIZE)", medir(), True))
encolar(lambda: u.ShowWindow(int(w.winId()), 9), 1000,
        lambda: chequear("B · restaurada (SW_RESTORE)", medir(), False))


def correr(i=0):
    if i >= len(pasos):
        print("TODO PASA" if all(resultados) else "HAY FALLAS")
        app.quit()
        return
    accion, espera, verif = pasos[i]
    accion()

    def despues():
        if verif:
            verif()
        correr(i + 1)
    QTimer.singleShot(espera, despues)


QTimer.singleShot(300, correr)
app.exec()
