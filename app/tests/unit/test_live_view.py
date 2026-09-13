"""La vista "Captura en vivo": card del ítem, hexágono del build y consola (fase 1, 2026-09-12).

Offscreen, afirmando sobre lo que QUEDÓ a la vista (A3). Las garantías que importan, más allá de
que pinte:

1. **El hexágono usa el orden de slots del juego**, no el del mockup.
2. **Un drop nunca dibuja el build del PJ que eligió el scoring.** `disc_detected` trae un `target`
   que sale de un scoring sin calibrar; la vista lo descarta.
3. **Las tenencias no se colapsan**: "sin identificar" no es "libre" y "no se pudo leer" no es
   ninguna de las dos.
4. La consola **escapa** lo que viene del OCR y respeta el **tope de 1000 bloques** (RNF-06).
"""
from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication      # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def _obs(**kw) -> dict:
    base = {
        "set": "Fuego carmesí", "set_logo": None, "set_tier": 4, "slot": 4, "rareza": "S",
        "nivel": 15, "main": "Ataque %", "main_valor": 30.0, "main_unidad": "%",
        "subs_detail": ["Daño Crítico 9.6% (+3)", "Prob. Crítica 2.4%"],
        "dueno": "Yanagi", "dueno_avatar": None, "tenencia": "equipada",
    }
    base.update(kw)
    return base


def _arma(**kw) -> dict:
    base = {"nombre": "Rotor de cañón", "en_catalogo": True, "rareza": "A", "nivel": 60,
            "nivel_max": 60, "refinamiento": 5, "stat": "ATQ% 25%", "dueno": None,
            "tenencia": "libre", "cambio": False, "tenencia_previa": None, "icono": None}
    base.update(kw)
    return base


# --- 1 · el orden de slots del juego ----------------------------------------------------------

def test_el_hexagono_usa_el_orden_de_zzz():
    """Columna izquierda 1→2→3 hacia abajo, derecha 6→5→4 hacia abajo."""
    from app.ui.live.hexagon import posiciones_slots
    cx = cy = 100.0
    p = posiciones_slots(cx, cy, 50.0)
    izq = [p[1], p[2], p[3]]
    der = [p[6], p[5], p[4]]
    assert all(x < cx for x, _ in izq), "1, 2 y 3 van a la izquierda"
    assert all(x > cx for x, _ in der), "4, 5 y 6 van a la derecha"
    assert izq[0][1] < izq[1][1] < izq[2][1], "la izquierda baja 1→2→3"
    assert der[0][1] < der[1][1] < der[2][1], "la derecha baja 6→5→4"


def test_no_es_el_orden_del_mockup():
    """El mockup arranca el slot 1 arriba al centro y gira en sentido horario. Si alguien 'lo
    alinea con el diseño', este test lo frena."""
    from app.ui.live.hexagon import posiciones_slots
    x1, y1 = posiciones_slots(100.0, 100.0, 50.0)[1]
    assert abs(x1 - 100.0) > 1, "el slot 1 no está arriba al centro"


# --- 2 · la card ------------------------------------------------------------------------------

def test_arranca_esperando(qapp):
    from app.ui.live.item_card import ItemCard
    c = ItemCard()
    assert c.modo() == "vacio"
    assert any("Esperando" in t for t in c.textos_visibles())


def test_disco_con_dueno_dibuja_el_build_de_ese_pj(qapp):
    from app.ui.live.item_card import ItemCard
    c = ItemCard()
    build = {1: {"logo": None, "nivel": 15}, 4: {"logo": None, "nivel": 15}}
    c.mostrar_disco(_obs(), build)
    assert c.modo() == "disco_con_dueno"
    hexa = c.hexagono()
    assert hexa is not None
    assert hexa.destacado() == 4, "el slot del disco que se está mirando"
    assert sorted(hexa.slots()) == [1, 4]
    textos = c.textos_visibles()
    assert "En Yanagi" in textos
    assert "EQUIPADO" in textos
    assert "Ataque %" in textos and "30%" in textos
    assert "Daño Crítico 9.6% (+3)" in textos


def test_disco_sin_dueno_no_dibuja_hexagono(qapp):
    from app.ui.live.item_card import ItemCard
    c = ItemCard()
    c.mostrar_disco(_obs(dueno=None, tenencia="libre"))
    assert c.modo() == "disco_sin_dueno"
    assert c.hexagono() is None
    textos = c.textos_visibles()
    assert "LIBRE" in textos
    assert not any(t.startswith("En ") for t in textos)


def test_las_tenencias_se_dicen_distinto(qapp):
    from app.ui.live.item_card import ItemCard
    vistos = {}
    for ten in ("libre", "incierto", "sin_leer", "nuevo"):
        c = ItemCard()
        c.mostrar_disco(_obs(dueno=None, tenencia=ten))
        vistos[ten] = c._tenencia.text()
    assert len(set(vistos.values())) == 4, vistos
    assert "LIBRE" not in vistos["incierto"], "sin identificar no es libre"
    assert "LIBRE" not in vistos["sin_leer"]


def test_pj_con_un_slot_vacio_pinta_sin_romper(qapp):
    """Cinco discos: el hueco se dibuja como hueco. `grab()` fuerza el paintEvent de verdad."""
    from app.ui.live.item_card import ItemCard
    c = ItemCard()
    c.resize(400, 700)
    build = {s: {"logo": None, "nivel": 10} for s in (1, 2, 3, 5, 6)}
    c.mostrar_disco(_obs(slot=4), build)
    assert 4 not in c.hexagono().slots()
    assert not c.grab().isNull()


def test_nivel_cero_es_un_nivel(qapp):
    """Mismo bug que tuvo el log el 2026-08-30: `if nivel` convertía el 0 en 'Nivel ?'."""
    from app.ui.live.item_card import ItemCard
    c = ItemCard()
    c.mostrar_disco(_obs(nivel=0, dueno=None, tenencia="nuevo"))
    assert any("Nivel 0/15" in t for t in c.textos_visibles())


def test_arma_libre(qapp):
    from app.ui.live.item_card import ItemCard
    c = ItemCard()
    c.mostrar_arma(_arma())
    assert c.modo() == "arma"
    textos = c.textos_visibles()
    assert "Rotor de cañón" in textos
    assert any("Nivel 60/60" in t and "P5" in t for t in textos)
    assert "LIBRE" in textos
    assert "sin ícono" in textos


def test_arma_con_dueno(qapp):
    from app.ui.live.item_card import ItemCard
    c = ItemCard()
    c.mostrar_arma(_arma(dueno="Evelyn", tenencia="incierto"))
    textos = c.textos_visibles()
    assert "Evelyn" in textos
    assert "EQUIPADO" in textos


def test_arma_fuera_de_catalogo_lo_avisa(qapp):
    from app.ui.live.item_card import ItemCard
    c = ItemCard()
    c.mostrar_arma(_arma(nombre="Anhelo marcato ESTRUENDO", en_catalogo=False))
    textos = c.textos_visibles()
    assert "Anhelo marcato ESTRUENDO" in textos
    assert any("Fuera del catálogo" in t for t in textos)


def test_arma_refinamiento_desconocido_no_inventa_p1(qapp):
    """NULL en refinamiento es 'no se pudo leer' desde la mig `_26`, no P1."""
    from app.ui.live.item_card import ItemCard
    c = ItemCard()
    c.mostrar_arma(_arma(refinamiento=None))
    assert any("P?" in t for t in c.textos_visibles())
    assert not any("P1" in t for t in c.textos_visibles())


# --- 3 · la vista: un drop no hereda el PJ del scoring -----------------------------------------

def test_un_drop_no_trae_nada_del_scoring():
    from app.ui.live.view import drop_como_observacion
    drop = {"variant": "equipar", "set": "Fuego carmesí", "slot": 2, "rarity": "S",
            "main": "ATK", "main_value": "2200.0", "subs_detail": ["x"], "target": "Ellen",
            "mind": 0, "score": 87.3, "threshold": 0.75, "urgency": 0.9}
    o = drop_como_observacion(drop)
    assert o["dueno"] is None
    assert o["tenencia"] == "nuevo"
    for k in ("target", "score", "variant", "threshold", "urgency"):
        assert k not in o
    assert o["main_valor"] == 2200.0 and o["main_unidad"] == "flat"


def test_la_vista_no_dibuja_el_build_del_pj_sugerido(qapp):
    """La garantía central: aunque el payload diga `target: Ellen`, no se consulta ni se dibuja el
    build de Ellen."""
    from app.ui.live.view import LiveView
    pedidos = []
    v = LiveView(build_fn=lambda n: pedidos.append(n) or {})
    v.on_disc_detected({"set": "Fuego carmesí", "slot": 2, "rarity": "S", "main": "ATK",
                        "main_value": "2200.0", "subs_detail": [], "target": "Ellen",
                        "score": 87.3, "variant": "equipar"})
    assert pedidos == [], "no se pidió ningún build"
    assert v.item_card.modo() == "disco_sin_dueno"


def test_la_vista_pide_el_build_del_dueno_en_pantalla(qapp):
    from app.ui.live.view import LiveView
    pedidos = []
    v = LiveView(build_fn=lambda n: pedidos.append(n) or {4: {"logo": None, "nivel": 15}})
    v.on_disc_observed(_obs(dueno="Yanagi"))
    assert pedidos == ["Yanagi"]
    assert v.item_card.modo() == "disco_con_dueno"


def test_la_region_derecha_esta_en_blanco(qapp):
    """Decisión de Daniel: en blanco hasta decidir qué va. Si alguien le mete algo sin decidirlo,
    este test lo marca."""
    from app.ui.live.view import LiveView
    v = LiveView()
    assert v.region_derecha.layout().count() == 0


# --- 4 · la consola ---------------------------------------------------------------------------

def test_la_consola_respeta_el_tope_de_bloques(qapp):
    from app.ui.live.console import MAX_BLOQUES, Console
    c = Console()
    for i in range(MAX_BLOQUES + 150):
        c.append_log(f"[disco] línea {i}")
    assert c.bloques() <= MAX_BLOQUES


def test_la_consola_escapa_lo_que_viene_del_ocr(qapp):
    """Un nombre leído por OCR con `<` no puede romper el render ni interpretarse como HTML."""
    from app.ui.live.console import Console
    c = Console()
    c.append_log("[reconocido] <b>Tetera</b> & cia")
    texto = c.texto_log()
    assert "<b>Tetera</b> & cia" in texto


def test_el_estado_actual_y_el_boton_de_captura(qapp):
    from app.ui.live.console import Console
    c = Console()
    emitidos = []
    c.start_monitor_requested.connect(lambda: emitidos.append("start"))
    c.stop_monitor_requested.connect(lambda: emitidos.append("stop"))
    c.on_state_changed("S30", 0.93)
    assert c.estado_text() == "S30"
    assert c.toggle_text() == "Iniciar captura"
    c._toggle.click()
    c.on_monitor_started()
    assert c.toggle_text() == "Detener captura"
    c._toggle.click()
    assert emitidos == ["start", "stop"]


# --- el proveedor del build -------------------------------------------------------------------

def test_build_provider_lee_inventory_discs(mem_db):
    from app.ui.live.build_provider import BuildProvider
    mem_db.execute("ALTER TABLE disc_sets ADD COLUMN nombre_en TEXT")
    for s in (1, 4):
        mem_db.execute(
            "INSERT INTO inventory_discs (id, set_id, slot, main_stat, main_valor, nivel, equipado,"
            " agente_asignado, descartado) VALUES (?,1,?,'ATK%',30,12,1,1,0)", (100 + s, s))
    b = BuildProvider(mem_db).build_de("TestAgent")
    assert sorted(b) == [1, 4]
    assert b[4]["nivel"] == 12


def test_build_provider_pj_desconocido(mem_db):
    from app.ui.live.build_provider import BuildProvider
    assert BuildProvider(mem_db).build_de("NoExiste") == {}
    assert BuildProvider(mem_db).build_de(None) == {}
