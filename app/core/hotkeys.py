"""
Hito 2.5.3-4 — Hotkeys globales vía pynput (lectura únicamente, RNF-03).
F8  → captura manual (force_scan en Monitor)
F9  → toggle panel principal
F10 → toggle pause/resume monitor
F11 → registrar run lategame (Fase 4)

Solo escucha teclas, nunca las envía (pynput.keyboard.Listener).
"""
from __future__ import annotations

import logging
import threading
from typing import Callable

log = logging.getLogger(__name__)

# Mapeo de tecla → nombre legible
_KEY_NAMES = {
    "f8":  "captura_manual",
    "f9":  "toggle_panel",
    "f10": "toggle_pausa",
    "f11": "registrar_run",
}


class HotkeyManager:
    """
    Registra callbacks por hotkey y arranca un listener global en thread daemon.
    Las callbacks se ejecutan en el thread del listener — usar señales Qt
    si necesitás actualizar UI desde ellas.
    """

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = {k: [] for k in _KEY_NAMES}
        self._listener: "pynput.keyboard.Listener | None" = None
        self._lock = threading.Lock()

    def on(self, key_name: str, callback: Callable) -> None:
        """Registra callback para key_name (f8, f9, f10, f11)."""
        key_name = key_name.lower()
        if key_name not in self._handlers:
            raise ValueError(f"Hotkey desconocida: {key_name}. Válidas: {list(_KEY_NAMES)}")
        with self._lock:
            self._handlers[key_name].append(callback)

    def start(self) -> bool:
        """Arranca el listener. Devuelve False si pynput no está instalado."""
        try:
            from pynput import keyboard

            def _on_press(key):
                try:
                    name = key.name.lower() if hasattr(key, "name") else None
                    if name and name in self._handlers:
                        log.debug("Hotkey: %s", name)
                        with self._lock:
                            callbacks = list(self._handlers[name])
                        for cb in callbacks:
                            try:
                                cb()
                            except Exception as exc:
                                log.exception("Error en callback %s: %s", name, exc)
                except Exception:
                    pass

            self._listener = keyboard.Listener(on_press=_on_press, daemon=True)
            self._listener.start()
            log.info("HotkeyManager activo: F8=captura F9=panel F10=pausa F11=run")
            return True
        except ImportError:
            log.warning("pynput no instalado — hotkeys deshabilitados.")
            return False

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None
