"""
Lista todas las ventanas visibles del sistema. Sirve para diagnosticar
por qué find_zzz_window() no encuentra el juego (típicamente porque el
título real difiere del que asumimos).

Uso:
    python tools/list_windows.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.core.capturer import find_zzz_window, list_all_visible_windows


def main():
    print("=" * 80)
    print("Ventanas visibles del sistema (con título no vacío):")
    print("=" * 80)
    windows = list_all_visible_windows()
    for hwnd, title in windows:
        marker = ""
        title_lower = title.lower()
        if "zenless" in title_lower or "zzz" in title_lower:
            marker = "  <-- POSIBLE ZZZ"
        print(f"  hwnd={hwnd:>10}  title={title!r}{marker}")

    print()
    print("=" * 80)
    print("Resultado de find_zzz_window():")
    print("=" * 80)
    w = find_zzz_window()
    if w is None:
        print("  NO se encontró la ventana de ZZZ.")
        print()
        print("  Si ZZZ está abierto, verificar que su título contiene 'Zenless' o 'ZZZ'.")
        print("  Si no, agregar el substring real al final de ZZZ_WINDOW_TITLE_CANDIDATES")
        print("  en app/core/capturer.py.")
    else:
        print(f"  OK: ventana encontrada")
        print(f"  title  = {w.title!r}")
        print(f"  pos    = ({w.left}, {w.top})")
        print(f"  size   = {w.width}x{w.height}")


if __name__ == "__main__":
    main()
