"""El shell de la ventana: sidebar, stack de vistas y contadores (fase 1 de la interfaz, 2026-09-12).

Referencia visual: `Documentacion/Interfaz/mockups/design_handoff_toast_variants/mockup-exports/
21-panel-principal-captura-en-vivo.png`. Se testea offscreen, afirmando sobre lo que QUEDÓ en los
widgets (A3): el texto de un label, el índice del stack, el número que se ve.

Dos cosas que el mockup dice y la app NO copia, a propósito:

- **Los contadores del mockup son inventados** (`332 discos`, `45 PJs`, `1.2k`). Acá son consultas a
  la DB, y un 0 se muestra como 0: esconder un contador vacío es afirmar que no hay nada que contar.
- **La card de hotkeys del mockup tiene un BOTÓN de pausa** (2026-09-17): las teclas no llegan a la
  app con el juego en foco (UIPI). No hay botón de cerrar censo: el sistema está siempre operativo.
"""
from __future__ import annotations

import os
import sqlite3
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QLabel, QWidget     # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


# --- estructura -------------------------------------------------------------------------------

def test_tres_grupos_y_nueve_items_en_el_orden_del_mockup(qapp):
    from app.ui.shell.sidebar import GRUPOS
    assert [g for g, _ in GRUPOS] == ["MONITOREO", "BUILD", "SISTEMA"]
    claves = [k for _, items in GRUPOS for k, _ in items]
    assert claves == ["live", "historico", "lategame",
                      "discos", "roster", "armas", "equipos",
                      "catalogos", "config"]


def test_no_hay_pestana_estado(qapp):
    """Su contenido pasó a la barra inferior. Un lugar por dato (B1)."""
    from app.ui.shell.sidebar import GRUPOS
    etiquetas = [lbl.lower() for _, items in GRUPOS for _, lbl in items]
    assert "estado" not in etiquetas


def test_click_en_un_item_emite_su_clave_y_lo_marca_activo(qapp):
    from app.ui.shell.sidebar import Sidebar
    sb = Sidebar()
    recibidos = []
    sb.item_selected.connect(recibidos.append)
    sb.select("roster")
    assert recibidos == ["roster"]
    assert sb.active_key() == "roster"


def test_seleccionar_una_clave_desconocida_no_hace_nada(qapp):
    from app.ui.shell.sidebar import Sidebar
    sb = Sidebar()
    recibidos = []
    sb.item_selected.connect(recibidos.append)
    sb.select("no_existe")
    assert recibidos == []
    assert sb.active_key() == "live"          # el activo por defecto


# --- contadores -------------------------------------------------------------------------------

def _textos(w: QWidget) -> list[str]:
    return [lbl.text() for lbl in w.findChildren(QLabel)]


def test_los_contadores_se_ven_y_el_cero_no_se_esconde(qapp):
    from app.ui.shell.sidebar import Sidebar
    sb = Sidebar()
    sb.set_counters({"discos": 385, "roster": 51, "armas": 56, "lategame": 0})
    assert sb.counter_text("discos") == "385"
    assert sb.counter_text("lategame") == "0", "un contador vacío se muestra, no se esconde"
    assert sb.counter_text("config") == "", "los ítems sin contador quedan sin contador"
    # Y no alcanza con el texto: la primera versión dejaba el texto vacío pero DIBUJABA el recuadro
    # (se vio en la captura, no en este test). Se afirma lo que se ve.
    assert not sb.counter_visible("config"), "sin contador no se dibuja la caja vacía"
    assert not sb.counter_visible("live")
    assert sb.counter_visible("lategame"), "el 0 sí se dibuja"


def test_los_miles_se_abrevian_como_en_el_mockup(qapp):
    from app.ui.shell.sidebar import Sidebar
    sb = Sidebar()
    sb.set_counters({"historico": 1234})
    assert sb.counter_text("historico") == "1.2k"


@pytest.fixture
def db():
    c = sqlite3.connect(":memory:")
    c.executescript("""
        CREATE TABLE agents (id INTEGER PRIMARY KEY);
        CREATE TABLE inventory_discs (id INTEGER PRIMARY KEY, descartado INTEGER);
        CREATE TABLE inventory_weapons (id INTEGER PRIMARY KEY, descartado INTEGER);
        CREATE TABLE inventory_disc_evaluations (id INTEGER PRIMARY KEY);
        CREATE TABLE team_compositions (id INTEGER PRIMARY KEY);
        CREATE TABLE lategame_runs (id INTEGER PRIMARY KEY);
        INSERT INTO agents VALUES (1),(2),(3);
        INSERT INTO inventory_discs VALUES (1,0),(2,0),(3,1),(4,NULL);
        INSERT INTO inventory_weapons VALUES (1,0),(2,1);
        INSERT INTO inventory_disc_evaluations VALUES (1),(2);
    """)
    yield c
    c.close()


def test_leer_contadores_no_cuenta_las_bajas_logicas(db):
    """Discos y armas descartados NO cuentan. El tab `Estado` que esto reemplaza contaba las armas
    SIN filtrar: habría dicho 58 cuando hay 56 (dos fantasmas del scroll dados de baja)."""
    from app.ui.shell.contadores import leer_contadores
    c = leer_contadores(db)
    assert c["discos"] == 3        # 1, 2 y el NULL; el 3 está descartado
    assert c["armas"] == 1
    assert c["roster"] == 3
    assert c["historico"] == 2
    assert c["equipos"] == 0
    assert c["lategame"] == 0


def test_leer_contadores_sobrevive_a_una_tabla_que_falta(db):
    """Una DB vieja sin alguna tabla no tumba el sidebar: ese contador queda sin valor, el resto
    sale igual."""
    from app.ui.shell.contadores import leer_contadores
    db.execute("DROP TABLE lategame_runs")
    c = leer_contadores(db)
    assert "lategame" not in c
    assert c["discos"] == 3


# --- acciones -----------------------------------------------------------------------------------

def test_la_card_de_acciones_tiene_solo_la_pausa_y_ninguna_tecla(qapp):
    import re
    from PySide6.QtWidgets import QPushButton
    from app.ui.shell.sidebar import Sidebar
    sb = Sidebar()
    botones = [b.text() for b in sb.findChildren(QPushButton)]
    assert "Pausar" in botones
    assert not [b for b in botones if "censo" in b.lower()], "no hay pasada de censo que cerrar"
    assert not [t for t in _textos(sb) + botones if re.fullmatch(r"F\d{1,2}", t.strip())]


def test_la_pausa_sigue_el_estado_del_monitor(qapp):
    from app.ui.shell.sidebar import Sidebar
    sb = Sidebar()
    assert not sb.btn_pausa.isEnabled(), "sin monitor no hay nada que pausar"
    sb.on_monitor_started()
    assert sb.btn_pausa.isEnabled() and sb.btn_pausa.text() == "Pausar"
    sb.on_pause_changed(True)
    assert sb.btn_pausa.text() == "Reanudar"
    sb.on_monitor_stopped()
    assert sb.btn_pausa.text() == "Pausar" and not sb.btn_pausa.isEnabled()


def test_pausar_emite_el_pedido(qapp):
    from app.ui.shell.sidebar import Sidebar
    sb = Sidebar()
    sb.on_monitor_started()
    pedidos: list[int] = []
    sb.pausa_pedida.connect(lambda: pedidos.append(1))
    sb.btn_pausa.click()
    assert pedidos == [1]


# --- shell ------------------------------------------------------------------------------------

def test_el_sidebar_cambia_la_vista_del_stack(qapp):
    from app.ui.shell.window import ShellWindow
    w = ShellWindow(install_native_frame=False)
    vistas = {}
    for k in ("live", "discos", "roster"):
        vistas[k] = QWidget()
        w.add_view(k, vistas[k])
    w.sidebar.select("discos")
    assert w.current_view() is vistas["discos"]
    w.sidebar.select("live")
    assert w.current_view() is vistas["live"]


def test_un_item_sin_vista_no_rompe(qapp):
    """Los 9 ítems existen aunque alguna vista todavía no esté registrada."""
    from app.ui.shell.window import ShellWindow
    w = ShellWindow(install_native_frame=False)
    live = QWidget()
    w.add_view("live", live)
    w.sidebar.select("catalogos")
    assert w.current_view() is live


def test_la_barra_de_titulo_no_trae_fps_ni_latencia(qapp):
    """Decisión de Daniel: no le dicen nada al usuario. Y el `18 FPS` del mockup era ficción — el
    ciclo real del inventario tarda 1569 ms."""
    from app.ui.shell.titlebar import TitleBar
    textos = " ".join(_textos(TitleBar())).upper()
    assert "FPS" not in textos
    assert "LATENCIA" not in textos


def test_la_barra_de_titulo_muestra_el_estado_del_monitor(qapp):
    from app.ui.shell.titlebar import TitleBar
    tb = TitleBar()
    assert tb.state_text() == "EN REPOSO"
    tb.on_monitor_started()
    assert tb.state_text() == "CAPTURA"
    tb.on_pause_changed(True)
    assert tb.state_text() == "PAUSADO"
    tb.on_pause_changed(False)
    assert tb.state_text() == "CAPTURA"
    tb.on_monitor_stopped()
    assert tb.state_text() == "EN REPOSO"
