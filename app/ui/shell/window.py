"""La ventana principal: frameless por fuera, ventana de Windows por dentro.

Decisión de Daniel (2026-09-12): barra de título propia, fiel al mockup. Se le advirtió el costo
—el frameless "a mano" obliga a reimplementar arrastre, resize por 8 zonas, snap y multi-monitor,
y es el lugar clásico donde una UI de Qt se llena de bugs— y lo eligió igual.

Por eso NO se reimplementa nada de eso. El camino es el sólido:

1. `FramelessWindowHint` para que Qt no dibuje el marco...
2. ...pero se le DEVUELVEN a la ventana los estilos nativos `WS_THICKFRAME | WS_CAPTION`, así Windows
   la sigue tratando como una ventana normal: snap, Aero Snap layouts, `Win+flechas`, sombra y
   animaciones de minimizar son de Windows.
3. `WM_NCCALCSIZE` devuelve 0: el área cliente ocupa la ventana entera y el marco no se dibuja.
4. `WM_NCHITTEST` le dice a Windows qué punto es borde de resize, qué es "caption" (arrastre) y qué
   es contenido. **Esa decisión es una función pura (`hit_test`) con tests**; lo único que queda sin
   test automático es el cableado con la API de Windows, y ese se prueba a mano.

Fuera de Windows, o con `install_native_frame=False` (los tests), es un frameless simple.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from app.ui import tokens as T
from app.ui.shell.sidebar import Sidebar
from app.ui.shell.statusbar import StatusBar
from app.ui.shell.titlebar import TitleBar

# Códigos de WM_NCHITTEST (winuser.h)
HTCLIENT, HTCAPTION = 1, 2
HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT = 10, 11, 12, 13, 14
HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 15, 16, 17

#: Grosor de la zona de resize, en px lógicos. 6 es lo que usa Windows 11 para ventanas sin marco.
RESIZE_BORDER = 6


def hit_test(x: int, y: int, w: int, h: int, *, border: int, maximized: bool,
             en_caption: bool) -> int:
    """Qué es el punto (x, y) de una ventana de w×h, en coordenadas locales.

    - Maximizada no hay bordes de resize (Windows tampoco los ofrece).
    - Las esquinas ganan a los lados: si no, agarrar la esquina redimensiona en un solo eje.
    - `en_caption` lo decide la barra de título (todo menos sus botones).
    """
    if not maximized and border > 0:
        izq, der = x < border, x >= w - border
        arr, aba = y < border, y >= h - border
        if arr and izq:
            return HTTOPLEFT
        if arr and der:
            return HTTOPRIGHT
        if aba and izq:
            return HTBOTTOMLEFT
        if aba and der:
            return HTBOTTOMRIGHT
        if izq:
            return HTLEFT
        if der:
            return HTRIGHT
        if arr:
            return HTTOP
        if aba:
            return HTBOTTOM
    return HTCAPTION if en_caption else HTCLIENT


class ShellWindow(QMainWindow):
    """Titlebar + (sidebar | stack de vistas) + statusbar. No sabe qué hay en las vistas."""

    def __init__(self, version: str = "", *, db_path=None, readonly: bool = False,
                 install_native_frame: bool = True, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumSize(1320, 820)
        self._native = install_native_frame and sys.platform == "win32"
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinMaxButtonsHint
        )
        self._views: dict[str, QWidget] = {}

        central = QWidget()
        central.setObjectName("shell")
        central.setStyleSheet(f"QWidget#shell {{ background: {T.BG_BASE}; }}")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.titlebar = TitleBar(version)
        self.sidebar = Sidebar()
        self.stack = QStackedWidget()
        self.statusbar_widget = StatusBar(db_path=db_path, readonly=readonly)

        cuerpo = QHBoxLayout()
        cuerpo.setContentsMargins(0, 0, 0, 0)
        cuerpo.setSpacing(0)
        cuerpo.addWidget(self.sidebar)
        cuerpo.addWidget(self.stack, 1)

        root.addWidget(self.titlebar)
        root.addLayout(cuerpo, 1)
        root.addWidget(self.statusbar_widget)

        self.sidebar.item_selected.connect(self._on_item)
        self.titlebar.minimize_requested.connect(self.showMinimized)
        self.titlebar.maximize_toggle_requested.connect(self._toggle_max)
        self.titlebar.close_requested.connect(self.close)

        if self._native:
            self._instalar_marco_nativo()

    # --- vistas -------------------------------------------------------------------------------

    def add_view(self, clave: str, widget: QWidget) -> None:
        self._views[clave] = widget
        self.stack.addWidget(widget)
        if clave == self.sidebar.active_key():
            self.stack.setCurrentWidget(widget)

    def _on_item(self, clave: str) -> None:
        w = self._views.get(clave)
        if w is not None:
            self.stack.setCurrentWidget(w)

    def current_view(self) -> QWidget | None:
        return self.stack.currentWidget()

    def show_view(self, clave: str) -> None:
        self.sidebar.select(clave)

    def _toggle_max(self) -> None:
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def mouseDoubleClickEvent(self, ev):
        """Sin marco nativo (tests / no-Windows) el doble clic en la barra maximiza a mano. Con
        marco nativo lo hace Windows, porque la barra es HTCAPTION."""
        if not self._native:
            pos = self.titlebar.mapFrom(self, ev.position().toPoint())
            if self.titlebar.rect().contains(pos) and self.titlebar.is_drag_area(pos):
                self._toggle_max()
                return
        super().mouseDoubleClickEvent(ev)

    # --- Windows ------------------------------------------------------------------------------

    def _instalar_marco_nativo(self) -> None:
        import ctypes

        user32 = ctypes.windll.user32
        GWL_STYLE = -16
        WS_THICKFRAME, WS_CAPTION = 0x00040000, 0x00C00000
        WS_MAXIMIZEBOX, WS_MINIMIZEBOX = 0x00010000, 0x00020000
        hwnd = int(self.winId())
        estilo = user32.GetWindowLongW(hwnd, GWL_STYLE)
        user32.SetWindowLongW(hwnd, GWL_STYLE,
                              estilo | WS_THICKFRAME | WS_CAPTION | WS_MAXIMIZEBOX | WS_MINIMIZEBOX)

        class MARGINS(ctypes.Structure):
            _fields_ = [("l", ctypes.c_int), ("r", ctypes.c_int),
                        ("t", ctypes.c_int), ("b", ctypes.c_int)]
        try:
            # 1 px de "vidrio" alcanza para que DWM vuelva a dibujar la sombra de la ventana.
            ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(MARGINS(1, 1, 1, 1)))
        except OSError:
            pass
        SWP = 0x0002 | 0x0001 | 0x0004 | 0x0020      # NOMOVE | NOSIZE | NOZORDER | FRAMECHANGED
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, SWP)

    def nativeEvent(self, event_type, message):
        # `event_type` llega como QByteArray: se normaliza a bytes. Si la comparación diera siempre
        # "distinto", el marco nativo no haría nada y en silencio — la ventana no se dejaría ni
        # arrastrar ni redimensionar.
        if not self._native or bytes(event_type) != b"windows_generic_MSG":
            return super().nativeEvent(event_type, message)
        from ctypes import wintypes

        msg = wintypes.MSG.from_address(int(message))
        WM_NCCALCSIZE, WM_NCHITTEST = 0x0083, 0x0084

        if msg.message == WM_NCCALCSIZE and msg.wParam:
            if self.isMaximized():
                # Maximizada, Windows extiende la ventana más allá del monitor por el grosor del
                # marco. Sin este recorte, el borde del contenido queda afuera de la pantalla.
                self._recortar_maximizada(msg.lParam)
            return True, 0

        if msg.message == WM_NCHITTEST:
            local = self.mapFromGlobal(QCursor.pos())
            en_barra = self.titlebar.geometry().contains(local)
            en_caption = en_barra and self.titlebar.is_drag_area(self.titlebar.mapFrom(self, local))
            res = hit_test(local.x(), local.y(), self.width(), self.height(),
                           border=RESIZE_BORDER, maximized=self.isMaximized(),
                           en_caption=en_caption)
            return True, res

        return super().nativeEvent(event_type, message)

    def _recortar_maximizada(self, lparam: int) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = int(self.winId())
        SM_CXSIZEFRAME, SM_CYSIZEFRAME, SM_CXPADDEDBORDER = 32, 33, 92
        try:
            dpi = user32.GetDpiForWindow(hwnd)
            gx = user32.GetSystemMetricsForDpi(SM_CXSIZEFRAME, dpi) + \
                user32.GetSystemMetricsForDpi(SM_CXPADDEDBORDER, dpi)
            gy = user32.GetSystemMetricsForDpi(SM_CYSIZEFRAME, dpi) + \
                user32.GetSystemMetricsForDpi(SM_CXPADDEDBORDER, dpi)
        except (AttributeError, OSError):
            gx = user32.GetSystemMetrics(SM_CXSIZEFRAME) + user32.GetSystemMetrics(SM_CXPADDEDBORDER)
            gy = user32.GetSystemMetrics(SM_CYSIZEFRAME) + user32.GetSystemMetrics(SM_CXPADDEDBORDER)
        # NCCALCSIZE_PARAMS empieza con rgrc[3]; el primero es el rect de la ventana propuesta.
        rect = wintypes.RECT.from_address(lparam)
        rect.left += gx
        rect.top += gy
        rect.right -= gx
        rect.bottom -= gy
