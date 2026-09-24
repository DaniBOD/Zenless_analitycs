"""Las marcas translúcidas se pintan del color que dicen, no de otro.

Qt lee un hex de 8 dígitos como `#AARRGGBB` (el alfa PRIMERO), también dentro de un stylesheet.
Pegarle el alfa al final (`AMBAR + "40"`, `{AMBAR}88`) no da "el mismo ámbar, translúcido": da
alfa F0 y color AA3C40, un rojo casi opaco. Ver
`Dev_IA/documentacion_cruda/2026-09/2026-09-24_FIX_El_alfa_pegado_al_hex_pinta_otro_color.md`.

Cada test captura el widget y compara el píxel de la marca contra la mezcla esperada: el color con
su alfa sobre el fondo que se MIDE al lado de la marca, no sobre uno supuesto.
"""
from __future__ import annotations

import io
import os
import re
import sys
import tokenize
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtGui import QColor                      # noqa: E402
from PySide6.QtWidgets import QApplication, QFrame   # noqa: E402

from app.ui.armas import celda as celda_armas         # noqa: E402
from app.ui.armas.celda import CeldaArma              # noqa: E402
from app.ui.armas.datos import FilaArma               # noqa: E402
from app.tests.unit.test_armas_datos import _arma      # noqa: E402
from app.ui.armas.view import ArmasView, _TarjetaPJ   # noqa: E402
from app.ui.roster import celda as celda_roster       # noqa: E402
from app.ui.roster.celda import CeldaRoster           # noqa: E402
from app.ui.roster.datos import CeldaPJ               # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication(sys.argv)


def _mezcla(color: str, alfa: int, fondo: QColor) -> QColor:
    """`color` con opacidad `alfa` (0-255) sobre `fondo`, como compone Qt."""
    c, a = QColor(color), alfa / 255
    return QColor(*(round(a * x + (1 - a) * y) for x, y in
                    ((c.red(), fondo.red()), (c.green(), fondo.green()), (c.blue(), fondo.blue()))))


def _cerca(px: QColor, obj: QColor, tol: int = 8) -> bool:
    return all(abs(a - b) <= tol for a, b in ((px.red(), obj.red()), (px.green(), obj.green()),
                                              (px.blue(), obj.blue())))


def _relleno_de_la_esquina(img, lado: int) -> QColor:
    """El relleno de la esquina rayada (triángulo arriba a la derecha): entre raya y raya, el píxel
    más oscuro del interior. Se dejan afuera los bordes del triángulo y el borde del widget."""
    w = img.width()
    interior = [QColor(img.pixel(x, y)) for y in range(1, lado - 3)
                for x in range(w - lado + y + 2, w - 1)]
    return min(interior, key=lambda c: c.red() + c.green() + c.blue())


# --- Roster ------------------------------------------------------------------------------------

def _celda_pj(**kw) -> CeldaPJ:
    base = dict(id=9, nombre="X", rango="S", elemento="Eléctrico", rol="Ataque",
                faccion="Taller Flint", mindscape=0, nivel=60, discos=6, tiene_arma=True,
                sin_thresholds=False, variante_de=None, prioridad="normal")
    base.update(kw)
    return CeldaPJ(**base)


def _captura_roster(celda: CeldaPJ):
    w = CeldaRoster(celda)
    w.resize(122, 96)
    w.layout().activate()
    return w, w.grab().toImage()


def test_roster_la_esquina_de_faltan_datos_es_ambar_no_roja(qapp):
    _, img = _captura_roster(_celda_pj(sin_thresholds=True))
    lado = 13
    fondo = QColor(img.pixel(img.width() - lado - 2, 2))
    relleno = _relleno_de_la_esquina(img, lado)
    esperado = _mezcla(celda_roster.AMBAR, 0x40, fondo)
    assert _cerca(relleno, esperado), (relleno.name(), esperado.name())


def test_roster_el_halo_del_rango_infinito_es_naranja_no_magenta(qapp):
    """El halo es el trazo de 3 px alrededor de la cápsula: su fila de arriba cae sobre el fondo (la
    cápsula maciza arranca un píxel más abajo). Se lo compara con el naranja al 40 % sobre la
    esquina del mismo widget, que queda afuera de la cápsula redondeada."""
    w, img = _captura_roster(_celda_pj(rango="∞"))
    o = w._rango.mapTo(w, w._rango.rect().topLeft())
    fondo = QColor(img.pixel(o.x(), o.y()))
    halo = QColor(img.pixel(o.x() + w._rango.width() // 2, o.y()))
    esperado = _mezcla(celda_roster.NARANJA_INF, 0x66, fondo)
    assert _cerca(halo, esperado), (halo.name(), esperado.name())


# --- Armas -------------------------------------------------------------------------------------

def test_armas_la_esquina_de_dato_faltante_es_ambar_no_roja(qapp):
    """Sin ícono en el catálogo la celda lleva la esquina rayada ámbar al 20 %."""
    fila = FilaArma(id=1, weapon_id=1, nombre="A", nombre_en=None, rareza="A", especialidad=None,
                    stat_base_valor=None, stat_base_tipo=None, stat=None, stat_valor=None,
                    nivel=None, refinamiento=None, equipado=False, dueno=None, dueno_id=None,
                    dueno_avatar=None, icono=None, copias=1)
    w = CeldaArma(fila)
    w.resize(celda_armas.CELDA_W, celda_armas.CELDA_H)
    w.layout().activate()
    img = w.grab().toImage()
    lado = 13
    fondo = QColor(img.pixel(img.width() - lado - 2, 2))
    relleno = _relleno_de_la_esquina(img, lado)
    esperado = _mezcla(celda_armas.AMBAR, 0x33, fondo)
    assert _cerca(relleno, esperado), (relleno.name(), esperado.name())


def test_armas_el_borde_de_la_tarjeta_de_pj_sin_arma_es_ambar(qapp):
    """Stylesheet: el QSS lee el hex igual que QColor, así que `{AMBAR}88` también pintaba otro
    color. El borde de arriba se compara con el ámbar al 53 % sobre el fondo de la tarjeta, medido
    dos píxeles más abajo."""
    w = _TarjetaPJ({"nombre": "Anby", "elemento": "Eléctrico"})
    img = w.grab().toImage()
    x = w.width() - 20
    fondo = QColor(img.pixel(x, 2))
    borde = QColor(img.pixel(x, 0))
    esperado = _mezcla(celda_armas.AMBAR, 0x88, fondo)
    assert _cerca(borde, esperado), (borde.name(), esperado.name())


def test_armas_el_borde_del_aviso_de_pjs_sin_arma_es_ambar(qapp, db_esquema_real):
    """El aviso arriba de las tarjetas (modo auditoría "PJs sin arma"): mismo stylesheet, mismo
    error, con el ámbar al 40 %. El fondo se mide adentro del aviso, donde no hay texto."""
    con = db_esquema_real
    con.executescript("""
        INSERT INTO weapons (id, nombre, nombre_en, rareza, tipo_especialidad) VALUES
            (1, 'Llanto mielgo', 'Weeping Gemini', 'A', 'Anomalía');
        INSERT INTO agents (id, nombre, rango, elemento, rol, faccion, protected_build) VALUES
            (1, 'Yanagi', 'S', 'Eléctrico', 'Anomalía', 'Hollow Special Operations Section 6', 0),
            (3, 'Anby', 'A', 'Eléctrico', 'Aturdimiento', 'Cunning Hares', 0);
    """)
    _arma(con, 10, 1, agente=1, equipado=1)
    v = ArmasView(con)
    v.resize(1100, 756)
    v.show()
    try:
        v.filtros.chip("auditoria", "pjs_sin_arma").click()
        qapp.processEvents()
        aviso = v.findChild(QFrame, "aviso_pjs")
        assert aviso is not None and aviso.isVisible()
        img = aviso.grab().toImage()
        x = aviso.width() - 6
        fondo = QColor(img.pixel(x, 3))
        borde = QColor(img.pixel(x, 0))
        esperado = _mezcla(celda_armas.AMBAR, 0x66, fondo)
        assert _cerca(borde, esperado), (borde.name(), esperado.name())
    finally:
        v.close()


# --- la guarda ---------------------------------------------------------------------------------

_UI = Path(__file__).resolve().parents[2] / "ui"
_DOS_HEX = re.compile(r"""^[rRbBuU]?["'][0-9A-Fa-f]{2}["']$""")
_FSTRING_ALFA = re.compile(r"\}[0-9A-Fa-f]{2}(?![0-9A-Za-z])")


def alfas_pegados(fuente: str) -> list[tuple[int, str]]:
    """Donde el código le pega dos dígitos hex a un color: `x + "40"` o `f"{x}88"`. Mira TOKENS,
    así un comentario que cuenta el error no cuenta como el error."""
    hallados, previo = [], None
    for tok in tokenize.generate_tokens(io.StringIO(fuente).readline):
        if tok.type == tokenize.STRING:
            if previo is not None and previo.string == "+" and _DOS_HEX.match(tok.string):
                hallados.append((tok.start[0], tok.line.strip()))
            elif tok.string[:1] in "fF" and _FSTRING_ALFA.search(tok.string):
                hallados.append((tok.start[0], tok.line.strip()))
        if tok.type not in (tokenize.NL, tokenize.COMMENT):
            previo = tok
    return hallados


@pytest.mark.parametrize("codigo", [
    'QColor(AMBAR + "40")',
    "QColor(AMBAR + '66')",
    'css = f"border: 1px solid {AMBAR}88;"',
    'css = f"border: 1px solid {T.YELLOW}66; color: red"',
])
def test_la_guarda_ve_las_dos_formas(codigo):
    assert alfas_pegados(codigo + "\n")


@pytest.mark.parametrize("codigo", [
    'x = "#F0AA3C"  # antes era AMBAR + "40"',
    'css = f"border: {grosor}px solid {AMBAR};"',
    'texto = f"{n}abc"',         # siguen más letras: es una palabra, no un alfa
    'total = a + "1"',
])
def test_la_guarda_no_ve_fantasmas(codigo):
    assert not alfas_pegados(codigo + "\n")


def test_ninguna_pantalla_le_pega_el_alfa_al_hex():
    """Qt lee #RRGGBBAA como #AARRGGBB, en QColor y en QSS. El alfa va con `setAlpha` (o
    `QColor.name(HexArgb)` para un stylesheet), nunca pegado al string."""
    archivos = sorted(_UI.rglob("*.py"))
    assert len(archivos) > 20, _UI          # que la guarda esté mirando la carpeta de verdad
    hallados = [f"{f.relative_to(_UI)}:{n}: {linea}" for f in archivos
                for n, linea in alfas_pegados(f.read_text(encoding="utf-8"))]
    assert not hallados, "\n".join(hallados)
