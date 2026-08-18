"""El roster DECLARADO por el usuario — y los tres desenlaces de esa declaración.

Existe porque el censo por observación no puede enumerar lo que el usuario **no** posee: el QA del
2026-08-17 midió que 4 de 6 personajes no obtenidos matchean a un PJ propio por encima del umbral
(`Lichter→Alice 0.667`), así que pararse en uno le dice al sistema que estás en otro.

La declaración tiene tres efectos, y los tres importan por motivos distintos:

1. **La tanda completa** queda registrada (los ~55 con su 1 o su 0). Es lo único que da el
   denominador, que la observación no puede dar por más que recorra.
2. **Un declarado sin fila en `agents` la recibe.** Sin esa fila la cosecha de badges se descarta
   en silencio — pasó con Aria.
3. **Un sobrante se marca, nunca se borra** (RNF-02): que el usuario no lo tilde es la señal más
   fuerte de una fila espuria, pero sigue siendo una señal, no una prueba.
"""
from __future__ import annotations

import sqlite3

import pytest

from app.core.roster_declaration import (
    CONFIRMADO,
    DECLARABLE,
    catalogo_declarable,
    declarar,
)

_ROSTER = [(1, "Ellen"), (2, "Aria"), (3, "Nekomata")]
_CATALOGO = {"Ellen", "Aria", "Nekomata", "Hugo", "Norma"}


@pytest.fixture
def dominio(tmp_path, monkeypatch):
    """DB mínima con las dos tablas que la declaración toca."""
    p = tmp_path / "danibod_zzz_v2.db"
    con = sqlite3.connect(p)
    con.executescript("""
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY, nombre TEXT UNIQUE NOT NULL,
            rango TEXT, elemento TEXT, rol TEXT, faccion TEXT,
            nivel INTEGER, pv INTEGER, ataque INTEGER, notas TEXT
        );
        CREATE TABLE inventory_discs (
            id INTEGER PRIMARY KEY, agente_asignado INTEGER, descartado INTEGER DEFAULT 0
        );
        CREATE TABLE roster_declarations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, nombre TEXT NOT NULL,
            poseido INTEGER NOT NULL, fuente TEXT NOT NULL DEFAULT 'usuario'
        );
    """)
    con.executemany(
        "INSERT INTO agents (id, nombre, rango, elemento, rol, faccion, nivel, notas) "
        "VALUES (?,?,?,?,?,?,?,?)",
        [(1, "Ellen", "S", "Hielo", "Ataque", "Victoria", 60, "nota previa"),
         (2, "Aria", "S", "Éter", "Anomalía", "Angels", None, None),
         (3, "Nekomata", "S", "Físico", "Ataque", "Cunning Hares", None, None)],
    )
    con.execute("INSERT INTO inventory_discs (id, agente_asignado) VALUES (1, 3)")
    con.commit(); con.close()
    monkeypatch.setenv("DANIBOD_DB_PATH", str(p))
    monkeypatch.delenv("DANIBOD_READONLY", raising=False)
    return p


def _catalogo():
    return catalogo_declarable(roster_catalogo=(_ROSTER, _CATALOGO))


def _agente(p, nombre):
    con = sqlite3.connect(p); con.row_factory = sqlite3.Row
    try:
        r = con.execute("SELECT * FROM agents WHERE nombre = ?", (nombre,)).fetchone()
        return dict(r) if r else None
    finally:
        con.close()


def _declaraciones(p):
    con = sqlite3.connect(p)
    try:
        return con.execute(
            "SELECT nombre, poseido FROM roster_declarations ORDER BY nombre").fetchall()
    finally:
        con.close()


# --- el catálogo declarable -------------------------------------------------------------------

def test_el_catalogo_une_el_roster_con_los_que_solo_tienen_arte(dominio):
    """Hugo y Norma no están en `agents` y existen igual. Sin ellos el usuario no puede declarar
    que SÍ los tiene, que es medio punto de todo esto."""
    nombres = {p.nombre for p in _catalogo()}
    assert nombres == _CATALOGO


def test_marca_quien_ya_tiene_fila_en_agents(dominio):
    por_nombre = {p.nombre: p for p in _catalogo()}
    assert por_nombre["Ellen"].en_agents is True
    assert por_nombre["Hugo"].en_agents is False


def test_arrastra_la_identidad_de_los_que_estan(dominio):
    """El diálogo la muestra al lado del nombre; sin eso, 55 checkboxes son 55 strings sueltos."""
    ellen = next(p for p in _catalogo() if p.nombre == "Ellen")
    assert (ellen.rango, ellen.elemento, ellen.rol) == ("S", "Hielo", "Ataque")


def test_un_pj_solo_del_arte_viene_sin_identidad_y_no_se_inventa(dominio):
    """RNF-02: de Hugo se sabe el nombre y nada más. Rellenar rango/elemento con algo plausible
    sería exactamente el error que la regla prohíbe."""
    hugo = next(p for p in _catalogo() if p.nombre == "Hugo")
    assert (hugo.rango, hugo.elemento, hugo.rol, hugo.faccion) == (None, None, None, None)


# --- confirmado vs declarable -----------------------------------------------------------------

def test_tener_discos_confirma_la_posesion(dominio):
    """Nekomata no tiene stats cargados pero tiene un disco equipado. Un disco equipado es prueba
    de posesión: no se puede declarar que no tenés al PJ que lo lleva puesto."""
    nekomata = next(p for p in _catalogo() if p.nombre == "Nekomata")
    assert nekomata.estado == CONFIRMADO
    assert "disco" in nekomata.motivo.lower()


def test_tener_stats_por_encima_del_default_confirma(dominio):
    ellen = next(p for p in _catalogo() if p.nombre == "Ellen")
    assert ellen.estado == CONFIRMADO


def test_sin_discos_ni_stats_queda_declarable(dominio):
    """Aria está en `agents` pero recién onboardeada: sin datos, no hay evidencia que la confirme.

    Es también el estado de TODOS los PJs el día después de reconstruir la DB — y está bien: se
    está declarando desde cero. El bloqueo recupera sentido a medida que el censo llena datos."""
    aria = next(p for p in _catalogo() if p.nombre == "Aria")
    assert aria.estado == DECLARABLE


def test_los_confirmados_vienen_tildados(dominio):
    por_nombre = {p.nombre: p for p in _catalogo()}
    assert por_nombre["Ellen"].poseido_actual is True
    assert por_nombre["Hugo"].poseido_actual is False


# --- la escritura -----------------------------------------------------------------------------

def test_guarda_la_tanda_COMPLETA_con_los_ceros(dominio):
    """Los no poseídos con `poseido = 0` son el dato que la pantalla no expone y que después
    permite vetar un match difuso. Guardar solo los tildados perdería justo eso."""
    declarar({"Ellen", "Aria", "Nekomata"}, catalogo=_catalogo(), fecha="2026-08-17")
    filas = _declaraciones(dominio)
    assert len(filas) == 5
    assert dict(filas) == {"Ellen": 1, "Aria": 1, "Nekomata": 1, "Hugo": 0, "Norma": 0}


def test_toda_la_tanda_comparte_el_mismo_ts(dominio):
    """Es lo que la vuelve una FOTO y no cinco eventos sueltos."""
    declarar({"Ellen"}, catalogo=_catalogo(), fecha="2026-08-17")
    con = sqlite3.connect(dominio)
    tss = {r[0] for r in con.execute("SELECT ts FROM roster_declarations")}
    con.close()
    assert len(tss) == 1


def test_un_declarado_sin_fila_en_agents_la_recibe(dominio):
    """Sin fila en `agents` la cosecha de badges se descarta EN SILENCIO (pasó con Aria). La fila
    es lo que hace existir al personaje para el resto del sistema."""
    res = declarar({"Ellen", "Hugo"}, catalogo=_catalogo(), fecha="2026-08-17")
    assert res.creados == ["Hugo"]
    hugo = _agente(dominio, "Hugo")
    assert hugo is not None
    assert hugo["rango"] is None and hugo["elemento"] is None, "no se inventa lo que no se sabe"
    assert "declarado_por_usuario_2026-08-17" in hugo["notas"]
    assert "onboarding" in hugo["notas"]


def test_un_sobrante_se_marca_y_NO_se_borra(dominio):
    res = declarar({"Ellen"}, catalogo=_catalogo(), fecha="2026-08-17")
    assert set(res.marcados) == {"Aria", "Nekomata"}
    for nombre in ("Aria", "Nekomata"):
        fila = _agente(dominio, nombre)
        assert fila is not None, "RNF-02: no se borra"
        assert "no_declarado_2026-08-17" in fila["notas"]


def test_la_marca_no_pisa_lo_que_ya_habia_en_notas(dominio):
    declarar(set(), catalogo=_catalogo(), fecha="2026-08-17")
    assert "nota previa" in _agente(dominio, "Ellen")["notas"]


def test_declarar_dos_veces_el_mismo_dia_no_duplica_la_marca(dominio):
    for _ in range(2):
        declarar({"Ellen"}, catalogo=_catalogo(), fecha="2026-08-17")
    assert _agente(dominio, "Aria")["notas"].count("no_declarado_2026-08-17") == 1


def test_declarar_de_nuevo_deja_las_dos_tandas_en_el_historial(dominio):
    """Re-declarar es una tanda NUEVA, no una corrección de la anterior. Eso es lo que vuelve la
    tabla una auditoría de sincronía y no un flag de 'ya se hizo'."""
    declarar({"Ellen"}, catalogo=_catalogo(), fecha="2026-08-17")
    declarar({"Ellen", "Aria"}, catalogo=_catalogo(), fecha="2026-08-18")
    con = sqlite3.connect(dominio)
    tandas = con.execute("SELECT COUNT(DISTINCT ts) FROM roster_declarations").fetchone()[0]
    con.close()
    assert tandas == 2


def test_un_declarado_que_ya_estaba_no_se_toca(dominio):
    declarar({"Ellen", "Aria", "Nekomata"}, catalogo=_catalogo(), fecha="2026-08-17")
    assert _agente(dominio, "Ellen")["notas"] == "nota previa"


# --- RNF-01 y el gate de readonly ---------------------------------------------------------------

def test_deja_backup_previo(dominio):
    declarar({"Ellen"}, catalogo=_catalogo(), fecha="2026-08-17")
    assert list(dominio.parent.glob("*.backup_predeclaracion_*.db")), "falta el backup RNF-01"


def test_en_readonly_no_escribe_y_LO_DICE(dominio, monkeypatch):
    """Un QA cuyo 'pass' es el silencio se reporta como fallo. El resultado tiene que distinguir
    'no escribí porque es readonly' de 'escribí'."""
    monkeypatch.setenv("DANIBOD_READONLY", "1")
    res = declarar({"Ellen"}, catalogo=_catalogo(), fecha="2026-08-17")
    assert res.escribio is False
    assert _declaraciones(dominio) == []
    assert _agente(dominio, "Aria")["notas"] is None


def test_declarar_sin_catalogo_no_hace_nada(dominio):
    """Si el catálogo viene vacío es que algo falló al leerlo. Escribir una tanda de cero filas
    declararía que el usuario no tiene NADA."""
    res = declarar({"Ellen"}, catalogo=[], fecha="2026-08-17")
    assert res.escribio is False
    assert _declaraciones(dominio) == []


def test_el_resultado_trae_los_conteos_para_la_ui(dominio):
    res = declarar({"Ellen", "Hugo"}, catalogo=_catalogo(), fecha="2026-08-17")
    assert res.declarados == 2
    assert res.total == 5
    assert res.escribio is True
