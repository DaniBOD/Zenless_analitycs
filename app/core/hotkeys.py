"""
Hotkeys globales (RNF-03: solo lectura, nunca enviamos teclas).

  F8  → captura manual (force_scan en Monitor)
  F9  → toggle panel principal
  F10 → toggle pause/resume monitor
  F11 → registrar run lategame (Fase 4)

Backend primario: **Win32 RegisterHotKey** (`pywin32`). Estos son hotkeys a
nivel sistema operativo — Windows enruta la combinación directo a nuestra
app **incluso si ZZZ está en pantalla completa con foco**. Es la API
correcta para overlays de juegos.

Fallback: `pynput.keyboard.Listener` (low-level keyboard hook). Funciona
en background general pero puede quedar bloqueado por algunos modos
fullscreen exclusive y por software antitrampa. Lo dejamos como Plan B.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable

log = logging.getLogger(__name__)

# Win32 virtual key codes (ver MSDN: Virtual-Key Codes)
_VK_CODES = {
    "f8":  0x77,
    "f9":  0x78,
    "f10": 0x79,
    "f11": 0x7A,
}

# Mapeo legible (para logs)
_KEY_NAMES = {
    "f8":  "captura_manual",
    "f9":  "toggle_panel",
    "f10": "toggle_pausa",
    "f11": "registrar_run",
}


class HotkeyManager:
    """
    Registra callbacks por hotkey global. Intenta Win32 RegisterHotKey primero,
    cae a pynput si pywin32 no está disponible. Las callbacks corren en el
    thread del listener — usar Qt signals si vas a tocar UI.
    """

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = {k: [] for k in _KEY_NAMES}
        self._lock = threading.Lock()
        # Backend activo (uno solo): win32 o pynput
        self._win32_thread: threading.Thread | None = None
        self._win32_stop: threading.Event | None = None
        self._pynput_listener = None

    def on(self, key_name: str, callback: Callable) -> None:
        """Registra callback para key_name (f8, f9, f10, f11)."""
        key_name = key_name.lower()
        if key_name not in self._handlers:
            raise ValueError(f"Hotkey desconocida: {key_name}. Válidas: {list(_KEY_NAMES)}")
        with self._lock:
            self._handlers[key_name].append(callback)

    def _fire(self, name: str) -> None:
        """Invoca callbacks registrados para `name` con manejo de excepciones."""
        with self._lock:
            callbacks = list(self._handlers[name])
        for cb in callbacks:
            try:
                cb()
            except Exception as exc:
                log.exception("Error en callback %s: %s", name, exc)

    def start(self) -> bool:
        """
        Arranca el backend de hotkeys. Devuelve True si alguno arrancó.
        Intenta Win32 primero (RegisterHotKey, robusto contra fullscreen),
        cae a pynput si pywin32 no está disponible.
        """
        if self._start_win32():
            log.info("HotkeyManager activo (Win32 RegisterHotKey): F8=captura F9=panel F10=pausa F11=run")
            return True
        if self._start_pynput():
            log.info("HotkeyManager activo (pynput fallback): F8=captura F9=panel F10=pausa F11=run")
            return True
        log.warning("HotkeyManager: ningún backend disponible. Hotkeys deshabilitados.")
        return False

    # ---- Backend 1: Win32 RegisterHotKey (preferido) ------------------------

    def _start_win32(self) -> bool:
        """
        Registra las hotkeys via Win32 API. Las combinaciones quedan
        registradas con el SO y se enrutan a la app sin importar el foco.
        """
        try:
            import win32con  # noqa: F401  — sólo testeo de import
        except ImportError:
            return False

        self._win32_stop = threading.Event()
        ready = threading.Event()
        startup_ok = [False]

        def _run():
            try:
                import ctypes
                from ctypes import wintypes

                user32 = ctypes.windll.user32

                WM_HOTKEY = 0x0312
                MOD_NOREPEAT = 0x4000  # no auto-repeat
                # Un id único por hotkey (1..N). Lo usamos también para mapear de vuelta.
                id_to_name: dict[int, str] = {}

                # Registrar TODAS las hotkeys que tienen callbacks
                with self._lock:
                    active_keys = [k for k, cbs in self._handlers.items() if cbs]
                for i, key_name in enumerate(active_keys, start=1):
                    vk = _VK_CODES[key_name]
                    if user32.RegisterHotKey(None, i, MOD_NOREPEAT, vk):
                        id_to_name[i] = key_name
                        log.debug("Win32 RegisterHotKey OK: id=%d %s (vk=0x%02x)", i, key_name, vk)
                    else:
                        err = ctypes.get_last_error()
                        log.warning("Win32 RegisterHotKey FAILED: %s (err=%d)", key_name, err)

                if not id_to_name:
                    return  # nada que escuchar

                startup_ok[0] = True
                ready.set()

                msg = wintypes.MSG()
                # Loop de mensajes — PeekMessage con timeout breve para chequear stop
                while not self._win32_stop.is_set():
                    # PM_REMOVE = 1 — extrae el mensaje de la cola si existe
                    has_msg = user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1)
                    if has_msg:
                        if msg.message == WM_HOTKEY:
                            hk_id = msg.wParam
                            name = id_to_name.get(hk_id)
                            if name:
                                log.debug("Win32 HOTKEY id=%d -> %s", hk_id, name)
                                self._fire(name)
                    else:
                        # Sin mensaje en cola, sleep corto para no bloquear CPU
                        self._win32_stop.wait(0.02)

                # Cleanup
                for hk_id in id_to_name:
                    user32.UnregisterHotKey(None, hk_id)
            except Exception:
                log.exception("Win32 hotkey loop falló")
            finally:
                ready.set()

        self._win32_thread = threading.Thread(target=_run, name="zzz-hotkey-win32", daemon=True)
        self._win32_thread.start()
        # Esperar a que se registre o falle (timeout corto)
        ready.wait(timeout=2.0)
        return startup_ok[0]

    # ---- Backend 2: pynput fallback -----------------------------------------

    def _start_pynput(self) -> bool:
        try:
            from pynput import keyboard
        except ImportError:
            return False

        def _on_press(key):
            try:
                name = key.name.lower() if hasattr(key, "name") else None
                if name and name in self._handlers:
                    log.debug("pynput hotkey: %s", name)
                    self._fire(name)
            except Exception:
                pass

        self._pynput_listener = keyboard.Listener(on_press=_on_press, daemon=True)
        self._pynput_listener.start()
        return True

    # ---- Stop --------------------------------------------------------------

    def stop(self) -> None:
        if self._win32_stop:
            self._win32_stop.set()
        if self._win32_thread and self._win32_thread.is_alive():
            self._win32_thread.join(timeout=2.0)
        if self._pynput_listener:
            try:
                self._pynput_listener.stop()
            except Exception:
                pass
            self._pynput_listener = None
        self._win32_thread = None
        self._win32_stop = None
